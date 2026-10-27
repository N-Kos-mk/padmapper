"""設定画面 (ブラウザ) 用のローカル HTTP サーバー。

127.0.0.1 だけで待ち受け、起動ごとに作るトークンを持たない API 要求は拒否する。
Host / Origin も確かめ、他の Web ページから設定を読み書きされないようにする。
"""

import json
import secrets
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .foreground import running_apps
from .profiles import ProfileError

WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/favicon.ico": ("icon.ico", "image/x-icon"),
}
# 外部から読み込むのはアイコン (Lucide、SRI で内容を固定) だけ
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)
STREAM_INTERVAL = 1 / 30
KEEPALIVE_INTERVAL = 2.0
MAX_BODY = 1 << 20


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Server:
    def __init__(self, runtime, port=0):
        self.runtime = runtime
        self.token = secrets.token_urlsafe(24)
        self.stopping = threading.Event()
        handler = type("Handler", (_Handler,), {"app": self})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/?token={self.token}"
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self.httpd.serve_forever, name="padmapper-http", daemon=True)
        self._thread.start()

    def stop(self):
        self.stopping.set()
        self.httpd.shutdown()
        self.httpd.server_close()


class _Handler(BaseHTTPRequestHandler):
    app = None

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    # 共通処理

    def _dispatch(self, method):
        url = urlsplit(self.path)
        try:
            self._check_origin()
            if method == "GET" and url.path in STATIC_FILES:
                self._send_static(*STATIC_FILES[url.path])
                return
            if not url.path.startswith("/api/"):
                raise ApiError(404, "見つかりません")
            self._check_token(parse_qs(url.query))
            body = None
            if method in ("POST", "PUT", "DELETE"):
                # JSON 以外を拒否すると、他のサイトのフォームなどからは送れなくなる
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    raise ApiError(415, "Content-Type は application/json にしてください")
                body = self._read_json()
            result = self._route(method, url.path, body)
            if result is not None:
                self._send_json(200, result)
        except ApiError as e:
            self._send_json(e.status, {"error": str(e)})
        except ProfileError as e:
            self._send_json(400, {"error": str(e)})
        except (ConnectionError, OSError):
            pass
        except Exception as e:
            self.app.runtime.log("設定画面の処理でエラーが発生しました\n" + traceback.format_exc())
            self._send_json(500, {"error": f"内部エラー: {e}"})

    def _check_origin(self):
        allowed = {f"127.0.0.1:{self.app.port}", f"localhost:{self.app.port}"}
        if self.headers.get("Host", "") not in allowed:
            raise ApiError(403, "許可されていない Host です")
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{h}" for h in allowed}:
            raise ApiError(403, "許可されていない Origin です")

    def _check_token(self, query):
        token = self.headers.get("X-Token") or query.get("token", [""])[0]
        if not secrets.compare_digest(token.encode(), self.app.token.encode()):
            raise ApiError(403, "トークンが一致しません。トレイアイコンから設定画面を開き直してください")

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ApiError(413, "要求が大きすぎます")
        if not length:
            return {}
        try:
            body = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            raise ApiError(400, "JSON を解釈できません") from None
        if not isinstance(body, dict):
            raise ApiError(400, "JSON のオブジェクトを送ってください")
        return body

    def _send_json(self, status, data):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _send_static(self, filename, content_type):
        payload = (WEB_DIR / filename).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        self.end_headers()
        self.wfile.write(payload)

    # API

    def _route(self, method, path, body):
        rt = self.app.runtime
        if path == "/api/state" and method == "GET":
            return rt.snapshot()
        if path == "/api/stream" and method == "GET":
            self._stream()
            return None
        if path == "/api/profiles":
            if method == "GET":
                return rt.profiles_payload()
            if method == "POST":
                rt.create_profile(body.get("name"), body.get("copy_from"))
                return rt.profiles_payload()
        if path.startswith("/api/profiles/"):
            name = unquote(path[len("/api/profiles/") :])
            if method == "PUT":
                rt.save_profile(name, body.get("raw"))
                return rt.profiles_payload()
            if method == "DELETE":
                rt.delete_profile(name)
                return rt.profiles_payload()
        if path == "/api/config" and method == "PUT":
            rt.save_config(body.get("raw"))
            return rt.profiles_payload()
        if path == "/api/enabled" and method == "POST":
            rt.set_enabled(body.get("enabled"))
            return rt.snapshot()
        if path == "/api/manual" and method == "POST":
            rt.set_manual(body.get("name"))
            return rt.snapshot()
        if path == "/api/apps" and method == "GET":
            return {"apps": running_apps()}
        if path == "/api/logs" and method == "GET":
            return {"lines": list(rt.logs)}
        raise ApiError(404, "見つかりません")

    def _stream(self):
        """コントローラーの状態を Server-Sent Events で送り続ける。"""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        last = None
        last_sent = 0.0
        while not self.app.stopping.is_set():
            data = json.dumps(self.app.runtime.snapshot(), ensure_ascii=False)
            now = time.monotonic()
            if data != last:
                self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                last, last_sent = data, now
            elif now - last_sent >= KEEPALIVE_INTERVAL:
                # 閉じられた接続を検出するために、変化がなくても定期的に書き込む
                self.wfile.write(b": keepalive\n\n")
                last_sent = now
            self.wfile.flush()
            time.sleep(STREAM_INTERVAL)

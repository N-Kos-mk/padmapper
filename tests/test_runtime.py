import http.client
import json
import os
import shutil
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from padmapper import uiwindow
from padmapper.__main__ import install_examples
from padmapper.foreground import Window
from padmapper.profiles import ProfileError
from padmapper.runtime import Runtime
from padmapper.server import Server
from tests.test_engine import Recorder

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO = Path(__file__).resolve().parent.parent


class FakeXInput:
    def read(self, slot):
        return None

    def find_connected(self):
        return None


def make_root():
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    shutil.copytree(FIXTURES / "profiles", root / "profiles")
    shutil.copy(FIXTURES / "config.toml", root / "config.toml")
    return tmp, root


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self._tmp, self.root = make_root()
        self.rt = Runtime(self.root, xinput=FakeXInput(), backend=Recorder(), echo=False)

    def tearDown(self):
        self._tmp.cleanup()

    def read(self, name):
        with open(self.root / "profiles" / f"{name}.toml", "rb") as f:
            return tomllib.load(f)

    def test_save_profile_writes_file_and_applies(self):
        raw = dict(self.rt.raws["desktop"])
        raw["sticks"] = {**raw["sticks"], "left": {**raw["sticks"]["left"], "speed": 900}}
        self.rt.save_profile("desktop", raw)
        self.assertEqual(self.read("desktop")["sticks"]["left"]["speed"], 900)
        self.assertEqual(self.rt.engine.profile.sticks["left"].speed, 900)
        # 書き換える前のファイルは backup/ に残る
        self.assertEqual(len(list((self.root / "backup").glob("desktop.*.toml"))), 1)

    def test_invalid_profile_is_rejected_without_writing(self):
        before = (self.root / "profiles" / "desktop.toml").read_bytes()
        with self.assertRaises(ProfileError):
            self.rt.save_profile("desktop", {"buttons": {"A": "key:nosuchkey"}})
        self.assertEqual((self.root / "profiles" / "desktop.toml").read_bytes(), before)
        self.assertEqual(self.rt.engine.profile.buttons["A"].text, "mouse:left")

    def test_null_values_are_removed(self):
        self.rt.save_profile("emu", {**self.rt.raws["emu"], "description": None})
        self.assertNotIn("description", self.read("emu"))

    def test_create_copy_and_delete(self):
        self.rt.create_profile("ゲーム用", copy_from="emu")
        raw = self.read("ゲーム用")
        self.assertNotIn("match", raw)  # 対象アプリは複製しない
        self.assertEqual(raw["buttons"], self.rt.raws["emu"]["buttons"])
        self.rt.delete_profile("ゲーム用")
        self.assertFalse((self.root / "profiles" / "ゲーム用.toml").exists())
        self.assertNotIn("ゲーム用", self.rt.profiles)

    def test_create_rejects_bad_or_duplicate_names(self):
        for name in ("a/b", "..", "con", "", "x" * 41, "Desktop"):
            with self.subTest(name), self.assertRaises(ProfileError):
                self.rt.create_profile(name)

    def test_delete_protects_default_and_parents(self):
        with self.assertRaises(ProfileError):
            self.rt.delete_profile("desktop")
        with self.assertRaises(ProfileError):
            self.rt.delete_profile("base")  # 他のプロファイルが継承している
        self.assertTrue((self.root / "profiles" / "base.toml").exists())

    def test_match_change_reselects_profile(self):
        self.rt.foreground = r"C:\Tools\notepad.exe"
        self.rt.engine.set_foreground(self.rt.foreground)
        self.assertEqual(self.rt.engine.profile.name, "desktop")
        self.rt.save_profile("emu", {**self.rt.raws["emu"], "match": ["notepad.exe"]})
        self.assertEqual(self.rt.engine.profile.name, "emu")

    def test_save_config(self):
        self.rt.save_config({**self.rt.config_raw, "toggle_hold": 2.0})
        self.assertEqual(self.rt.config.toggle_hold, 2.0)
        with open(self.root / "config.toml", "rb") as f:
            self.assertEqual(tomllib.load(f)["toggle_hold"], 2.0)
        with self.assertRaises(ProfileError):
            self.rt.save_config({"default_profile": "nope"})

    def test_settings_window_suspends_and_keeps_profile(self):
        self.rt._on_focus(Window(1, r"C:\Games\emu\emu.exe", "emu", 100))
        self.assertEqual((self.rt.engine.profile.name, self.rt.engine.suspended), ("emu", False))
        edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        for title in ("padmapper 設定", "padmapper 設定 - 個人 - Microsoft Edge"):
            self.rt._on_focus(Window(2, edge, title, 200))
            self.assertEqual((self.rt.engine.profile.name, self.rt.engine.suspended), ("emu", True))
            self.assertTrue(self.rt.snapshot()["suspended"])
        self.rt._on_focus(Window(3, sys.executable, "", os.getpid()))  # トレイのメニュー
        self.assertTrue(self.rt.engine.suspended)
        uiwindow._launched_pids.add(300)  # 設定画面用に起動したブラウザ (読み込み中でタイトルが違う)
        try:
            self.rt._on_focus(Window(5, edge, "127.0.0.1_/", 300))
            self.assertTrue(self.rt.engine.suspended)
        finally:
            uiwindow._launched_pids.discard(300)
        self.rt._on_focus(Window(4, edge, "ニュース - Microsoft Edge", 200))
        self.assertEqual((self.rt.engine.profile.name, self.rt.engine.suspended), ("desktop", False))

    def test_manual_and_enabled(self):
        self.rt.set_manual("emu")
        self.assertEqual(self.rt.snapshot()["manual"], "emu")
        self.rt.set_manual(None)
        self.assertIsNone(self.rt.snapshot()["manual"])
        self.rt.set_enabled(False)
        self.assertFalse(self.rt.snapshot()["enabled"])


class FirstRunTest(unittest.TestCase):
    def test_examples_are_installed_once(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "profiles").mkdir()
            shutil.copy(REPO / "profiles" / "base.toml", root / "profiles" / "base.toml")
            install_examples(root, REPO / "examples")
            # 追跡している base.toml とサンプルだけで起動できる
            rt = Runtime(root, xinput=FakeXInput(), backend=Recorder(), echo=False)
            self.assertEqual(sorted(rt.profiles), ["base", "desktop", "passthrough"])
            # 2 回目以降 (全体設定がある) は、変更したファイルを上書きしない
            (root / "profiles" / "desktop.toml").write_text('inherit = "base"\n', encoding="utf-8")
            (root / "profiles" / "passthrough.toml").unlink()
            install_examples(root, REPO / "examples")
            self.assertEqual((root / "profiles" / "desktop.toml").read_text(encoding="utf-8"), 'inherit = "base"\n')
            self.assertFalse((root / "profiles" / "passthrough.toml").exists())


class ServerTest(unittest.TestCase):
    def setUp(self):
        self._tmp, self.root = make_root()
        self.rt = Runtime(self.root, xinput=FakeXInput(), backend=Recorder(), echo=False)
        self.server = Server(self.rt)
        self.server.start()

    def tearDown(self):
        self.server.stop()
        self._tmp.cleanup()

    def request(self, method, path, body=None, token=True, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=5)
        h = {"Content-Type": "application/json"}
        if token:
            h["X-Token"] = self.server.token
        h.update(headers or {})
        conn.request(method, path, None if body is None else json.dumps(body), h)
        res = conn.getresponse()
        data = res.read()
        conn.close()
        return res.status, data

    def test_static_page_and_security_headers(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=5)
        conn.request("GET", "/")
        res = conn.getresponse()
        self.assertEqual(res.status, 200)
        self.assertIn("default-src 'self'", res.getheader("Content-Security-Policy"))
        res.read()
        conn.close()

    def test_api_requires_token(self):
        self.assertEqual(self.request("GET", "/api/state", token=False)[0], 403)
        self.assertEqual(self.request("GET", "/api/state", headers={"X-Token": "wrong"})[0], 403)
        self.assertEqual(self.request("GET", "/api/state")[0], 200)

    def test_rejects_foreign_host_and_origin(self):
        self.assertEqual(self.request("GET", "/api/state", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.request("GET", "/", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.request("POST", "/api/enabled", {"enabled": False}, headers={"Origin": "http://evil.example"})[0], 403)
        self.assertTrue(self.rt.engine.enabled)

    def test_rejects_non_json_writes(self):
        status, _ = self.request("POST", "/api/enabled", {"enabled": False}, headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        self.assertTrue(self.rt.engine.enabled)

    def test_profile_round_trip_through_api(self):
        status, data = self.request("GET", "/api/profiles")
        self.assertEqual(status, 200)
        payload = json.loads(data)
        raw = payload["profiles"]["emu"]["raw"]
        raw["sticks"]["right"]["speed"] = 650
        status, _ = self.request("PUT", "/api/profiles/emu", {"raw": raw})
        self.assertEqual(status, 200)
        self.assertEqual(self.rt.profiles["emu"].sticks["right"].speed, 650)

        status, data = self.request("PUT", "/api/profiles/emu", {"raw": {"buttons": {"Q": "key:a"}}})
        self.assertEqual(status, 400)
        self.assertIn("不明なボタン", json.loads(data)["error"])

        status, _ = self.request("POST", "/api/profiles", {"name": "新規", "copy_from": None})
        self.assertEqual(status, 200)
        status, _ = self.request("DELETE", "/api/profiles/%E6%96%B0%E8%A6%8F")
        self.assertEqual(status, 200)
        self.assertNotIn("新規", self.rt.profiles)


if __name__ == "__main__":
    unittest.main()

"""入力処理のループと、設定画面から操作するための共有状態。

入力処理のスレッドと設定画面 (HTTP サーバー) のスレッドは、lock で Engine と設定を共有する。
"""

import collections
import copy
import os
import re
import shutil
import threading
import time
import traceback
from pathlib import Path

from .engine import Engine
from .foreground import foreground_window
from .keys import ALIASES, VK, VK_NAMES
from .output import DryRunBackend, Output, WinBackend
from .profiles import (
    DEFAULT_CONFIG,
    DEFAULT_SETTINGS,
    DEFAULT_STICK,
    MOUSE_BUTTONS,
    STICK_MODES,
    WHEEL_DIRECTIONS,
    ProfileError,
    build_config,
    build_profiles,
    load_raw_config,
    load_raw_profiles,
    resolve_raw,
)
from .tomlwriter import dumps, dumps_profile
from .uiwindow import is_ui_window
from .xinput import ALL_BUTTONS, XInput

RECONNECT_INTERVAL = 1.0
MAX_DT = 0.05  # 処理が止まった後にカーソルが飛ばないよう、1 周期の経過時間に上限を設ける
NAME_PATTERN = re.compile(r"^[\w-]{1,40}$")
RESERVED_NAMES = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(10)} | {f"lpt{i}" for i in range(10)}

SCHEMA = {
    "buttons": list(ALL_BUTTONS),
    "keys": VK,
    "key_names": {str(vk): name for vk, name in VK_NAMES.items()},
    "aliases": ALIASES,
    "mouse_buttons": list(MOUSE_BUTTONS),
    "wheel_directions": list(WHEEL_DIRECTIONS),
    "stick_modes": list(STICK_MODES),
    "stick_defaults": DEFAULT_STICK,
    "settings_defaults": DEFAULT_SETTINGS,
    "config_defaults": DEFAULT_CONFIG,
}


def _strip_none(value):
    """JSON の null は「項目を消す」として扱う。"""
    if isinstance(value, dict):
        return {k: _strip_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_strip_none(v) for v in value if v is not None]
    return value


def _check_name(name):
    if not isinstance(name, str) or not NAME_PATTERN.match(name) or name.lower() in RESERVED_NAMES:
        raise ProfileError("名前には文字・数字・_・- だけを使えます (40 文字まで)")


class Runtime:
    def __init__(self, root, dry_run=False, fixed_profile=None, xinput=None, backend=None, log_path=None, echo=True):
        self.root = Path(root)
        self.profiles_dir = self.root / "profiles"
        self.config_path = self.root / "config.toml"
        self.backup_dir = self.root / "backup"
        self.ui_profile_dir = self.root / "ui-profile"  # 設定画面のウィンドウ用のブラウザプロファイル
        self.lock = threading.RLock()
        self.logs = collections.deque(maxlen=300)
        self._echo = echo
        self._log_file = None
        if log_path:
            Path(log_path).parent.mkdir(exist_ok=True)
            self._log_file = open(log_path, "w", encoding="utf-8")

        self.raws = load_raw_profiles(self.profiles_dir)
        self.profiles = build_profiles(self.raws)
        self.config_raw = load_raw_config(self.config_path)
        self.config = build_config(self.config_raw, self.profiles, self.config_path.name)
        if fixed_profile is not None and fixed_profile not in self.profiles:
            raise ProfileError(f"プロファイル '{fixed_profile}' がありません")

        if backend is None:
            backend = DryRunBackend(self.log) if dry_run else WinBackend(self.config.mouse_mode, self.log)
        self.backend = backend
        self.engine = Engine(self.profiles, self.config, Output(backend), self.log)
        if fixed_profile:
            self.engine.set_manual(fixed_profile)
        self.xinput = xinput or XInput()
        self.foreground = None
        self.state = None  # 最後に読んだ PadState
        self._backed_up = set()
        self._stop = threading.Event()
        self._thread = None

    def log(self, message):
        line = f"{time.strftime('%H:%M:%S')} {message}"
        self.logs.append(line)
        if self._echo:
            print(line, flush=True)
        if self._log_file:
            self._log_file.write(line + "\n")
            self._log_file.flush()

    # 入力処理のループ

    def start(self):
        self._thread = threading.Thread(target=self.run_loop, name="padmapper-input", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def run_loop(self):
        slot = None
        connected = False
        next_reconnect = next_focus = 0.0
        last = next_tick = time.perf_counter()
        try:
            while not self._stop.is_set():
                now = time.perf_counter()
                dt = min(now - last, MAX_DT)
                last = now
                config = self.config

                window = None
                check_focus = now >= next_focus
                if check_focus:
                    next_focus = now + config.focus_interval
                    window = foreground_window()

                # 未接続のスロットの読み取りは遅いことがあるので、再接続の確認は間隔を空ける
                state = None
                if connected or now >= next_reconnect:
                    if not connected:
                        slot = self.xinput.find_connected() if config.pad < 0 else config.pad
                    state = self.xinput.read(slot) if slot is not None else None
                    connected = state is not None
                    if not connected:
                        next_reconnect = now + RECONNECT_INTERVAL

                with self.lock:
                    try:
                        if window and window.path:
                            self._on_focus(window)
                        self.state = state
                        self.engine.update(state, now, dt)
                    except Exception:
                        self.log("内部エラーのため変換を無効にしました\n" + traceback.format_exc())
                        self.engine.set_enabled(False)

                next_tick += 1 / config.poll_hz
                delay = next_tick - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_tick = time.perf_counter()
        finally:
            with self.lock:
                self.engine.release_all()

    def _on_focus(self, window):
        # 設定画面 (とトレイのメニュー) が前面にある間は変換を止める。
        # プロファイルは直前のアプリのものを保ち、設定画面にどのプロファイルが使われていたかを表示できるようにする
        own = is_ui_window(window) or window.pid == os.getpid()
        self.engine.set_suspended(own)
        if not own:
            self.foreground = window.path
            self.engine.set_foreground(window.path)

    # 設定画面向けの状態

    def snapshot(self):
        with self.lock:
            s = self.state
            return {
                "connected": s is not None,
                "enabled": self.engine.enabled,
                "suspended": self.engine.suspended,
                "profile": self.engine.profile.name,
                "manual": self.engine.manual_name,
                "foreground": self.foreground,
                "layers": self.engine.active_layers,
                "pressed": sorted(self.engine.pressed),
                "axes": None
                if s is None
                else {"lt": s.lt, "rt": s.rt, "lx": s.lx, "ly": s.ly, "rx": s.rx, "ry": s.ry},
            }

    def profiles_payload(self):
        with self.lock:
            return {
                "profiles": {
                    name: {"raw": raw, "merged": resolve_raw(name, self.raws)} for name, raw in self.raws.items()
                },
                "config": {**DEFAULT_CONFIG, **self.config_raw},
                "schema": SCHEMA,
            }

    def set_enabled(self, enabled):
        with self.lock:
            self.engine.set_enabled(bool(enabled))

    def set_manual(self, name):
        with self.lock:
            if name is not None and name not in self.profiles:
                raise ProfileError(f"プロファイル '{name}' がありません")
            self.engine.set_manual(name)

    # 設定の変更 (検証してから書き込み、反映する)

    def save_profile(self, name, raw):
        if not isinstance(raw, dict):
            raise ProfileError("プロファイルの内容が不正です")
        raw = _strip_none(raw)
        with self.lock:
            if name not in self.raws:
                raise ProfileError(f"プロファイル '{name}' がありません")
            raws = {**self.raws, name: raw}
            profiles, config = self._validate(raws, self.config_raw)
            self._write(self.profiles_dir / f"{name}.toml", dumps_profile(raw))
            self._commit(raws, profiles, self.config_raw, config)

    def create_profile(self, name, copy_from=None):
        with self.lock:
            _check_name(name)
            if any(n.lower() == name.lower() for n in self.raws):
                raise ProfileError(f"プロファイル '{name}' は既にあります")
            if copy_from:
                if copy_from not in self.raws:
                    raise ProfileError(f"プロファイル '{copy_from}' がありません")
                raw = copy.deepcopy(self.raws[copy_from])
                raw.pop("match", None)  # 同じアプリに 2 つのプロファイルが当たらないように対象アプリは引き継がない
                raw["description"] = f"{copy_from} のコピー"
            else:
                raw = {"inherit": "base"} if "base" in self.raws else {}
            raws = {**self.raws, name: raw}
            profiles, config = self._validate(raws, self.config_raw)
            self._write(self.profiles_dir / f"{name}.toml", dumps_profile(raw))
            self._commit(raws, profiles, self.config_raw, config)

    def delete_profile(self, name):
        with self.lock:
            if name not in self.raws:
                raise ProfileError(f"プロファイル '{name}' がありません")
            if name == self.config.default_profile:
                raise ProfileError("既定のプロファイルは削除できません。全体設定で既定を変えてから削除してください")
            raws = {k: v for k, v in self.raws.items() if k != name}
            try:
                profiles, config = self._validate(raws, self.config_raw)
            except ProfileError as e:
                raise ProfileError(f"他のプロファイルから使われているため削除できません: {e}") from None
            path = self.profiles_dir / f"{name}.toml"
            self._backup(path)
            path.unlink()
            self._commit(raws, profiles, self.config_raw, config)

    def save_config(self, raw):
        if not isinstance(raw, dict):
            raise ProfileError("全体設定の内容が不正です")
        raw = _strip_none(raw)
        with self.lock:
            profiles, config = self._validate(self.raws, raw)
            self._write(self.config_path, dumps(raw))
            self._commit(self.raws, profiles, raw, config)

    def _validate(self, raws, config_raw):
        profiles = build_profiles(raws)
        return profiles, build_config(config_raw, profiles, self.config_path.name)

    def _commit(self, raws, profiles, config_raw, config):
        self.raws, self.profiles, self.config_raw, self.config = raws, profiles, config_raw, config
        self.engine.replace(profiles, config)
        if self.foreground:
            self.engine.set_foreground(self.foreground)  # 対象アプリの変更を反映して選び直す
        if isinstance(self.backend, WinBackend):
            self.backend.mouse_mode = config.mouse_mode

    def _backup(self, path):
        """起動後に初めて書き換えるファイルを backup/ に残す。"""
        if path in self._backed_up or not path.exists():
            return
        self.backup_dir.mkdir(exist_ok=True)
        shutil.copy2(path, self.backup_dir / f"{path.stem}.{time.strftime('%Y%m%d-%H%M%S')}{path.suffix}")
        self._backed_up.add(path)

    def _write(self, path, text):
        self._backup(path)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)

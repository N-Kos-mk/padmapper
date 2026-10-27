"""padmapper の起動。

    pythonw -m padmapper --tray           タスクトレイに常駐する (padmapper.pyw と同じ)
    python -m padmapper                   コンソールで起動する (Ctrl+C で終了)
    python -m padmapper --check           設定を検証して一覧を表示する (入力は送らない)
    python -m padmapper --dry-run         入力を送らず、送る予定の内容を表示する
    python -m padmapper --profile NAME    NAME に固定して起動する
"""

import argparse
import ctypes
import shutil
import sys
import traceback
from ctypes import wintypes
from pathlib import Path

from . import tray, uiwindow
from .profiles import ProfileError, load_config, load_profiles
from .runtime import Runtime
from .server import WEB_DIR, Server

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "logs" / "padmapper.log"
EXAMPLES_DIR = ROOT / "examples"
CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT = 2, 5, 6


def install_examples(root, examples=EXAMPLES_DIR):
    """初回起動 (全体設定がまだない) のときに、サンプルの全体設定とプロファイルを用意する。既にあるファイルは変更しない。"""
    config = root / "config.toml"
    if config.exists():
        return
    profiles = root / "profiles"
    profiles.mkdir(exist_ok=True)
    for src in sorted((examples / "profiles").glob("*.toml")):
        if not (profiles / src.name).exists():
            shutil.copyfile(src, profiles / src.name)
    shutil.copyfile(examples / "config.toml", config)


def set_dpi_aware():
    """高 DPI 環境でもカーソルを 1 ピクセル単位で動かせるようにする (このプロセスだけに影響)。"""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        pass


def install_close_handler(callback):
    """コンソールを閉じたときやログオフ時にも、押しっぱなしの入力を離す。"""
    handler_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    def handler(event):
        if event in (CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT):
            callback()
        return False

    fn = handler_type(handler)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(fn, True)
    return fn  # 参照を保持しないとコールバックが解放される


def _stick_text(stick):
    return f"{stick.mode} (speed {stick.speed:g}{', axis_lock' if stick.axis_lock else ''})"


def print_summary(profiles, config):
    print(f"既定のプロファイル: {config.default_profile}")
    print(f"有効/無効の切り替え: {' + '.join(config.toggle_combo)} を {config.toggle_hold:g} 秒長押し")
    print()
    for name, profile in profiles.items():
        print(f"[{name}] {profile.description}")
        if profile.match:
            print(f"  match: {', '.join(profile.match)}")
        for side, stick in profile.sticks.items():
            if stick.mode != "none":
                print(f"  {side} stick: {_stick_text(stick)}")
        for button, binding in profile.buttons.items():
            if binding is not None:
                print(f"  {button:8} {binding.text}{' (repeat)' if binding.repeat else ''}")
        for lname, layer in profile.layers.items():
            print(f"  layer {lname}:")
            for side, stick in layer.sticks.items():
                print(f"    {side} stick: {_stick_text(stick)}")
            for button, binding in layer.buttons.items():
                if binding is not None:
                    print(f"    {button:8} {binding.text}{' (repeat)' if binding.repeat else ''}")


def run_console(args):
    runtime = Runtime(ROOT, dry_run=args.dry_run, fixed_profile=args.profile)
    server = Server(runtime)
    server.start()
    close_handler = install_close_handler(runtime.stop)  # noqa: F841
    runtime.log(f"起動しました (プロファイル: {runtime.engine.profile.name}{', dry-run' if args.dry_run else ''})")
    combo = " + ".join(runtime.config.toggle_combo)
    runtime.log(f"{combo} を {runtime.config.toggle_hold:g} 秒長押しで変換の有効/無効、Ctrl+C で終了")
    runtime.log(f"設定画面: {server.url}")
    if args.open:
        uiwindow.open_ui(server.url, runtime.ui_profile_dir, runtime.log)
    try:
        runtime.run_loop()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        runtime.log("終了しました")


def run_tray(args):
    runtime = Runtime(ROOT, dry_run=args.dry_run, fixed_profile=args.profile, log_path=LOG_PATH, echo=False)
    server = Server(runtime)
    server.start()
    runtime.start()
    runtime.log(f"起動しました (プロファイル: {runtime.engine.profile.name}{', dry-run' if args.dry_run else ''})")
    uiwindow.close_ui()  # 前回の起動で開いたままの設定画面は、接続先が変わって使えないので閉じる
    try:
        icon = tray.Tray(runtime, server.url, WEB_DIR / "icon.ico", WEB_DIR / "icon-off.ico")
        if args.open:
            icon.open_ui()
        icon.run()
    finally:
        runtime.stop()
        server.stop()
        runtime.log("終了しました")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="padmapper", description="XInput コントローラーをキーボード・マウス操作に変換する")
    parser.add_argument("--tray", action="store_true", help="タスクトレイに常駐する")
    parser.add_argument("--open", action="store_true", help="起動と同時に設定画面を開く")
    parser.add_argument("--check", action="store_true", help="設定を検証して一覧を表示する")
    parser.add_argument("--dry-run", action="store_true", help="入力を送らず、送る予定の内容を表示する")
    parser.add_argument("--profile", help="このプロファイルに固定して起動する")
    args = parser.parse_args(argv)
    install_examples(ROOT)

    if args.check:
        try:
            profiles = load_profiles(ROOT / "profiles")
            print_summary(profiles, load_config(ROOT / "config.toml", profiles))
        except ProfileError as e:
            print(f"設定エラー: {e}", file=sys.stderr)
            return 1
        return 0

    # 2 つ同時に動くと入力が二重に送られるので、多重起動を防ぐ
    report = tray.show_error if args.tray else (lambda message: print(message, file=sys.stderr))
    mutex = tray.acquire_single_instance()  # noqa: F841 (終了まで保持する)
    if mutex is None:
        if tray.notify_running_instance():
            if not args.tray:
                print("padmapper はトレイで起動中のため、その設定画面を開きました", file=sys.stderr)
            return 0
        report("padmapper は既に起動しています")
        return 1

    set_dpi_aware()
    try:
        if args.tray:
            run_tray(args)
        else:
            run_console(args)
    except ProfileError as e:
        report(f"設定エラー: {e}")
        return 1
    except Exception:
        if not args.tray:
            raise
        tray.show_error("予期しないエラーで終了しました\n\n" + traceback.format_exc())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

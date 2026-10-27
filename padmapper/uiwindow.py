"""設定画面を、タブやアドレスバーのない独立したウィンドウで開く。

Windows に標準で入っている Edge (なければ Chrome) のアプリモード (--app) を使う。
専用のブラウザプロファイル (ui-profile/) で起動し、普段使いのブラウザの履歴や設定とは分ける。
"""

import os
import subprocess
import webbrowser
from pathlib import Path

from .foreground import bring_to_front, close_window, top_level_windows

UI_TITLE = "padmapper 設定"  # web/index.html の <title> と同じにする
WINDOW_SIZE = "1280,860"


def _candidates():
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    return [
        Path(program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
        Path(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
        Path(program_files, "Google", "Chrome", "Application", "chrome.exe"),
        Path(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
        Path(local, "Google", "Chrome", "Application", "chrome.exe"),
    ]


def find_browser():
    return next((p for p in _candidates() if p.is_file()), None)


# 設定画面用に起動したブラウザのプロセス。ui-profile 専用のプロセスなので、そのウィンドウはすべて設定画面
# (読み込み中はタイトルが "127.0.0.1_/" などになるため、タイトルだけでは判定できない)
_launched_pids = set()


def is_ui_window(window):
    """設定画面か。通常のブラウザのタブで開いた場合 ("padmapper 設定 - Microsoft Edge" など) も含む。"""
    return window.pid in _launched_pids or (bool(window.title) and window.title.startswith(UI_TITLE))


def ui_windows():
    """設定画面専用のウィンドウ。通常のブラウザのウィンドウは、閉じると他のタブまで閉じてしまうので含めない
    (タイトルにブラウザ名が付くので区別できる)。"""
    return [w for w in top_level_windows() if w.pid in _launched_pids or w.title == UI_TITLE]


def open_ui(url, profile_dir, log=print):
    """設定画面を開く。既に開いていれば、そのウィンドウを前面に出す。"""
    windows = ui_windows()
    if windows:
        bring_to_front(windows[0].hwnd)
        return
    browser = find_browser()
    if browser is None:
        log("Edge / Chrome が見つからないため、既定のブラウザで設定画面を開きます")
        webbrowser.open(url)
        return
    proc = subprocess.Popen(
        [
            str(browser),
            f"--app={url}",
            f"--user-data-dir={profile_dir}",
            f"--window-size={WINDOW_SIZE}",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _launched_pids.add(proc.pid)


def close_ui():
    """開いている設定画面を閉じる (padmapper の終了時や、前回の起動で開いたままの画面)。"""
    for w in ui_windows():
        close_window(w.hwnd)

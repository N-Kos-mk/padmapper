"""前面にあるウィンドウの実行ファイルやタイトルを調べる。"""

import ctypes
from ctypes import wintypes
from typing import NamedTuple

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GW_OWNER = 4
SW_RESTORE = 9
WM_CLOSE = 0x0010

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetWindow.restype = wintypes.HWND
_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

_cache = {}  # pid -> 実行ファイルのパス


class Window(NamedTuple):
    hwnd: int
    path: str  # 実行ファイルのパス。取得できなければ None
    title: str
    pid: int


def _process_path(pid):
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return None
        return buf.value
    finally:
        _kernel32.CloseHandle(handle)


def _cached_path(pid):
    if pid not in _cache:
        if len(_cache) > 256:
            _cache.clear()
        _cache[pid] = _process_path(pid)
    return _cache[pid]


def _title(hwnd):
    length = _user32.GetWindowTextLengthW(hwnd)
    if not length:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _pid(hwnd):
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def foreground_window():
    """前面のウィンドウ。取得できなければ None。"""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = _pid(hwnd)
    if not pid:
        return None
    return Window(hwnd, _cached_path(pid), _title(hwnd), pid)


def top_level_windows():
    """タスクバーに出るような、表示中でタイトルのあるウィンドウの一覧。"""
    handles = []

    def visit(hwnd, _):
        if _user32.IsWindowVisible(hwnd) and not _user32.GetWindow(hwnd, GW_OWNER):
            handles.append(hwnd)
        return True

    _user32.EnumWindows(_WNDENUMPROC(visit), 0)
    windows = []
    for hwnd in handles:
        title = _title(hwnd)
        if title:
            pid = _pid(hwnd)
            windows.append(Window(hwnd, _process_path(pid), title, pid))
    return windows


def running_apps():
    """ウィンドウを表示しているアプリの一覧。[{"path": 実行ファイル, "title": ウィンドウ名}]"""
    apps = {}
    for w in top_level_windows():
        if w.path and w.path not in apps:
            apps[w.path] = w.title
    return [{"path": path, "title": title} for path, title in sorted(apps.items(), key=lambda a: a[0].lower())]


def bring_to_front(hwnd):
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, SW_RESTORE)
    _user32.SetForegroundWindow(hwnd)


def close_window(hwnd):
    _user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

"""通知領域 (タスクトレイ) のアイコン。追加ライブラリなしで、Win32 API を ctypes で直接呼ぶ。

左クリックで設定画面を開き、右クリックでメニュー (有効/無効、プロファイルの固定、終了) を出す。
"""

import ctypes
import traceback
from ctypes import wintypes

from . import uiwindow

LRESULT = ctypes.c_ssize_t
UINT_PTR = ctypes.c_size_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

CLASS_NAME = "padmapper_tray"
MUTEX_NAME = "Local\\padmapper"
ERROR_ALREADY_EXISTS = 183

WM_DESTROY = 0x0002
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
WM_NULL = 0x0000
WM_TIMER = 0x0113
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_APP = 0x8000
WM_TRAY = WM_APP + 1  # アイコンへのマウス操作
WM_OPEN_UI = WM_APP + 2  # 2 つ目の起動から、起動中のものに設定画面を開かせる

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x1, 0x2, 0x4
MF_STRING, MF_CHECKED, MF_POPUP, MF_SEPARATOR = 0x0, 0x8, 0x10, 0x800
TPM_RIGHTBUTTON, TPM_NONOTIFY, TPM_RETURNCMD = 0x2, 0x80, 0x100
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x10
SM_CXSMICON, SM_CYSMICON = 49, 50
MB_ICONERROR = 0x10
TIMER_ID = 1
TIMER_MS = 300

ID_OPEN, ID_TOGGLE, ID_AUTO, ID_QUIT = 1, 2, 3, 4
ID_PROFILE_BASE = 100


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
user32.RegisterWindowMessageW.restype = wintypes.UINT
user32.LoadImageW.argtypes = [
    wintypes.HINSTANCE,
    wintypes.LPCWSTR,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.LoadImageW.restype = wintypes.HANDLE
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, UINT_PTR, wintypes.LPCWSTR]
user32.SetMenuDefaultItem.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.LPVOID,
]
user32.TrackPopupMenu.restype = wintypes.BOOL
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.SetTimer.argtypes = [wintypes.HWND, UINT_PTR, wintypes.UINT, wintypes.LPVOID]
user32.SetTimer.restype = UINT_PTR
user32.KillTimer.argtypes = [wintypes.HWND, UINT_PTR]
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE


def acquire_single_instance():
    """多重起動を防ぐ。既に起動していれば None、そうでなければ (保持し続ける) ミューテックスを返す。"""
    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return None
    return handle


def notify_running_instance():
    """起動中のトレイに設定画面を開かせる。トレイが見つからなければ False。"""
    hwnd = user32.FindWindowW(CLASS_NAME, None)
    if not hwnd:
        return False
    user32.PostMessageW(hwnd, WM_OPEN_UI, 0, 0)
    return True


def show_error(message):
    user32.MessageBoxW(None, message, "padmapper", MB_ICONERROR)


class Tray:
    def __init__(self, runtime, url, icon_path, icon_off_path):
        self.runtime = runtime
        self.url = url
        # CreateWindowExW の途中から _proc が呼ばれるので、そこで使う値を先に用意する
        self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self._shown = None
        self._wndproc = WNDPROC(self._proc)  # 参照を保持しないとコールバックが解放される
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW(lpfnWndProc=self._wndproc, hInstance=hinst, lpszClassName=CLASS_NAME)
        if not user32.RegisterClassW(ctypes.byref(wc)):
            raise ctypes.WinError(ctypes.get_last_error())
        # 表示しないトップレベルウィンドウ。ログオフ通知やエクスプローラー再起動の通知を受け取るため
        self.hwnd = user32.CreateWindowExW(0, CLASS_NAME, "padmapper", 0, 0, 0, 0, 0, None, None, hinst, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        cx, cy = user32.GetSystemMetrics(SM_CXSMICON), user32.GetSystemMetrics(SM_CYSMICON)
        self.icons = {
            True: user32.LoadImageW(None, str(icon_path), IMAGE_ICON, cx, cy, LR_LOADFROMFILE),
            False: user32.LoadImageW(None, str(icon_off_path), IMAGE_ICON, cx, cy, LR_LOADFROMFILE),
        }
        self._notify(NIM_ADD)
        user32.SetTimer(self.hwnd, TIMER_ID, TIMER_MS, None)

    def run(self):
        """メッセージループ。終了が選ばれるまで戻らない。"""
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            for icon in self.icons.values():
                if icon:
                    user32.DestroyIcon(icon)

    def open_ui(self):
        uiwindow.open_ui(self.url, self.runtime.ui_profile_dir, self.runtime.log)

    def quit(self):
        uiwindow.close_ui()
        user32.DestroyWindow(self.hwnd)

    # アイコンの表示

    def _status(self):
        with self.runtime.lock:
            engine = self.runtime.engine
            tip = f"padmapper: {engine.profile.name}"
            if engine.manual_name:
                tip += " (固定)"
            if not engine.enabled:
                tip += " - 無効"
            return engine.enabled, tip

    def _notify(self, action):
        enabled, tip = self._status()
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self.icons[enabled]
        nid.szTip = tip[:127]
        shell32.Shell_NotifyIconW(action, ctypes.byref(nid))
        self._shown = (enabled, tip)

    def _remove(self):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))

    # メニュー

    def _menu(self):
        with self.runtime.lock:
            enabled = self.runtime.engine.enabled
            manual = self.runtime.engine.manual_name
            names = sorted(self.runtime.profiles)
        menu = user32.CreatePopupMenu()
        sub = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, ID_OPEN, "設定画面を開く")
        user32.SetMenuDefaultItem(menu, ID_OPEN, False)
        user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if enabled else 0), ID_TOGGLE, "変換を有効にする")
        user32.AppendMenuW(sub, MF_STRING | (MF_CHECKED if manual is None else 0), ID_AUTO, "自動 (前面のアプリに合わせる)")
        user32.AppendMenuW(sub, MF_SEPARATOR, 0, None)
        for i, name in enumerate(names):
            user32.AppendMenuW(sub, MF_STRING | (MF_CHECKED if manual == name else 0), ID_PROFILE_BASE + i, name)
        user32.AppendMenuW(menu, MF_POPUP, sub, "プロファイルを固定")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, ID_QUIT, "終了")

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)  # これがないとメニュー外をクリックしても閉じない
        cmd = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_NONOTIFY | TPM_RETURNCMD, pt.x, pt.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)  # サブメニューも一緒に破棄される

        if cmd == ID_OPEN:
            self.open_ui()
        elif cmd == ID_TOGGLE:
            self.runtime.set_enabled(not enabled)
        elif cmd == ID_AUTO:
            self.runtime.set_manual(None)
        elif cmd >= ID_PROFILE_BASE and cmd - ID_PROFILE_BASE < len(names):
            self.runtime.set_manual(names[cmd - ID_PROFILE_BASE])
        elif cmd == ID_QUIT:
            self.quit()
        self._refresh()

    def _refresh(self):
        if self._status() != self._shown:
            self._notify(NIM_MODIFY)

    # ウィンドウプロシージャ

    def _proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAY:
                event = lparam & 0xFFFF
                if event == WM_LBUTTONUP:
                    self.open_ui()
                elif event == WM_RBUTTONUP:
                    self._menu()
                return 0
            if msg == WM_OPEN_UI:
                self.open_ui()
                return 0
            if msg == WM_TIMER:
                self._refresh()
                return 0
            if self._taskbar_created and msg == self._taskbar_created:
                # エクスプローラーが再起動するとアイコンが消えるので追加し直す
                self._notify(NIM_ADD)
                return 0
            if msg == WM_QUERYENDSESSION:
                return 1
            if msg == WM_ENDSESSION and wparam:
                self.runtime.stop()  # ログオフ・シャットダウン時も押しっぱなしの入力を離す
                return 0
            if msg == WM_DESTROY:
                user32.KillTimer(hwnd, TIMER_ID)
                self._remove()
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            self.runtime.log("トレイの処理でエラーが発生しました\n" + traceback.format_exc())
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

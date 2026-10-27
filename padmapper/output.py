"""キーボード・マウス入力の送信。

Output は押下を参照カウントで管理し、同じキーを複数のボタンが押していても、
最後の 1 つが離されるまでキーを離さない。実際の送信はバックエンドが行う。
"""

import ctypes
import time
from ctypes import wintypes

from .keys import EXTENDED_VKS, key_name


class Output:
    def __init__(self, backend):
        self.backend = backend
        self._keys = {}  # vk -> 押しているボタンの数
        self._mouse = {}  # ボタン名 -> 押しているボタンの数

    def press_keys(self, vks):
        for vk in vks:
            self._press(self._keys, vk, self.backend.key)

    def release_keys(self, vks):
        for vk in reversed(vks):
            self._release(self._keys, vk, self.backend.key)

    def repeat_key(self, vk):
        self.backend.key(vk, True)

    def press_mouse(self, button):
        self._press(self._mouse, button, self.backend.mouse_button)

    def release_mouse(self, button):
        self._release(self._mouse, button, self.backend.mouse_button)

    def wheel(self, delta, horizontal=False):
        self.backend.wheel(delta, horizontal)

    def move(self, dx, dy):
        self.backend.move(dx, dy)

    def release_all(self):
        for button in reversed(list(self._mouse)):
            self.backend.mouse_button(button, False)
        for vk in reversed(list(self._keys)):
            self.backend.key(vk, False)
        self._mouse.clear()
        self._keys.clear()

    @staticmethod
    def _press(counts, item, send):
        counts[item] = counts.get(item, 0) + 1
        if counts[item] == 1:
            send(item, True)

    @staticmethod
    def _release(counts, item, send):
        count = counts.get(item, 0)
        if count > 1:
            counts[item] = count - 1
        elif count == 1:
            del counts[item]
            send(item, False)


ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
MAPVK_VK_TO_VSC_EX = 4
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
# ボタン名 -> (押す, 離す, mouseData)
MOUSE_BUTTONS = {
    "left": (0x0002, 0x0004, 0),
    "right": (0x0008, 0x0010, 0),
    "middle": (0x0020, 0x0040, 0),
    "x1": (0x0080, 0x0100, 1),
    "x2": (0x0080, 0x0100, 2),
}


class WinBackend:
    """SendInput で実際に入力を送る。"""

    def __init__(self, mouse_mode="cursor", log=print):
        self.mouse_mode = mouse_mode
        self.log = log
        self._warned = False
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        user32.SendInput.restype = wintypes.UINT
        user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
        user32.MapVirtualKeyW.restype = wintypes.UINT
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        self._user32 = user32

    def key(self, vk, down):
        scan = self._user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC_EX)
        flags = 0 if down else KEYEVENTF_KEYUP
        if vk in EXTENDED_VKS or scan & 0xFF00 in (0xE000, 0xE100):
            flags |= KEYEVENTF_EXTENDEDKEY
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.ki = KEYBDINPUT(wVk=vk, wScan=scan & 0xFF, dwFlags=flags)
        self._send(inp)

    def mouse_button(self, button, down):
        press, release, data = MOUSE_BUTTONS[button]
        self._send_mouse(press if down else release, data=data)

    def wheel(self, delta, horizontal):
        # mouseData は DWORD なので負の値は 2 の補数で渡す
        self._send_mouse(MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL, data=delta & 0xFFFFFFFF)

    def move(self, dx, dy):
        if self.mouse_mode == "relative":
            self._send_mouse(MOUSEEVENTF_MOVE, dx, dy)
            return
        pt = wintypes.POINT()
        if self._user32.GetCursorPos(ctypes.byref(pt)):
            self._user32.SetCursorPos(pt.x + dx, pt.y + dy)

    def _send_mouse(self, flags, dx=0, dy=0, data=0):
        inp = INPUT(type=INPUT_MOUSE)
        inp.mi = MOUSEINPUT(dx=dx, dy=dy, mouseData=data, dwFlags=flags)
        self._send(inp)

    def _send(self, inp):
        if self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1 and not self._warned:
            self._warned = True
            self.log(f"警告: SendInput が失敗しました (error {ctypes.get_last_error()})")


class DryRunBackend:
    """入力を送らず、送る予定の内容を表示する。"""

    def __init__(self, log=print):
        self.log = log
        self._move = [0, 0]
        self._last_move_log = 0.0

    def key(self, vk, down):
        self.log(f"[dry-run] key {key_name(vk)} {'down' if down else 'up'}")

    def mouse_button(self, button, down):
        self.log(f"[dry-run] mouse {button} {'down' if down else 'up'}")

    def wheel(self, delta, horizontal):
        self.log(f"[dry-run] wheel {'h' if horizontal else 'v'} {delta:+d}")

    def move(self, dx, dy):
        # 毎周期表示すると流れてしまうので 0.25 秒ごとにまとめる
        self._move[0] += dx
        self._move[1] += dy
        now = time.perf_counter()
        if now - self._last_move_log >= 0.25:
            self.log(f"[dry-run] move {self._move[0]:+d},{self._move[1]:+d}")
            self._move = [0, 0]
            self._last_move_log = now

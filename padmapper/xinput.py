"""XInput からコントローラーの状態を読む。"""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", wintypes.WORD),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", XINPUT_GAMEPAD)]


BUTTON_BITS = {
    "UP": 0x0001,
    "DOWN": 0x0002,
    "LEFT": 0x0004,
    "RIGHT": 0x0008,
    "START": 0x0010,
    "BACK": 0x0020,
    "LS": 0x0040,
    "RS": 0x0080,
    "LB": 0x0100,
    "RB": 0x0200,
    "GUIDE": 0x0400,
    "A": 0x1000,
    "B": 0x2000,
    "X": 0x4000,
    "Y": 0x8000,
}
TRIGGERS = ("LT", "RT")
# スティックを mode = "buttons" にしたときに使える仮想ボタン
STICK_DIRECTIONS = tuple(f"{p}_{d}" for p in ("LS", "RS") for d in ("UP", "DOWN", "LEFT", "RIGHT"))
ALL_BUTTONS = tuple(BUTTON_BITS) + TRIGGERS + STICK_DIRECTIONS

SLOTS = 4
ERROR_SUCCESS = 0


@dataclass(frozen=True)
class PadState:
    buttons: int = 0
    lt: float = 0.0  # 0〜1
    rt: float = 0.0
    lx: float = 0.0  # -1〜1 (右・上が正)
    ly: float = 0.0
    rx: float = 0.0
    ry: float = 0.0


def _axis(value):
    return max(-1.0, value / 32767)


class XInput:
    def __init__(self):
        dll = ctypes.WinDLL("xinput1_4.dll")
        try:
            # 序数 100 は Guide ボタンも取得できる非公開版 XInputGetStateEx
            fn = dll[100]
        except (AttributeError, OSError):
            fn = dll.XInputGetState
        fn.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
        fn.restype = wintypes.DWORD
        self._get_state = fn
        self._state = XINPUT_STATE()

    def read(self, slot):
        """slot の状態を返す。未接続なら None。"""
        if self._get_state(slot, ctypes.byref(self._state)) != ERROR_SUCCESS:
            return None
        pad = self._state.Gamepad
        return PadState(
            buttons=pad.wButtons,
            lt=pad.bLeftTrigger / 255,
            rt=pad.bRightTrigger / 255,
            lx=_axis(pad.sThumbLX),
            ly=_axis(pad.sThumbLY),
            rx=_axis(pad.sThumbRX),
            ry=_axis(pad.sThumbRY),
        )

    def find_connected(self):
        """接続されている最初のスロット番号を返す。なければ None。"""
        for slot in range(SLOTS):
            if self.read(slot) is not None:
                return slot
        return None

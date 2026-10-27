"""XInput コントローラーの入力を読み取って表示するだけのモニター。

標準ライブラリ(ctypes)のみ使用。システム設定やドライバには一切書き込まない。

使い方:
    python tools/xinput_monitor.py          # 押したボタン・スティックの変化を表示 (Ctrl+C で終了)
    python tools/xinput_monitor.py --once   # 接続状況と現在の状態を 1 回だけ表示
"""

import argparse
import ctypes
import time
from ctypes import wintypes


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


BUTTONS = {
    0x0001: "DPAD_UP",
    0x0002: "DPAD_DOWN",
    0x0004: "DPAD_LEFT",
    0x0008: "DPAD_RIGHT",
    0x0010: "START",
    0x0020: "BACK",
    0x0040: "L_STICK_PUSH",
    0x0080: "R_STICK_PUSH",
    0x0100: "LB",
    0x0200: "RB",
    0x0400: "GUIDE",
    0x1000: "A",
    0x2000: "B",
    0x4000: "X",
    0x8000: "Y",
}

ERROR_SUCCESS = 0
STICK_DEADZONE = 8000
TRIGGER_THRESHOLD = 30


def load_get_state():
    dll = ctypes.WinDLL("xinput1_4.dll")
    try:
        # 序数 100 は Guide ボタンも取得できる非公開版 XInputGetStateEx
        fn = dll[100]
    except (AttributeError, OSError):
        fn = dll.XInputGetState
    fn.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
    fn.restype = wintypes.DWORD
    return fn


def pressed_names(buttons):
    return [name for bit, name in BUTTONS.items() if buttons & bit]


def stick_dir(x, y):
    dirs = []
    if y > STICK_DEADZONE:
        dirs.append("上")
    elif y < -STICK_DEADZONE:
        dirs.append("下")
    if x < -STICK_DEADZONE:
        dirs.append("左")
    elif x > STICK_DEADZONE:
        dirs.append("右")
    return "".join(dirs) or "中央"


def describe(pad):
    parts = [
        "buttons=" + (",".join(pressed_names(pad.wButtons)) or "-"),
        f"LT={pad.bLeftTrigger:3d}",
        f"RT={pad.bRightTrigger:3d}",
        f"L=({pad.sThumbLX:6d},{pad.sThumbLY:6d}){stick_dir(pad.sThumbLX, pad.sThumbLY)}",
        f"R=({pad.sThumbRX:6d},{pad.sThumbRY:6d}){stick_dir(pad.sThumbRX, pad.sThumbRY)}",
    ]
    return "  ".join(parts)


def snapshot(pad):
    """表示を変えるべき変化だけを比較するための要約。スティックの微小なぶれは無視する。"""
    return (
        pad.wButtons,
        pad.bLeftTrigger > TRIGGER_THRESHOLD,
        pad.bRightTrigger > TRIGGER_THRESHOLD,
        stick_dir(pad.sThumbLX, pad.sThumbLY),
        stick_dir(pad.sThumbRX, pad.sThumbRY),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    get_state = load_get_state()
    states = [XINPUT_STATE() for _ in range(4)]

    connected = [get_state(i, ctypes.byref(states[i])) == ERROR_SUCCESS for i in range(4)]
    for i in range(4):
        print(f"slot {i}: {'接続あり' if connected[i] else '未接続'}")
        if args.once and connected[i]:
            print("  " + describe(states[i].Gamepad))
    if args.once:
        return
    if not any(connected):
        print("XInput コントローラーが見つかりません。")
        return

    print("ボタンを押すと表示されます (Ctrl+C で終了)")
    last = [None] * 4
    try:
        while True:
            for i in range(4):
                if get_state(i, ctypes.byref(states[i])) != ERROR_SUCCESS:
                    continue
                snap = snapshot(states[i].Gamepad)
                if snap != last[i]:
                    last[i] = snap
                    print(f"[slot {i}] " + describe(states[i].Gamepad))
            time.sleep(1 / 120)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

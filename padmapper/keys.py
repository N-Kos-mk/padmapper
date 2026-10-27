"""キー名と仮想キーコード (VK) の対応。"""

VK = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "capslock": 0x14,
    "convert": 0x1C,
    "nonconvert": 0x1D,
    "esc": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "printscreen": 0x2C,
    "insert": 0x2D,
    "delete": 0x2E,
    "win": 0x5B,
    "rwin": 0x5C,
    "apps": 0x5D,
    "multiply": 0x6A,
    "add": 0x6B,
    "subtract": 0x6D,
    "decimal": 0x6E,
    "divide": 0x6F,
    "numlock": 0x90,
    "scrolllock": 0x91,
    "lshift": 0xA0,
    "rshift": 0xA1,
    "lctrl": 0xA2,
    "rctrl": 0xA3,
    "lalt": 0xA4,
    "ralt": 0xA5,
    "browser_back": 0xA6,
    "browser_forward": 0xA7,
    "browser_refresh": 0xA8,
    "volume_mute": 0xAD,
    "volume_down": 0xAE,
    "volume_up": 0xAF,
    "media_next": 0xB0,
    "media_prev": 0xB1,
    "media_stop": 0xB2,
    "media_play_pause": 0xB3,
    # 記号キー。配列 (JIS/US) によって刻印が異なるものは oem_* の名前で指定する
    "oem_1": 0xBA,
    "oem_plus": 0xBB,
    "comma": 0xBC,
    "minus": 0xBD,
    "period": 0xBE,
    "slash": 0xBF,
    "oem_3": 0xC0,
    "oem_4": 0xDB,
    "oem_5": 0xDC,
    "oem_6": 0xDD,
    "oem_7": 0xDE,
    "oem_102": 0xE2,
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK[_c] = ord(_c.upper())
for _d in "0123456789":
    VK[_d] = ord(_d)
for _i in range(1, 25):
    VK[f"f{_i}"] = 0x6F + _i
for _i in range(10):
    VK[f"numpad{_i}"] = 0x60 + _i

ALIASES = {
    "escape": "esc",
    "return": "enter",
    "control": "ctrl",
    "del": "delete",
    "ins": "insert",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "lwin": "win",
    "menu": "apps",
}

# 拡張キー。MapVirtualKeyW が拡張キーの印 (0xE0) を返さない環境があるため明示する。
# これがないと、例えば ↑ がテンキーの 8 と同じスキャンコードで送られる
EXTENDED_VKS = frozenset(
    [0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2C, 0x2D, 0x2E]  # PageUp〜↓, PrintScreen, Insert, Delete
    + [0x5B, 0x5C, 0x5D, 0x6F, 0xA3, 0xA5]  # Win, Apps, テンキーの /, 右 Ctrl, 右 Alt
    + list(range(0xA6, 0xB8))  # ブラウザ・音量・メディアキー
)

VK_NAMES = {}
for _name, _vk in VK.items():
    VK_NAMES.setdefault(_vk, _name)


def parse_keys(text):
    """'ctrl+shift+s' を押す順に並んだ VK のタプルにする。'0x41' のような直接指定も可。"""
    vks = []
    for part in text.split("+"):
        name = part.strip().lower()
        if not name:
            raise ValueError(f"'{text}' に空のキーがあります")
        if name.startswith("0x"):
            vk = int(name, 16)
            if not 0x01 <= vk <= 0xFE:
                raise ValueError(f"'{name}' は VK の範囲 (0x01〜0xFE) 外です")
        else:
            name = ALIASES.get(name, name)
            if name not in VK:
                raise ValueError(f"不明なキー名 '{name}'")
            vk = VK[name]
        vks.append(vk)
    return tuple(vks)


def key_name(vk):
    return VK_NAMES.get(vk, f"0x{vk:02X}")

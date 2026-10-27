"""トレイ・設定画面用のアイコン (padmapper/web/icon.ico, icon-off.ico) を生成する。

標準ライブラリのみ。コントローラーの形を 4x4 のスーパーサンプリングで描き、複数サイズの ICO にまとめる。
    python tools/make_icons.py
"""

import math
import struct
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "padmapper" / "web"
SIZES = (16, 20, 24, 32, 40, 48, 64)
SAMPLES = 4
COLORS = {"icon.ico": (0x2F, 0x6F, 0xED), "icon-off.ico": (0x8A, 0x8F, 0x98)}


def _in_rounded_rect(x, y, left, top, right, bottom, r):
    cx = min(max(x, left + r), right - r)
    cy = min(max(y, top + r), bottom - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r and left <= x <= right and top <= y <= bottom


def _inside(x, y):
    """座標 (0〜1) がコントローラーの形の内側か。"""
    body = _in_rounded_rect(x, y, 0.06, 0.24, 0.94, 0.66, 0.17)
    grips = math.hypot(x - 0.26, y - 0.64) <= 0.18 or math.hypot(x - 0.74, y - 0.64) <= 0.18
    if not (body or grips):
        return False
    # 十字キーとボタンの部分をくり抜く
    dpad = (abs(x - 0.29) <= 0.11 and abs(y - 0.45) <= 0.04) or (abs(x - 0.29) <= 0.04 and abs(y - 0.45) <= 0.11)
    buttons = math.hypot(x - 0.66, y - 0.40) <= 0.055 or math.hypot(x - 0.78, y - 0.51) <= 0.055
    return not (dpad or buttons)


def _image(size, rgb):
    """BMP 形式 (ICO 内部用) の 32bit 画像データ。"""
    rows = []
    for py in range(size):
        row = bytearray()
        for px in range(size):
            hits = sum(
                _inside((px + (sx + 0.5) / SAMPLES) / size, (py + (sy + 0.5) / SAMPLES) / size)
                for sx in range(SAMPLES)
                for sy in range(SAMPLES)
            )
            alpha = round(255 * hits / (SAMPLES * SAMPLES))
            row += bytes((rgb[2], rgb[1], rgb[0], alpha))
        rows.append(bytes(row))
    pixels = b"".join(reversed(rows))  # BMP は下の行から
    mask = bytes(((size + 31) // 32) * 4 * size)  # 透過は alpha で表すので AND マスクは全て 0
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(pixels) + len(mask), 0, 0, 0, 0)
    return header + pixels + mask


def build_ico(rgb):
    images = [_image(size, rgb) for size in SIZES]
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for size, data in zip(SIZES, images):
        out += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return out + b"".join(images)


def main():
    for name, rgb in COLORS.items():
        path = OUT_DIR / name
        path.write_bytes(build_ico(rgb))
        print(f"{path} を書き出しました")


if __name__ == "__main__":
    main()

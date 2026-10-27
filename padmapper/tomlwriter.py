"""プロファイルと全体設定を TOML に書き出す。

tomllib は読み込み専用なので、padmapper の設定で使う型 (文字列・数値・真偽値・配列・テーブル) だけを書ける
最小限の書き出しを用意する。buttons テーブル内のテーブル ({ do = ..., repeat = ... }) はインラインで書く。
"""

import math
import re

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
PROFILE_KEY_ORDER = ("inherit", "description", "match", "settings", "sticks", "buttons", "layers")


def _string(text):
    out = ['"']
    for ch in text:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _key(key):
    return key if _BARE_KEY.match(key) else _string(key)


def _value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("inf / nan は書き出せません")
        return repr(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, list):
        return "[" + ", ".join(_value(v) for v in value) + "]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        return "{ " + ", ".join(f"{_key(k)} = {_value(v)}" for k, v in value.items()) + " }"
    raise TypeError(f"TOML に書き出せない型です: {type(value).__name__}")


def _emit(lines, path, table):
    inline = bool(path) and path[-1] == "buttons"
    scalars = [(k, v) for k, v in table.items() if inline or not isinstance(v, dict)]
    tables = [(k, v) for k, v in table.items() if not inline and isinstance(v, dict)]
    # 子テーブルしかないテーブルは見出しを省く。空のテーブルは存在を残すために見出しだけ書く
    if path and (scalars or not tables):
        lines.append("")
        lines.append("[" + ".".join(_key(p) for p in path) + "]")
    for key, value in scalars:
        lines.append(f"{_key(key)} = {_value(value)}")
    for key, value in tables:
        _emit(lines, path + [key], value)


def dumps(data):
    lines = []
    _emit(lines, [], data)
    return "\n".join(lines).strip() + "\n"


def dumps_profile(raw):
    """プロファイルを、手で読みやすい項目順にして書き出す。"""
    ordered = {k: raw[k] for k in PROFILE_KEY_ORDER if k in raw}
    ordered.update({k: v for k, v in raw.items() if k not in ordered})
    return dumps(ordered)

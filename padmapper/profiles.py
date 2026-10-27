"""プロファイル (profiles/*.toml) と全体設定 (config.toml) の読み込み。"""

import fnmatch
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .keys import parse_keys
from .xinput import ALL_BUTTONS

STICKS = ("left", "right")
STICK_MODES = ("none", "mouse", "scroll", "buttons")
MOUSE_BUTTONS = ("left", "right", "middle", "x1", "x2")
WHEEL_DIRECTIONS = ("up", "down", "left", "right")
PROFILE_KEYS = {"inherit", "match", "description", "settings", "buttons", "sticks", "layers"}
LAYER_KEYS = {"buttons", "sticks"}

DEFAULT_STICK = {
    "mode": "none",
    "speed": 1000,
    "deadzone": 0.15,
    "curve": 2.0,
    "threshold": 0.5,
    "invert_y": False,
    "axis_lock": False,
}
DEFAULT_SETTINGS = {
    "trigger_threshold": 0.3,
    "repeat_delay": 0.4,
    "repeat_rate": 20,
    "scroll_step": 30,
}
DEFAULT_CONFIG = {
    "default_profile": "desktop",
    "pad": -1,
    "poll_hz": 500,
    "focus_interval": 0.2,
    "mouse_mode": "cursor",
    "start_enabled": True,
    "toggle_combo": ["BACK", "START"],
    "toggle_hold": 1.0,
}


class ProfileError(Exception):
    pass


@dataclass(frozen=True)
class Binding:
    kind: str  # key / mouse / wheel / layer / layer_toggle / profile
    target: object  # key: VK のタプル、それ以外: 名前
    repeat: bool = False
    text: str = ""


@dataclass(frozen=True)
class Stick:
    mode: str
    speed: float
    deadzone: float
    curve: float
    threshold: float
    invert_y: bool
    axis_lock: bool  # 縦横のうち強いほうの軸だけを使う


@dataclass(frozen=True)
class Settings:
    trigger_threshold: float
    repeat_delay: float
    repeat_rate: float
    scroll_step: int


@dataclass(frozen=True)
class Layer:
    buttons: dict  # ボタン名 -> Binding (None は明示的な割り当てなし)
    sticks: dict  # "left" / "right" -> Stick。指定したものだけ


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    match: tuple
    buttons: dict
    sticks: dict
    layers: dict
    settings: Settings


@dataclass(frozen=True)
class Config:
    default_profile: str
    pad: int
    poll_hz: float
    focus_interval: float
    mouse_mode: str
    start_enabled: bool
    toggle_combo: tuple
    toggle_hold: float


# 値の検証


def _number(value, where, low=None, high=None, low_open=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProfileError(f"{where}: 数値で指定してください")
    if low is not None and (value <= low if low_open else value < low):
        raise ProfileError(f"{where}: {low} {'より大きい' if low_open else '以上の'}値にしてください")
    if high is not None and value > high:
        raise ProfileError(f"{where}: {high} 以下にしてください")
    return value


def _bool(value, where):
    if not isinstance(value, bool):
        raise ProfileError(f"{where}: true か false で指定してください")
    return value


def _table(value, where):
    if not isinstance(value, dict):
        raise ProfileError(f"{where}: テーブルで指定してください")
    return value


def _no_unknown(table, allowed, where):
    unknown = set(table) - set(allowed)
    if unknown:
        raise ProfileError(f"{where}: 不明な項目 {sorted(unknown)} (使える項目: {sorted(allowed)})")


def parse_binding(value, where):
    """割り当て 1 つを解釈する。"none" は None を返す。"""
    repeat = False
    if isinstance(value, dict):
        _no_unknown(value, ("do", "repeat"), where)
        if "do" not in value:
            raise ProfileError(f"{where}: do を指定してください")
        repeat = _bool(value.get("repeat", False), f"{where}.repeat")
        value = value["do"]
    if not isinstance(value, str):
        raise ProfileError(f"{where}: 文字列で指定してください")
    if value == "none":
        return None
    kind, sep, arg = value.partition(":")
    if not sep or not arg:
        raise ProfileError(f"{where}: '{value}' は '種類:値' の形式で指定してください")
    if kind == "key":
        try:
            target = parse_keys(arg)
        except ValueError as e:
            raise ProfileError(f"{where}: {e}") from None
    elif kind == "mouse":
        if arg not in MOUSE_BUTTONS:
            raise ProfileError(f"{where}: mouse は {MOUSE_BUTTONS} のどれかです")
        target = arg
    elif kind == "wheel":
        if arg not in WHEEL_DIRECTIONS:
            raise ProfileError(f"{where}: wheel は {WHEEL_DIRECTIONS} のどれかです")
        target = arg
    elif kind in ("layer", "layer_toggle", "profile"):
        target = arg
    else:
        raise ProfileError(f"{where}: 不明な種類 '{kind}'")
    if repeat and kind not in ("key", "wheel"):
        raise ProfileError(f"{where}: repeat は key と wheel にだけ使えます")
    return Binding(kind, target, repeat, value)


def _build_buttons(raw, where):
    buttons = {}
    for name, value in raw.items():
        if name not in ALL_BUTTONS:
            raise ProfileError(f"{where}: 不明なボタン '{name}' (使えるボタン: {', '.join(ALL_BUTTONS)})")
        buttons[name] = parse_binding(value, f"{where}.{name}")
    return buttons


def _build_stick(raw, where):
    _no_unknown(raw, DEFAULT_STICK, where)
    v = {**DEFAULT_STICK, **raw}
    if v["mode"] not in STICK_MODES:
        raise ProfileError(f"{where}.mode: {STICK_MODES} のどれかです")
    return Stick(
        mode=v["mode"],
        speed=float(_number(v["speed"], f"{where}.speed", 0)),
        deadzone=float(_number(v["deadzone"], f"{where}.deadzone", 0, 0.9)),
        curve=float(_number(v["curve"], f"{where}.curve", 0, low_open=True)),
        threshold=float(_number(v["threshold"], f"{where}.threshold", 0, 1, low_open=True)),
        invert_y=_bool(v["invert_y"], f"{where}.invert_y"),
        axis_lock=_bool(v["axis_lock"], f"{where}.axis_lock"),
    )


def _build_settings(raw, where):
    _no_unknown(raw, DEFAULT_SETTINGS, where)
    v = {**DEFAULT_SETTINGS, **raw}
    return Settings(
        trigger_threshold=float(_number(v["trigger_threshold"], f"{where}.trigger_threshold", 0, 1, low_open=True)),
        repeat_delay=float(_number(v["repeat_delay"], f"{where}.repeat_delay", 0)),
        repeat_rate=float(_number(v["repeat_rate"], f"{where}.repeat_rate", 0, low_open=True)),
        scroll_step=int(_number(v["scroll_step"], f"{where}.scroll_step", 1, 120)),
    )


# 読み込みと継承


def _check_shape(raw, where):
    """継承でマージする前に、テーブルであるべき項目の型を確かめる。"""
    _no_unknown(raw, PROFILE_KEYS, where)
    for key in ("settings", "buttons"):
        _table(raw.get(key, {}), f"{where} [{key}]")
    for side, stick in _table(raw.get("sticks", {}), f"{where} [sticks]").items():
        if side not in STICKS:
            raise ProfileError(f"{where} [sticks]: 不明なスティック '{side}' (left / right)")
        _table(stick, f"{where} [sticks.{side}]")
    for name, layer in _table(raw.get("layers", {}), f"{where} [layers]").items():
        lwhere = f"{where} [layers.{name}]"
        _no_unknown(_table(layer, lwhere), LAYER_KEYS, lwhere)
        _table(layer.get("buttons", {}), f"{lwhere}.buttons")
        for side, stick in _table(layer.get("sticks", {}), f"{lwhere}.sticks").items():
            if side not in STICKS:
                raise ProfileError(f"{lwhere}.sticks: 不明なスティック '{side}' (left / right)")
            _table(stick, f"{lwhere}.sticks.{side}")


def _merge_sticks(base, over):
    return {side: {**base.get(side, {}), **over.get(side, {})} for side in {*base, *over}}


def _merge(base, over):
    """親プロファイル base に子 over を重ねる。割り当ては丸ごと置き換え、スティック設定は項目ごとに上書きする。"""
    result = dict(base)
    for key, value in over.items():
        if key in ("settings", "buttons"):
            result[key] = {**base.get(key, {}), **value}
        elif key == "sticks":
            result[key] = _merge_sticks(base.get(key, {}), value)
        elif key == "layers":
            layers = dict(base.get(key, {}))
            for name, layer in value.items():
                layers[name] = _merge(layers.get(name, {}), layer)
            result[key] = layers
        else:
            result[key] = value
    return result


def _resolve(name, raws, chain):
    if name in chain:
        raise ProfileError(f"inherit が循環しています: {' -> '.join(chain + [name])}")
    if name not in raws:
        raise ProfileError(f"{chain[-1]}.toml: 継承元のプロファイル '{name}' がありません")
    raw = raws[name]
    own = {k: v for k, v in raw.items() if k not in ("inherit", "match", "description")}
    parent = raw.get("inherit")
    if parent is None:
        return own
    if not isinstance(parent, str):
        raise ProfileError(f"{name}.toml: inherit は文字列で指定してください")
    return _merge(_resolve(parent, raws, chain + [name]), own)


def _build_profile(name, raw, merged):
    where = f"{name}.toml"
    match = raw.get("match", [])
    if not isinstance(match, list) or not all(isinstance(m, str) for m in match):
        raise ProfileError(f"{where}: match は文字列の配列で指定してください")
    description = raw.get("description", "")
    if not isinstance(description, str):
        raise ProfileError(f"{where}: description は文字列で指定してください")

    stick_raw = merged.get("sticks", {})
    sticks = {side: _build_stick(stick_raw.get(side, {}), f"{where} [sticks.{side}]") for side in STICKS}
    layers = {}
    for lname, lraw in merged.get("layers", {}).items():
        lwhere = f"{where} [layers.{lname}]"
        lsticks = {
            side: _build_stick({**stick_raw.get(side, {}), **value}, f"{lwhere}.sticks.{side}")
            for side, value in lraw.get("sticks", {}).items()
        }
        layers[lname] = Layer(_build_buttons(lraw.get("buttons", {}), f"{lwhere}.buttons"), lsticks)

    return Profile(
        name=name,
        description=description,
        match=tuple(match),
        buttons=_build_buttons(merged.get("buttons", {}), f"{where} [buttons]"),
        sticks=sticks,
        layers=layers,
        settings=_build_settings(merged.get("settings", {}), f"{where} [settings]"),
    )


def _check_references(profiles):
    for profile in profiles.values():
        tables = [("buttons", profile.buttons)]
        tables += [(f"layers.{n}.buttons", layer.buttons) for n, layer in profile.layers.items()]
        for table_name, buttons in tables:
            for button, binding in buttons.items():
                if binding is None:
                    continue
                where = f"{profile.name}.toml [{table_name}].{button}"
                if binding.kind in ("layer", "layer_toggle") and binding.target not in profile.layers:
                    raise ProfileError(f"{where}: レイヤー '{binding.target}' が定義されていません")
                if binding.kind == "profile" and binding.target != "auto" and binding.target not in profiles:
                    raise ProfileError(f"{where}: プロファイル '{binding.target}' がありません")


def _read_toml(path):
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ProfileError(f"{path.name}: TOML の書式エラー: {e}") from None


def load_raw_profiles(directory):
    """profiles/*.toml を検証せずに読む。{プロファイル名: TOML の内容}"""
    return {path.stem: _read_toml(path) for path in sorted(Path(directory).glob("*.toml"))}


def resolve_raw(name, raws):
    """継承を適用したプロファイルの内容 (match などの継承しない項目を除く)。"""
    return _resolve(name, raws, [])


def build_profiles(raws):
    """読み込んだ内容を検証して Profile にする。"""
    if not raws:
        raise ProfileError("プロファイルがありません")
    for name, raw in raws.items():
        _check_shape(raw, f"{name}.toml")
    profiles = {name: _build_profile(name, raw, _resolve(name, raws, [])) for name, raw in raws.items()}
    _check_references(profiles)
    return profiles


def load_profiles(directory):
    return build_profiles(load_raw_profiles(directory))


def load_raw_config(path):
    path = Path(path)
    return _read_toml(path) if path.exists() else {}


def load_config(path, profiles):
    return build_config(load_raw_config(path), profiles, Path(path).name)


def build_config(raw, profiles, where="config.toml"):
    _no_unknown(raw, DEFAULT_CONFIG, where)
    v = {**DEFAULT_CONFIG, **raw}
    if v["default_profile"] not in profiles:
        raise ProfileError(f"{where}: default_profile のプロファイル '{v['default_profile']}' がありません")
    if v["mouse_mode"] not in ("cursor", "relative"):
        raise ProfileError(f"{where}: mouse_mode は cursor か relative です")
    combo = v["toggle_combo"]
    if not isinstance(combo, list) or not all(b in ALL_BUTTONS for b in combo):
        raise ProfileError(f"{where}: toggle_combo はボタン名の配列で指定してください")
    pad = _number(v["pad"], f"{where}.pad", -1, 3)
    if not isinstance(pad, int):
        raise ProfileError(f"{where}.pad: 整数で指定してください")
    return Config(
        default_profile=v["default_profile"],
        pad=pad,
        poll_hz=float(_number(v["poll_hz"], f"{where}.poll_hz", 10, 1000)),
        focus_interval=float(_number(v["focus_interval"], f"{where}.focus_interval", 0.05)),
        mouse_mode=v["mouse_mode"],
        start_enabled=_bool(v["start_enabled"], f"{where}.start_enabled"),
        toggle_combo=tuple(combo),
        toggle_hold=float(_number(v["toggle_hold"], f"{where}.toggle_hold", 0)),
    )


def select_profile(profiles, exe_path, default):
    """前面アプリの実行ファイルに合うプロファイル名を返す。

    match のうち、"/" を含まないものは実行ファイル名と、含むものはフルパスと照合する。
    実行ファイル名での一致をパスでの一致より優先する。どれにも合わなければ default。
    """
    if not exe_path:
        return None
    path = exe_path.replace("\\", "/").lower()
    base = path.rsplit("/", 1)[-1]
    best, best_score = default, 0
    for name, profile in profiles.items():
        for pattern in profile.match:
            pattern = pattern.replace("\\", "/").lower()
            if "/" in pattern:
                score = 1 if fnmatch.fnmatchcase(path, pattern) else 0
            else:
                score = 2 if fnmatch.fnmatchcase(base, pattern) else 0
            if score > best_score:
                best, best_score = name, score
    return best

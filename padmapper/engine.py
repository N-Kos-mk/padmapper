"""コントローラーの状態を、プロファイルに従ってキーボード・マウス操作に変換する。"""

import math
from dataclasses import dataclass

from .profiles import select_profile
from .xinput import ALL_BUTTONS, BUTTON_BITS

TRIGGER_RELEASE_RATIO = 0.8  # 押した判定の 8 割まで戻ったら離したとみなす (ちらつき防止)
WHEEL_NOTCH = 120
WHEEL_DIRECTIONS = {
    "up": (WHEEL_NOTCH, False),
    "down": (-WHEEL_NOTCH, False),
    "right": (WHEEL_NOTCH, True),
    "left": (-WHEEL_NOTCH, True),
}


@dataclass
class _Active:
    """押されているボタンと、押した時点で実行した割り当て。"""

    binding: object
    next_repeat: float = math.inf


def lock_axis(x, y):
    """縦横のうち強いほうの軸だけを残す。"""
    return (x, 0.0) if abs(x) > abs(y) else (0.0, y)


def shape_stick(x, y, stick):
    """デッドゾーンと感度カーブを適用した (x, y) を返す。大きさは 0〜1。"""
    mag = math.hypot(x, y)
    if mag <= stick.deadzone:
        return 0.0, 0.0
    scaled = min(1.0, (mag - stick.deadzone) / (1 - stick.deadzone)) ** stick.curve
    return x / mag * scaled, y / mag * scaled


class Engine:
    def __init__(self, profiles, config, output, log=print):
        self.profiles = profiles
        self.config = config
        self.out = output
        self.log = log
        self.enabled = config.start_enabled
        self.suspended = False  # 設定画面が前面にある間など、一時的に変換を止める (enabled とは別)
        self.profile = profiles[config.default_profile]
        self.auto_name = config.default_profile
        self.manual_name = None  # profile: で手動選択したプロファイル
        self._pressed = frozenset()  # 今回の周期で押されているボタン
        self._prev = frozenset()
        self._active = {}  # ボタン名 -> _Active
        self._suppressed = set()  # 離されるまで無視するボタン
        self._held_layers = []
        self._toggled_layers = []
        self._triggers = {"LT": False, "RT": False}
        self._move = [0.0, 0.0]
        self._scroll = [0.0, 0.0]
        self._combo_since = None
        self._combo_fired = False
        self._connected = None

    @property
    def pressed(self):
        """押されているとみなしているボタン (トリガー・スティックの仮想ボタンを含む)。"""
        return self._pressed

    @property
    def active_layers(self):
        return self._layers()

    def set_enabled(self, enabled):
        if self.enabled == enabled:
            return
        self.enabled = enabled
        self.release_all()
        self.log("変換: 有効" if enabled else "変換: 無効")

    def set_suspended(self, suspended):
        if self.suspended == suspended:
            return
        self.suspended = suspended
        self.release_all()

    # プロファイル

    def replace(self, profiles, config):
        """再読み込みした設定に差し替える。送信中の入力はすべて離す。"""
        self.release_all()
        self._toggled_layers.clear()
        self.profiles = profiles
        self.config = config
        if self.manual_name not in profiles:
            self.manual_name = None
        if self.auto_name not in profiles:
            self.auto_name = config.default_profile
        self.profile = profiles[self.manual_name or self.auto_name]

    def set_manual(self, name):
        """プロファイルを固定する。None で前面のアプリに合わせた自動選択に戻す。"""
        self.manual_name = name
        self.switch_profile(name or self.auto_name)

    def set_foreground(self, exe_path):
        name = select_profile(self.profiles, exe_path, self.config.default_profile)
        if name is None or name == self.auto_name:
            return
        self.auto_name = name
        if self.manual_name is None:
            self.switch_profile(name)

    def switch_profile(self, name):
        if self.profile.name == name:
            return
        self.release_all()
        self._toggled_layers.clear()
        self.profile = self.profiles[name]
        self.log(f"プロファイル: {name}")

    def release_all(self):
        """送信中の入力をすべて離す。押されたままのボタンは、一度離されるまで無視する。"""
        self._suppressed |= self._pressed
        self._active.clear()
        self._held_layers.clear()
        self._move = [0.0, 0.0]
        self._scroll = [0.0, 0.0]
        self.out.release_all()

    # 毎周期の処理

    def update(self, state, now, dt):
        if state is None:
            if self._connected:
                self.log("コントローラーが切断されました")
            self._connected = False
            self.release_all()
            self._pressed = self._prev = frozenset()
            self._suppressed.clear()
            self._combo_since = None
            return
        if not self._connected:
            self.log("コントローラーを検出しました")
            self._connected = True

        pressed = self._digital(state)
        self._pressed = pressed
        self._check_toggle(pressed, now)
        for button in self._prev - pressed:
            self._release(button)
        if self.enabled and not self.suspended:
            for button in ALL_BUTTONS:
                if button in pressed and button not in self._prev:
                    self._press(button, now)
            self._repeat(now)
            self._sticks(state, dt)
        self._prev = pressed

    def _digital(self, state):
        """デジタルなボタンとして扱う入力の集合。トリガーと、buttons モードのスティックを含む。"""
        pressed = {name for name, bit in BUTTON_BITS.items() if state.buttons & bit}
        threshold = self.profile.settings.trigger_threshold
        for name, value in (("LT", state.lt), ("RT", state.rt)):
            limit = threshold * TRIGGER_RELEASE_RATIO if self._triggers[name] else threshold
            self._triggers[name] = value > limit
            if self._triggers[name]:
                pressed.add(name)
        sticks = self._effective_sticks()
        for side, prefix, x, y in (("left", "LS", state.lx, state.ly), ("right", "RS", state.rx, state.ry)):
            stick = sticks[side]
            if stick.mode != "buttons":
                continue
            if stick.axis_lock:
                x, y = lock_axis(x, y)
            for direction, value in (("UP", y), ("DOWN", -y), ("RIGHT", x), ("LEFT", -x)):
                name = f"{prefix}_{direction}"
                limit = stick.threshold * TRIGGER_RELEASE_RATIO if name in self._prev else stick.threshold
                if value > limit:
                    pressed.add(name)
        return frozenset(pressed)

    def _check_toggle(self, pressed, now):
        combo = self.config.toggle_combo
        if not combo or not set(combo) <= pressed:
            self._combo_since = None
            self._combo_fired = False
            return
        if self._combo_since is None:
            self._combo_since = now
        if self._combo_fired or now - self._combo_since < self.config.toggle_hold:
            return
        self._combo_fired = True
        self.set_enabled(not self.enabled)

    # ボタン

    def _layers(self):
        """有効なレイヤー名。後ろほど優先。"""
        return self._toggled_layers + self._held_layers

    def _lookup(self, button):
        for name in reversed(self._layers()):
            layer = self.profile.layers[name]
            if button in layer.buttons:
                return layer.buttons[button]
        return self.profile.buttons.get(button)

    def _press(self, button, now):
        if button in self._suppressed:
            return
        binding = self._lookup(button)
        entry = _Active(binding)
        self._active[button] = entry
        if binding is None:
            return
        kind = binding.kind
        if kind == "key":
            self.out.press_keys(binding.target)
        elif kind == "mouse":
            self.out.press_mouse(binding.target)
        elif kind == "wheel":
            self.out.wheel(*WHEEL_DIRECTIONS[binding.target])
        elif kind == "layer":
            self._held_layers.append(binding.target)
        elif kind == "layer_toggle":
            if binding.target in self._toggled_layers:
                self._toggled_layers.remove(binding.target)
                self.log(f"レイヤー {binding.target}: 無効")
            else:
                self._toggled_layers.append(binding.target)
                self.log(f"レイヤー {binding.target}: 有効")
        elif kind == "profile":
            self.set_manual(None if binding.target == "auto" else binding.target)
            return
        if binding.repeat:
            entry.next_repeat = now + self.profile.settings.repeat_delay

    def _release(self, button):
        self._suppressed.discard(button)
        entry = self._active.pop(button, None)
        if entry is None or entry.binding is None:
            return
        binding = entry.binding
        if binding.kind == "key":
            self.out.release_keys(binding.target)
        elif binding.kind == "mouse":
            self.out.release_mouse(binding.target)
        elif binding.kind == "layer" and binding.target in self._held_layers:
            self._held_layers.remove(binding.target)

    def _repeat(self, now):
        interval = 1 / self.profile.settings.repeat_rate
        for entry in self._active.values():
            if now < entry.next_repeat:
                continue
            binding = entry.binding
            if binding.kind == "key":
                # 修飾キーは押したまま、最後のキーだけを繰り返す
                self.out.repeat_key(binding.target[-1])
            elif binding.kind == "wheel":
                self.out.wheel(*WHEEL_DIRECTIONS[binding.target])
            entry.next_repeat += interval
            if entry.next_repeat < now:
                entry.next_repeat = now + interval

    # スティック

    def _effective_sticks(self):
        sticks = dict(self.profile.sticks)
        for name in self._layers():
            sticks.update(self.profile.layers[name].sticks)
        return sticks

    def _sticks(self, state, dt):
        sticks = self._effective_sticks()
        for side, x, y in (("left", state.lx, state.ly), ("right", state.rx, state.ry)):
            stick = sticks[side]
            if stick.mode not in ("mouse", "scroll"):
                continue
            if stick.axis_lock:
                x, y = lock_axis(x, y)
            vx, vy = shape_stick(x, y, stick)
            if stick.invert_y:
                vy = -vy
            if stick.mode == "mouse":
                self._move[0] += vx * stick.speed * dt
                self._move[1] -= vy * stick.speed * dt  # 画面座標は下が正
            else:
                self._scroll[0] += vx * stick.speed * WHEEL_NOTCH * dt
                self._scroll[1] += vy * stick.speed * WHEEL_NOTCH * dt

        dx, dy = int(self._move[0]), int(self._move[1])
        if dx or dy:
            self._move[0] -= dx
            self._move[1] -= dy
            self.out.move(dx, dy)
        step = self.profile.settings.scroll_step
        for index, horizontal in ((1, False), (0, True)):
            amount = int(self._scroll[index] / step) * step
            if amount:
                self._scroll[index] -= amount
                self.out.wheel(amount, horizontal)

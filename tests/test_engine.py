import tempfile
import unittest
from pathlib import Path

from padmapper.engine import Engine
from padmapper.keys import VK
from padmapper.output import Output
from padmapper.profiles import load_config, load_profiles
from padmapper.xinput import BUTTON_BITS, PadState

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DT = 0.002


class Recorder:
    """送信内容を記録するだけのバックエンド。"""

    def __init__(self):
        self.events = []

    def key(self, vk, down):
        self.events.append(("key", vk, down))

    def mouse_button(self, button, down):
        self.events.append(("mouse", button, down))

    def wheel(self, delta, horizontal):
        self.events.append(("wheel", delta, horizontal))

    def move(self, dx, dy):
        self.events.append(("move", dx, dy))

    def take(self):
        events, self.events = self.events, []
        return events


def pad(*buttons, **axes):
    bits = 0
    for name in buttons:
        bits |= BUTTON_BITS[name]
    return PadState(buttons=bits, **axes)


class EngineTest(unittest.TestCase):
    def setUp(self):
        profiles = load_profiles(FIXTURES / "profiles")
        self.config = load_config(FIXTURES / "config.toml", profiles)
        self.rec = Recorder()
        self.engine = Engine(profiles, self.config, Output(self.rec), log=lambda _: None)
        self.now = 0.0
        self.step(pad())

    def step(self, state, seconds=DT):
        self.now += seconds
        self.engine.update(state, self.now, seconds)
        return self.rec.take()

    def test_button_press_and_release(self):
        self.assertEqual(self.step(pad("A")), [("mouse", "left", True)])
        self.assertEqual(self.step(pad("A")), [])
        self.assertEqual(self.step(pad()), [("mouse", "left", False)])

    def test_layer_while_held(self):
        self.step(pad(), seconds=0)
        self.step(pad(lt=1.0))
        events = self.step(pad("X", lt=1.0))
        self.assertEqual(events, [("key", VK["ctrl"], True), ("key", VK["c"], True)])
        # レイヤーのボタンを先に離しても、X を離したときに押した時点の割り当てが離される
        self.assertEqual(self.step(pad("X")), [])
        self.assertEqual(self.step(pad()), [("key", VK["c"], False), ("key", VK["ctrl"], False)])
        self.assertEqual(self.step(pad("X")), [("key", VK["enter"], True)])

    def test_shared_key_released_by_last_button(self):
        self.step(pad("A"))
        self.assertEqual(self.step(pad("A", rt=1.0)), [])
        self.assertEqual(self.step(pad(rt=1.0)), [])
        self.assertEqual(self.step(pad()), [("mouse", "left", False)])

    def test_trigger_hysteresis(self):
        self.assertEqual(self.step(pad(rt=0.35)), [("mouse", "left", True)])
        self.assertEqual(self.step(pad(rt=0.28)), [])
        self.assertEqual(self.step(pad(rt=0.2)), [("mouse", "left", False)])

    def test_toggle_combo_disables_and_enables(self):
        self.step(pad("BACK", "START"))
        self.step(pad("BACK", "START"), seconds=1.1)
        self.assertFalse(self.engine.enabled)
        self.step(pad())
        self.assertEqual(self.step(pad("A")), [])
        self.step(pad())
        self.step(pad("BACK", "START"))
        self.step(pad("BACK", "START"), seconds=1.1)
        self.assertTrue(self.engine.enabled)
        self.assertEqual(self.step(pad()), [])
        self.assertEqual(self.step(pad("A")), [("mouse", "left", True)])

    def test_disable_releases_held_input(self):
        self.step(pad("A"))
        self.step(pad("A", "BACK", "START"))
        events = self.step(pad("A", "BACK", "START"), seconds=1.1)
        self.assertIn(("mouse", "left", False), events)

    def test_profile_switch_releases_and_suppresses(self):
        self.step(pad("A"))
        self.engine.set_foreground(r"C:\Games\emu\emu.exe")
        self.assertEqual(self.engine.profile.name, "emu")
        self.assertEqual(self.rec.take(), [("mouse", "left", False)])
        self.assertEqual(self.step(pad("A")), [])
        self.assertEqual(self.step(pad()), [])
        self.assertEqual(self.step(pad(rt=1.0)), [("mouse", "left", True)])

    def test_suspended_sends_nothing_and_releases(self):
        self.step(pad("A"))
        self.engine.set_suspended(True)
        self.assertEqual(self.rec.take(), [("mouse", "left", False)])
        self.assertEqual(self.step(pad()), [])
        self.assertEqual(self.step(pad("B")), [])
        self.assertIn("B", self.engine.pressed)  # 設定画面の表示用に、押されたボタンは記録される
        self.engine.set_suspended(False)
        self.assertEqual(self.step(pad("B")), [])  # 停止中から押したままのボタンは、離すまで無視する
        self.step(pad())
        self.assertEqual(self.step(pad("B")), [("mouse", "right", True)])

    def test_disconnect_releases(self):
        self.step(pad("A"))
        self.assertEqual(self.step(None), [("mouse", "left", False)])

    def test_stick_moves_cursor(self):
        moved_x = moved_y = 0
        for _ in range(50):
            for kind, dx, dy in self.step(pad(lx=1.0, ly=1.0 / 3), seconds=0.002):
                self.assertEqual(kind, "move")
                moved_x += dx
                moved_y += dy
        self.assertGreater(moved_x, 0)
        self.assertLess(moved_y, 0)  # スティック上 = 画面上方向
        self.assertLessEqual(moved_x, 1400 * 0.1)

    def test_scroll_axis_lock(self):
        events = []
        for _ in range(25):
            events += self.step(pad(rx=0.6, ry=-1.0), seconds=0.01)
        self.assertTrue(events)
        # 右下に倒しても、強いほうの縦方向 (下) だけがスクロールされる
        self.assertTrue(all(e[0] == "wheel" and e[1] < 0 and e[2] is False for e in events))

    def test_deadzone_does_not_move(self):
        self.assertEqual(self.step(pad(lx=0.1, ly=-0.1), seconds=0.5), [])

    def test_key_repeat(self):
        self.assertEqual(self.step(pad("UP")), [("key", VK["up"], True)])
        self.assertEqual(self.step(pad("UP"), seconds=0.3), [])
        events = self.step(pad("UP"), seconds=0.15)
        self.assertEqual(events, [("key", VK["up"], True)])
        self.assertEqual(self.step(pad()), [("key", VK["up"], False)])

    def test_layer_toggle(self):
        self.engine.switch_profile("touch")
        self.rec.take()
        self.assertEqual(self.step(pad(rt=1.0)), [])
        self.step(pad())
        self.step(pad("LS"))
        self.step(pad())
        self.assertEqual(self.step(pad(rt=1.0)), [("mouse", "left", True)])
        self.step(pad())
        self.step(pad("LS"))
        self.step(pad())
        self.assertEqual(self.step(pad(rt=1.0)), [])


class StickButtonsTest(unittest.TestCase):
    def test_stick_as_buttons(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "p.toml").write_text(
                '[sticks.left]\nmode = "buttons"\n[buttons]\nLS_UP = "key:w"\n', encoding="utf-8"
            )
            Path(d, "config.txt").write_text('default_profile = "p"\n', encoding="utf-8")
            profiles = load_profiles(d)
            config = load_config(Path(d, "config.txt"), profiles)
            rec = Recorder()
            engine = Engine(profiles, config, Output(rec), log=lambda _: None)
            engine.update(PadState(ly=0.6), 0.0, DT)
            self.assertEqual(rec.take(), [("key", VK["w"], True)])
            engine.update(PadState(ly=0.45), 0.01, DT)  # 戻りのしきい値 (0.4) より上なので押したまま
            self.assertEqual(rec.take(), [])
            engine.update(PadState(ly=0.3), 0.02, DT)
            self.assertEqual(rec.take(), [("key", VK["w"], False)])

    def test_stick_buttons_axis_lock_is_four_way(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "p.toml").write_text(
                '[sticks.left]\nmode = "buttons"\naxis_lock = true\n[buttons]\nLS_UP = "key:w"\nLS_RIGHT = "key:d"\n',
                encoding="utf-8",
            )
            Path(d, "config.txt").write_text('default_profile = "p"\n', encoding="utf-8")
            profiles = load_profiles(d)
            rec = Recorder()
            engine = Engine(profiles, load_config(Path(d, "config.txt"), profiles), Output(rec), log=lambda _: None)
            engine.update(PadState(lx=0.6, ly=0.7), 0.0, DT)
            self.assertEqual(rec.take(), [("key", VK["w"], True)])


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from padmapper.keys import VK
from padmapper.profiles import ProfileError, load_config, load_profiles, select_profile

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def write_profiles(directory, files):
    for name, text in files.items():
        Path(directory, f"{name}.toml").write_text(text, encoding="utf-8")
    return load_profiles(directory)


class FixtureProfilesTest(unittest.TestCase):
    def test_bundled_profiles_and_config_load(self):
        profiles = load_profiles(FIXTURES / "profiles")
        config = load_config(FIXTURES / "config.toml", profiles)
        self.assertIn(config.default_profile, profiles)
        self.assertEqual(profiles["desktop"].sticks["left"].mode, "mouse")
        # レイヤーのスティック設定は、指定していない項目をプロファイルから引き継ぐ
        fn_left = profiles["desktop"].layers["fn"].sticks["left"]
        self.assertEqual((fn_left.mode, fn_left.speed), ("mouse", 350))

    def test_select_bundled_profiles(self):
        profiles = load_profiles(FIXTURES / "profiles")
        select = lambda path: select_profile(profiles, path, "desktop")  # noqa: E731
        self.assertEqual(select(r"C:\Games\emu\emu.exe"), "emu")
        self.assertEqual(select(r"C:\Games\touch\touchapp.exe"), "touch")
        self.assertEqual(select(r"D:\SteamLibrary\steamapps\common\Terraria\Terraria.exe"), "passthrough")
        self.assertEqual(select(r"C:\Windows\explorer.exe"), "desktop")
        self.assertIsNone(select(None))


class LoadTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_inherit_overrides_and_none_unbinds(self):
        profiles = write_profiles(
            self.dir,
            {
                "parent": '[buttons]\nA = "key:a"\nB = { do = "key:b", repeat = true }\n[sticks.left]\nmode = "mouse"\nspeed = 100\n',
                "child": 'inherit = "parent"\n[buttons]\nA = "none"\nB = "key:c"\n[sticks.left]\nspeed = 200\n',
            },
        )
        child = profiles["child"]
        self.assertIsNone(child.buttons["A"])
        self.assertEqual(child.buttons["B"].target, (VK["c"],))
        self.assertFalse(child.buttons["B"].repeat)
        self.assertEqual((child.sticks["left"].mode, child.sticks["left"].speed), ("mouse", 200))

    def test_match_is_not_inherited(self):
        profiles = write_profiles(self.dir, {"parent": 'match = ["a.exe"]\n', "child": 'inherit = "parent"\n'})
        self.assertEqual(profiles["child"].match, ())

    def test_chord_keys_in_press_order(self):
        profiles = write_profiles(self.dir, {"p": '[buttons]\nA = "key:ctrl+shift+s"\n'})
        self.assertEqual(profiles["p"].buttons["A"].target, (VK["ctrl"], VK["shift"], VK["s"]))

    def test_errors(self):
        cases = {
            "unknown button": '[buttons]\nZ = "key:a"\n',
            "unknown key": '[buttons]\nA = "key:nosuchkey"\n',
            "unknown kind": '[buttons]\nA = "jump:a"\n',
            "missing layer": '[buttons]\nA = "layer:nope"\n',
            "repeat on mouse": '[buttons]\nA = { do = "mouse:left", repeat = true }\n',
            "bad stick mode": '[sticks.left]\nmode = "fly"\n',
            "unknown top key": 'buttonz = 1\n',
            "missing parent": 'inherit = "nope"\n',
        }
        for label, text in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ProfileError):
                    write_profiles(d, {"p": text})

    def test_inherit_cycle(self):
        with self.assertRaises(ProfileError):
            write_profiles(self.dir, {"a": 'inherit = "b"\n', "b": 'inherit = "a"\n'})

    def test_exe_match_beats_path_match(self):
        profiles = write_profiles(
            self.dir,
            {"games": 'match = ["C:/Games/*"]\n', "emu": 'match = ["emu.exe"]\n', "default": ""},
        )
        self.assertEqual(select_profile(profiles, r"C:\Games\emu\emu.exe", "default"), "emu")
        self.assertEqual(select_profile(profiles, r"C:\Games\other\game.exe", "default"), "games")
        self.assertEqual(select_profile(profiles, r"C:\Tools\tool.exe", "default"), "default")


if __name__ == "__main__":
    unittest.main()

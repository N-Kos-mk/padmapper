import tomllib
import unittest
from pathlib import Path

from padmapper.profiles import load_raw_profiles
from padmapper.tomlwriter import dumps, dumps_profile

ROOT = Path(__file__).resolve().parent.parent
# 追跡しているプロファイル (テスト用・サンプル・共通設定)
PROFILE_DIRS = (ROOT / "tests" / "fixtures" / "profiles", ROOT / "examples" / "profiles")


class TomlWriterTest(unittest.TestCase):
    def assertRoundTrip(self, data, dump=dumps):
        self.assertEqual(tomllib.loads(dump(data)), data)

    def test_tracked_profiles_round_trip(self):
        for directory in PROFILE_DIRS:
            for name, raw in load_raw_profiles(directory).items():
                with self.subTest(f"{directory.parent.name}/{name}"):
                    self.assertRoundTrip(raw, dumps_profile)
        with open(ROOT / "profiles" / "base.toml", "rb") as f:
            self.assertRoundTrip(tomllib.load(f), dumps_profile)

    def test_values_and_escaping(self):
        self.assertRoundTrip(
            {
                "description": 'quote " backslash \\ 改行\nタブ\t',
                "match": ["C:/Games/*", "a.exe"],
                "settings": {"repeat_rate": 20, "repeat_delay": 0.4},
                "sticks": {"left": {"mode": "mouse", "invert_y": False, "deadzone": 0.15}},
            }
        )

    def test_buttons_are_inline_and_empty_tables_survive(self):
        data = {
            "buttons": {"A": "key:a", "UP": {"do": "key:up", "repeat": True}},
            "layers": {"fn": {}, "日本語": {"buttons": {"B": "none"}, "sticks": {"left": {}}}},
        }
        text = dumps_profile(data)
        self.assertIn('UP = { do = "key:up", repeat = true }', text)
        self.assertIn("[layers.fn]", text)
        self.assertRoundTrip(data, dumps_profile)

    def test_rejects_unsupported_values(self):
        with self.assertRaises(TypeError):
            dumps({"a": None})
        with self.assertRaises(ValueError):
            dumps({"a": float("inf")})


if __name__ == "__main__":
    unittest.main()

"""ENV 选项来自本地配置：默认到 Link3，改成 Link4 就出现 Link4，配置坏掉不崩整批。"""

import json
import tempfile
import unittest
from pathlib import Path

from autorename.config import ensure_default_config, load_env_options

DEFAULTS = ("Server", "Link1", "Link2", "Link3")


class EnvOptionsFromConfigTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "config.json"

    def test_missing_config_falls_back_to_the_default_options(self):
        options = load_env_options(self.path)

        self.assertEqual(options.envs, DEFAULTS)
        self.assertIsNone(options.warning)

    def test_config_can_add_a_fourth_link(self):
        self._write({"envs": ["Server", "Link1", "Link2", "Link3", "Link4"]})

        options = load_env_options(self.path)

        self.assertEqual(options.envs[-1], "Link4")
        self.assertEqual(len(options.envs), 5)

    def test_configured_envs_are_canonicalised(self):
        self._write({"envs": ["SERVER", "link1", "  Link2 "]})

        self.assertEqual(load_env_options(self.path).envs, ("Server", "Link1", "Link2"))

    def test_duplicate_options_collapse_into_one(self):
        self._write({"envs": ["Server", "SERVER", "Link1"]})

        self.assertEqual(load_env_options(self.path).envs, ("Server", "Link1"))

    def test_broken_config_keeps_the_defaults_and_says_why(self):
        self.path.write_text("{ 这不是 JSON", encoding="utf-8")

        options = load_env_options(self.path)

        self.assertEqual(options.envs, DEFAULTS)
        self.assertTrue(options.warning)
        self.assertIn(str(self.path), options.warning)

    def test_empty_env_list_falls_back_instead_of_offering_nothing(self):
        self._write({"envs": []})

        options = load_env_options(self.path)

        self.assertEqual(options.envs, DEFAULTS)
        self.assertTrue(options.warning)

    def test_ensure_writes_an_editable_default_file_once(self):
        ensure_default_config(self.path)
        self.assertTrue(self.path.is_file())

        self.path.write_text(json.dumps({"envs": ["Server", "Link4"]}), encoding="utf-8")
        ensure_default_config(self.path)

        self.assertEqual(load_env_options(self.path).envs, ("Server", "Link4"))

    def _write(self, payload: dict) -> None:
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

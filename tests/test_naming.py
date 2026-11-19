"""命名规则：模板、ENV 的大小写、封闭的类别词表、默认落盘目录。"""

import os
import unittest

from autorename.naming import build_target_name, default_target_directory
from autorename.vocabulary import CATEGORIES, DEFAULT_ENVS, canonical_env


class TargetNameTest(unittest.TestCase):
    def test_target_name_follows_the_agreed_template(self):
        """规格里的模板是 `(ENV)<Ultraviewer ID>_PCNAME-类别.png`，日期段不进名字。"""
        name = build_target_name(ultraviewer_id="82331647", pcname="TCSB2", env="Server", category="Spec")

        self.assertEqual(name, "(Server)82331647_TCSB2-Spec.png")

    def test_shouted_or_lowercase_env_is_corrected_in_the_name(self):
        """磁盘上旧的示意稿写全大写，不得照抄：名字里只能是 `Server` / `Link1`。"""
        for written in ("SERVER", "server", "SeRvEr"):
            with self.subTest(written=written):
                name = build_target_name(
                    ultraviewer_id="82331647", pcname="TCSB2", env=written, category="Spec"
                )
                self.assertEqual(name, "(Server)82331647_TCSB2-Spec.png")

        name = build_target_name(ultraviewer_id="82335369", pcname="BB", env="LINK1", category="Group")
        self.assertEqual(name, "(Link1)82335369_BB-Group.png")


class EnvCasingTest(unittest.TestCase):
    def test_canonical_form_is_first_letter_upper_rest_lower(self):
        self.assertEqual(canonical_env("Server"), "Server")
        self.assertEqual(canonical_env("SERVER"), "Server")
        self.assertEqual(canonical_env("  link2 "), "Link2")
        self.assertEqual(canonical_env("LINK3"), "Link3")


class VocabularyTest(unittest.TestCase):
    def test_category_vocabulary_is_closed_and_corrected(self):
        self.assertEqual(len(CATEGORIES), 7)
        self.assertIn("Data", CATEGORIES)
        self.assertIn("Group", CATEGORIES)
        self.assertNotIn("Database", CATEGORIES)
        self.assertNotIn("Goup", CATEGORIES)

    def test_default_env_options_cover_server_and_at_least_three_links(self):
        """规格：默认至少到 `Link3`，`Server` 打头。"""
        self.assertEqual(DEFAULT_ENVS[0], "Server")
        for expected in ("Link1", "Link2", "Link3"):
            self.assertIn(expected, DEFAULT_ENVS)


class DefaultTargetDirectoryTest(unittest.TestCase):
    def test_default_target_directory_is_renamed_under_the_source(self):
        self.assertEqual(
            default_target_directory(os.path.join("C:", "Shots")),
            os.path.join("C:", "Shots", "Renamed"),
        )


if __name__ == "__main__":
    unittest.main()

"""分类器：OCR 文本 → 7 类之一，或「未定」。

12 张实拍图的文本录在 `fixtures/ocr_texts.json`，测试不跑真 OCR。
类别以界面本身为准，人工标注一次，改规则时先看这张表。
"""

import json
import unittest
from pathlib import Path

from autorename.classifier import RULES, Rule, classify
from autorename.vocabulary import CATEGORIES, UNDECIDED

FIXTURES = Path(__file__).parent / "fixtures" / "ocr_texts.json"

# 12 张实拍图的人工标注：同一界面的两张图（服务器 / 客户端）判同一类。
EXPECTED = {
    "82331647_TCSB218112026_111024.png": "Version",
    "82331647_TCSB218112026_111027.png": "Data",
    "82331647_TCSB218112026_111030.png": "Group",
    "82331647_TCSB218112026_111035.png": "Test",
    "82331647_TCSB218112026_11156.png": "Analyse",
    "82331647_TCSB218112026_11157.png": "Main",
    "82331647_TCSB218112026_11835.png": "Spec",
    "82335369_BB18112026_111038.png": "Test",
    "82335369_BB18112026_111040.png": "Spec",
    "82335369_BB18112026_111042.png": "Data",
    "82335369_BB18112026_111048.png": "Group",
    "82335369_BB18112026_111049.png": "Version",
}


def _fixtures() -> dict[str, list[str]]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


class RealBatchTest(unittest.TestCase):
    """验收：12 张实拍图，每张都判对。"""

    def setUp(self):
        self.texts = _fixtures()

    def test_every_recorded_screenshot_is_recognised(self):
        self.assertEqual(len(self.texts), 12)
        self.assertEqual(set(self.texts), set(EXPECTED))

        for filename, expected in EXPECTED.items():
            with self.subTest(filename=filename):
                self.assertEqual(classify(self.texts[filename]), expected)

    def test_most_rows_are_predicted_so_the_human_only_confirms(self):
        predicted = [classify(lines) for lines in self.texts.values()]
        decided = [category for category in predicted if category != UNDECIDED]

        self.assertGreaterEqual(len(decided), 11)

    def test_every_prediction_stays_inside_the_closed_vocabulary(self):
        for filename, lines in self.texts.items():
            with self.subTest(filename=filename):
                self.assertIn(classify(lines), CATEGORIES + (UNDECIDED,))


class BoundaryTextTest(unittest.TestCase):
    """构造的边界文本：规则优先级最容易踩空的那几条。"""

    def test_spec_page_mentioning_this_pc_is_not_swallowed_by_main(self):
        """`This PC` 也在 Main 的触发词里，但 Spec 必须先命中。"""
        lines = ["This PC", "Device specifications", "Rename this PC", "Installed RAM 8.00 GB"]

        self.assertEqual(classify(lines), "Spec")

    def test_this_pc_alone_is_spec(self):
        self.assertEqual(classify(["This PC"]), "Spec")

    def test_desktop_screen_stays_main_even_with_a_this_pc_icon(self):
        """桌面上有个「此电脑」图标，但那是主屏，不是规格页。"""
        lines = ["This PC", "Recycle Bin", "Type here to search", "Control Panel"]

        self.assertEqual(classify(lines), "Main")

    def test_database_alone_becomes_data(self):
        """历史误标 `Database` 必须归成 `Data`，不是原样保留。"""
        self.assertEqual(classify(["Database"]), "Data")

    def test_goup_alone_becomes_group(self):
        self.assertEqual(classify(["Goup"]), "Group")

    def test_database_group_page_is_group_not_data(self):
        """`SQL Account Database Group` 里有个 `Database`，仍是 Group。"""
        self.assertEqual(classify(["SQL Account Database Group"]), "Group")

    def test_empty_text_is_undecided(self):
        for empty in ([], [""], ["   "], ""):
            with self.subTest(text=empty):
                self.assertEqual(classify(empty), UNDECIDED)

    def test_text_matching_nothing_is_undecided(self):
        self.assertEqual(classify(["Lorem ipsum dolor sit amet"]), UNDECIDED)

    def test_a_single_string_is_accepted_like_a_list_of_lines(self):
        self.assertEqual(classify("DCF Database"), classify(["DCF", "Database"]))


class RuleTableTest(unittest.TestCase):
    """规则表本身的约束：顺序与词表。"""

    def test_main_rule_is_last(self):
        """`Main` 的触发词最泛，排最后才不会先吞掉 Spec。"""
        self.assertEqual(RULES[-1].category, "Main")

    def test_every_rule_names_a_category_from_the_closed_vocabulary(self):
        for rule in RULES:
            with self.subTest(category=rule.category):
                self.assertIn(rule.category, CATEGORIES)

    def test_a_rule_with_a_legacy_misspelling_refuses_to_exist(self):
        with self.assertRaises(ValueError):
            Rule("Database", ("database",))


if __name__ == "__main__":
    unittest.main()

"""分类器：OCR 文本 → 词表里的某一类，或「未定」。

17 张实拍图的文本录在 `fixtures/ocr_texts.json`，测试不跑真 OCR。
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


# 5 张新样本的人工标注：类别取自文件名，窗口内容逐张核对过。
MANUAL_EXPECTED = {
    "113267544_LAPTOP-SVL3F0SP(Financial_Date.png": "Financial_Date",
    "113267544_LAPTOP-SVL3F0SP(License.png": "License",
    "113267544_LAPTOP-SVL3F0SP(Report Header.png": "Report_Header",
    "113341216_LAPTOP-G59BTH4M(Bank.png": "Bank",
    "87005828_OFFICE-KELVIN(Negative.png": "Negative",
}


def _fixtures() -> dict[str, list[str]]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


class RealBatchTest(unittest.TestCase):
    """验收：17 张实拍图，每张都判对。"""

    def setUp(self):
        self.texts = _fixtures()

    def test_every_recorded_screenshot_is_recognised(self):
        self.assertEqual(set(self.texts), set(EXPECTED) | set(MANUAL_EXPECTED))

        for filename, expected in (EXPECTED | MANUAL_EXPECTED).items():
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


class ManualCategoryTest(unittest.TestCase):
    """后五个类别：判据是窗口里的字段标签，不是「银行」「负数」这种单词。"""

    def setUp(self):
        self.texts = _fixtures()

    def test_activation_window_is_not_swallowed_by_spec(self):
        """激活窗口里有 `Product ID`，Spec 的触发词也有——顺序错了这张就变 Spec。"""
        self.assertEqual(
            classify(self.texts["113267544_LAPTOP-SVL3F0SP(License.png"]), "License"
        )

    def test_account_chart_is_bank_not_license(self):
        """许可证窗口里也有 `Foreign Bank`、`Bank Reconciliation`，所以判据只用 `Bank Account`。"""
        self.assertEqual(classify(self.texts["113341216_LAPTOP-G59BTH4M(Bank.png"]), "Bank")

    def test_report_header_window_wins_over_its_company_profile_title(self):
        """窗口标题就是 `Company Profile`（另一个类别名），这一页仍须判 Report_Header。"""
        self.assertEqual(
            classify(self.texts["113267544_LAPTOP-SVL3F0SP(Report Header.png"]), "Report_Header"
        )

    def test_the_two_options_dialogs_do_not_swap(self):
        """Financial_Date 与 Negative 是同一个 Options 对话框，连标签页都一样。"""
        self.assertEqual(
            classify(self.texts["113267544_LAPTOP-SVL3F0SP(Financial_Date.png"]), "Financial_Date"
        )
        self.assertEqual(classify(self.texts["87005828_OFFICE-KELVIN(Negative.png"]), "Negative")

    def test_a_single_misread_label_is_backed_up_by_the_other(self):
        """`Financial Start Period` 与 `System Conversion Date` 是两个独立标签。

        读坏一个，另一个还立得住；两个都坏才退回「未定」——多短语规则的用意就在这。
        """
        lines = self.texts["113267544_LAPTOP-SVL3F0SP(Financial_Date.png"]
        one_broken = [
            line.replace("Financial Start Period", "Financia1 Start Period") for line in lines
        ]
        self.assertEqual(classify(one_broken), "Financial_Date")

        both_broken = [
            line.replace("System Conversion Date", "System Converslon Date") for line in one_broken
        ]
        self.assertEqual(classify(both_broken), UNDECIDED)


class ShapeEvidenceTest(unittest.TestCase):
    """结构证据：格式本身就是判据，标题被截掉也认得出。"""

    def test_a_license_key_alone_is_enough(self):
        self.assertEqual(classify(["VMKS-X8VP-RL6F-8JV4-2EEV-SRKV-9XQM-JKCW"]), "License")

    def test_a_license_key_read_in_lowercase_still_counts(self):
        self.assertEqual(classify(["vmks-x8vp-rl6f-8jv4-2eev-srkv-9xqm-jkcw"]), "License")

    def test_a_windows_product_id_is_not_mistaken_for_a_license_key(self):
        """Windows 规格页的产品 ID 是 5 段，形状对不上激活码。"""
        self.assertNotEqual(classify(["Product ID 00330-80000-00000-AA123"]), "License")


class WeakWordTest(unittest.TestCase):
    """单词级触发词是误判的主要来源：这几个词单独出现时必须留在「未定」。"""

    def test_bare_words_are_not_enough(self):
        for text in (
            ["Bank"],
            ["Negative"],
            ["Report"],
            ["License"],
            ["Bank Reconciliation", "Foreign Bank"],
            ["Maintain Account"],
        ):
            with self.subTest(text=text):
                self.assertEqual(classify(text), UNDECIDED)


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

    def test_a_rule_without_any_evidence_refuses_to_exist(self):
        """两类证据都空 = 永远不可能命中，是写错了，不是「暂时不用」。"""
        with self.assertRaises(ValueError):
            Rule("Bank")

    def test_a_rule_with_a_broken_shape_refuses_to_exist(self):
        with self.assertRaises(ValueError):
            Rule("Bank", ("bank account",), shapes=("(unclosed",))

    def test_no_rule_predicts_other(self):
        """`Other` 是给人点的兜底，不是机器的兜底。

        它不在「未定」里，一旦被规则命中，认不出的图会直接落盘成 `-Other.png`，
        「宁可让人点一下」这条底线就没了。
        """
        self.assertNotIn("Other", {rule.category for rule in RULES})


if __name__ == "__main__":
    unittest.main()

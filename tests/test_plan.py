"""计划器：逐张决定（ENV + 类别 + Ultraviewer ID + PCNAME）→ 谁可以落盘、谁卡在哪儿。

未定、ENV 未点、缺 ID 或缺 PCNAME 的图只是被挡在门外，不拖累同批其余图。
文件名不合规的图也能落盘——补齐缺的那几项就行，所以它挡住的理由会逐项列出。
"""

import unittest

from autorename.nameparse import parse_filename
from autorename.plan import Decision, plan_batch
from autorename.scanner import ScanResult, ScannedImage

CONFIRMED = "82331647_TCSB218112026_111024.png"
UNDECIDED_IMAGE = "82331647_TCSB218112026_111027.png"
TARGET = "C:/shots/Renamed"


def _scan(*filenames: str) -> ScanResult:
    return ScanResult(
        directory="C:/shots",
        images=[ScannedImage(filename=name, parsed=parse_filename(name)) for name in filenames],
    )


class ReadyImageTest(unittest.TestCase):
    def test_confirmed_image_carries_the_target_name_and_the_machine(self):
        plan = plan_batch(
            _scan(CONFIRMED),
            [Decision(CONFIRMED, env="Server", category="Spec")],
            TARGET,
        )

        self.assertEqual(plan.blocked, ())
        self.assertEqual(len(plan.ready), 1)
        copy = plan.ready[0]
        self.assertEqual(copy.source_filename, CONFIRMED)
        self.assertEqual(copy.target_name, "(Server)82331647_TCSB2-Spec.png")
        self.assertEqual(copy.pcname, "TCSB2")
        self.assertEqual(copy.env, "Server")
        self.assertEqual(copy.category, "Spec")

    def test_env_from_the_page_is_canonicalised_before_it_reaches_the_name(self):
        plan = plan_batch(
            _scan(CONFIRMED),
            [Decision(CONFIRMED, env="SERVER", category="Spec")],
            TARGET,
        )

        self.assertEqual(plan.ready[0].target_name, "(Server)82331647_TCSB2-Spec.png")
        self.assertEqual(plan.ready[0].env, "Server")

    def test_the_machine_confirmed_for_the_group_brings_its_own_pcname_and_id(self):
        """组头选定的机器说了算：PCNAME 与 Ultraviewer ID 一次带出，不逐张填。"""
        plan = plan_batch(
            _scan(CONFIRMED),
            [Decision(CONFIRMED, env="Link1", category="Spec", pcname="BB", ultraviewer_id="82335369")],
            TARGET,
        )

        self.assertEqual(plan.ready[0].target_name, "(Link1)82335369_BB-Spec.png")
        self.assertEqual(plan.ready[0].pcname, "BB")

    def test_without_a_confirmed_machine_the_filename_identity_stands(self):
        plan = plan_batch(
            _scan(CONFIRMED),
            [Decision(CONFIRMED, env="Server", category="Spec", pcname="", ultraviewer_id="")],
            TARGET,
        )

        self.assertEqual(plan.ready[0].target_name, "(Server)82331647_TCSB2-Spec.png")


class BlockedImageTest(unittest.TestCase):
    def test_undecided_category_is_blocked_and_keeps_its_reason(self):
        plan = plan_batch(
            _scan(CONFIRMED),
            [Decision(CONFIRMED, env="Server", category="未定")],
            TARGET,
        )

        self.assertEqual(plan.ready, ())
        self.assertEqual(plan.blocked[0].reason, "类别未定")

    def test_missing_env_is_blocked(self):
        plan = plan_batch(
            _scan(CONFIRMED),
            [Decision(CONFIRMED, env="", category="Spec")],
            TARGET,
        )

        self.assertEqual(plan.ready, ())
        self.assertEqual(plan.blocked[0].reason, "ENV 未选")

    def test_image_without_any_decision_is_blocked_for_both_reasons(self):
        plan = plan_batch(_scan(CONFIRMED), [], TARGET)

        self.assertEqual(plan.ready, ())
        self.assertEqual(plan.blocked[0].reason, "类别未定、ENV 未选")

    def test_category_outside_the_vocabulary_says_so_instead_of_pretending_it_is_unset(self):
        plan = plan_batch(
            _scan(CONFIRMED),
            [Decision(CONFIRMED, env="Server", category="Database")],
            TARGET,
        )

        self.assertEqual(plan.ready, ())
        self.assertEqual(plan.blocked[0].reason, "类别不在词表里：Database")

    def test_non_compliant_filename_lists_every_missing_field(self):
        """文件名不合规不再一句话判死：缺哪一项就列哪一项，人补一项少一项。"""
        broken = "82331647_111024.png"
        plan = plan_batch(
            _scan(broken),
            [Decision(broken, env="Server", category="Spec")],
            TARGET,
        )

        self.assertEqual(plan.ready, ())
        self.assertEqual(plan.blocked[0].reason, "PCNAME 未定、Ultraviewer ID 未填")


class NonCompliantImageTest(unittest.TestCase):
    """文件名不合规的图：补齐 ID、PCNAME、类别、ENV 就能落盘。"""

    BROKEN = "82331647_111024.png"

    def test_filling_in_the_missing_fields_lets_it_through(self):
        plan = plan_batch(
            _scan(self.BROKEN),
            [
                Decision(
                    self.BROKEN,
                    env="Server",
                    category="Spec",
                    pcname="TCSB2",
                    ultraviewer_id="82331647",
                )
            ],
            TARGET,
        )

        self.assertEqual(plan.blocked, ())
        self.assertEqual(plan.ready[0].target_name, "(Server)82331647_TCSB2-Spec.png")
        self.assertEqual(plan.ready[0].ultraviewer_id, "82331647")

    def test_nothing_filled_in_says_all_four_are_missing(self):
        plan = plan_batch(_scan(self.BROKEN), [], TARGET)

        self.assertEqual(plan.ready, ())
        self.assertEqual(
            plan.blocked[0].reason,
            "类别未定、ENV 未选、PCNAME 未定、Ultraviewer ID 未填",
        )

    def test_a_hand_typed_id_must_be_digits_only(self):
        plan = plan_batch(
            _scan(self.BROKEN),
            [
                Decision(
                    self.BROKEN,
                    env="Server",
                    category="Spec",
                    pcname="TCSB2",
                    ultraviewer_id="82-331",
                )
            ],
            TARGET,
        )

        self.assertEqual(plan.ready, ())
        self.assertEqual(plan.blocked[0].reason, "Ultraviewer ID 必须是纯数字：82-331")

    def test_a_full_width_id_is_refused_even_though_python_calls_it_a_digit(self):
        """`str.isdigit()` 放行全角数字，但它们进不了文件名，不能悄悄落盘。"""
        plan = plan_batch(
            _scan(self.BROKEN),
            [
                Decision(
                    self.BROKEN,
                    env="Server",
                    category="Spec",
                    pcname="TCSB2",
                    ultraviewer_id="８２３３１６４７",
                )
            ],
            TARGET,
        )

        self.assertEqual(plan.ready, ())
        self.assertEqual(plan.blocked[0].reason, "Ultraviewer ID 必须是纯数字：８２３３１６４７")

    def test_a_hand_typed_id_beats_the_one_in_the_filename(self):
        """没选机器时，页面送下来的手输 ID 压过文件名里的（组头选了机器则以登记为准）。"""
        plan = plan_batch(
            _scan(CONFIRMED),
            [Decision(CONFIRMED, env="Server", category="Spec", ultraviewer_id="99999999")],
            TARGET,
        )

        self.assertEqual(plan.ready[0].target_name, "(Server)99999999_TCSB2-Spec.png")


class PcnameValidationTest(unittest.TestCase):
    """PCNAME 现在可以手改，改出来的名字照样进文件名：非法字符得当场挡住。"""

    def test_a_hand_typed_pcname_with_a_slash_is_blocked_and_named(self):
        plan = plan_batch(
            _scan(CONFIRMED),
            [Decision(CONFIRMED, env="Server", category="Spec", pcname="TCSB/2")],
            TARGET,
        )

        self.assertEqual(plan.ready, ())
        self.assertEqual(plan.blocked[0].reason, "PCNAME 含非法字符：TCSB/2")

    def test_every_windows_forbidden_character_blocks_the_card(self):
        """九个字符一个都不能漏：漏一个就会落出一个打不开的文件名。"""
        for character in '\\/:*?"<>|':
            with self.subTest(character=character):
                plan = plan_batch(
                    _scan(CONFIRMED),
                    [Decision(CONFIRMED, env="Server", category="Spec", pcname="TCSB" + character + "2")],
                    TARGET,
                )

                self.assertEqual(plan.ready, ())
                self.assertIn("PCNAME 含非法字符", plan.blocked[0].reason)

    def test_a_hand_typed_pcname_is_taken_as_typed(self):
        """手填的值只去首尾空格：大小写与连字符照原样进文件名，工具不替人归一。"""
        plan = plan_batch(
            _scan(CONFIRMED),
            [Decision(CONFIRMED, env="Server", category="Spec", pcname="  tcsb-2  ")],
            TARGET,
        )

        self.assertEqual(plan.blocked, ())
        self.assertEqual(plan.ready[0].pcname, "tcsb-2")
        self.assertEqual(plan.ready[0].target_name, "(Server)82331647_tcsb-2-Spec.png")


class CollisionNumberingTest(unittest.TestCase):
    """同机同类多张：首张不带数字后缀，第二张起 `-2`、`-3`，互不覆盖。"""

    FIRST = "82331647_TCSB218112026_111024.png"
    SECOND = "82331647_TCSB218112026_111027.png"
    THIRD = "82331647_TCSB218112026_111030.png"

    def test_images_without_a_time_fragment_are_numbered_last(self):
        """手动补全的图没有时间片段：排在最后，彼此按源文件名。"""
        plan = plan_batch(
            _scan(self.FIRST, "broken_b.png", "broken_a.png"),
            [
                Decision(self.FIRST, env="Server", category="Spec"),
                Decision("broken_b.png", env="Server", category="Spec", pcname="TCSB2", ultraviewer_id="82331647"),
                Decision("broken_a.png", env="Server", category="Spec", pcname="TCSB2", ultraviewer_id="82331647"),
            ],
            TARGET,
        )

        names = {copy.source_filename: copy.target_name for copy in plan.ready}
        self.assertEqual(names[self.FIRST], "(Server)82331647_TCSB2-Spec.png")
        self.assertEqual(names["broken_a.png"], "(Server)82331647_TCSB2-Spec-2.png")
        self.assertEqual(names["broken_b.png"], "(Server)82331647_TCSB2-Spec-3.png")

    def test_three_images_from_one_machine_and_category_are_numbered_from_the_second(self):
        plan = plan_batch(
            _scan(self.FIRST, self.SECOND, self.THIRD),
            [
                Decision(self.FIRST, env="Server", category="Spec"),
                Decision(self.SECOND, env="Server", category="Spec"),
                Decision(self.THIRD, env="Server", category="Spec"),
            ],
            TARGET,
        )

        self.assertEqual(
            [copy.target_name for copy in plan.ready],
            [
                "(Server)82331647_TCSB2-Spec.png",
                "(Server)82331647_TCSB2-Spec-2.png",
                "(Server)82331647_TCSB2-Spec-3.png",
            ],
        )

    def test_the_suffix_follows_the_time_fragment_not_the_order_they_were_listed(self):
        """编号只为防撞名，不表达顺序语义：排序只认文件名里的时间片段。"""
        plan = plan_batch(
            _scan(self.THIRD, self.FIRST, self.SECOND),
            [
                Decision(self.FIRST, env="Server", category="Spec"),
                Decision(self.SECOND, env="Server", category="Spec"),
                Decision(self.THIRD, env="Server", category="Spec"),
            ],
            TARGET,
        )

        by_source = {copy.source_filename: copy.target_name for copy in plan.ready}
        self.assertEqual(by_source[self.FIRST], "(Server)82331647_TCSB2-Spec.png")
        self.assertEqual(by_source[self.SECOND], "(Server)82331647_TCSB2-Spec-2.png")
        self.assertEqual(by_source[self.THIRD], "(Server)82331647_TCSB2-Spec-3.png")

    def test_two_machines_do_not_share_a_counter(self):
        other_machine = "82331648_TCSB318112026_111024.png"
        plan = plan_batch(
            _scan(self.FIRST, other_machine),
            [
                Decision(self.FIRST, env="Server", category="Spec"),
                Decision(other_machine, env="Server", category="Spec"),
            ],
            TARGET,
        )

        self.assertEqual(
            [copy.target_name for copy in plan.ready],
            ["(Server)82331647_TCSB2-Spec.png", "(Server)82331648_TCSB3-Spec.png"],
        )

    def test_two_categories_of_one_machine_do_not_share_a_counter(self):
        plan = plan_batch(
            _scan(self.FIRST, self.SECOND),
            [
                Decision(self.FIRST, env="Server", category="Spec"),
                Decision(self.SECOND, env="Server", category="Data"),
            ],
            TARGET,
        )

        self.assertEqual(
            [copy.target_name for copy in plan.ready],
            ["(Server)82331647_TCSB2-Spec.png", "(Server)82331647_TCSB2-Data.png"],
        )

    def test_two_envs_of_one_machine_and_category_do_not_share_a_counter(self):
        """ENV 写在名字最前面：`(Server)…-Spec` 与 `(Link1)…-Spec` 本来就不撞名。"""
        plan = plan_batch(
            _scan(self.FIRST, self.SECOND),
            [
                Decision(self.FIRST, env="Server", category="Spec"),
                Decision(self.SECOND, env="Link1", category="Spec"),
            ],
            TARGET,
        )

        self.assertEqual(
            [copy.target_name for copy in plan.ready],
            ["(Server)82331647_TCSB2-Spec.png", "(Link1)82331647_TCSB2-Spec.png"],
        )


class MixedBatchTest(unittest.TestCase):
    def test_undecided_rows_do_not_stop_the_confirmed_ones(self):
        plan = plan_batch(
            _scan(CONFIRMED, UNDECIDED_IMAGE),
            [
                Decision(CONFIRMED, env="Server", category="Spec"),
                Decision(UNDECIDED_IMAGE, env="", category="未定"),
            ],
            TARGET,
        )

        self.assertEqual([copy.source_filename for copy in plan.ready], [CONFIRMED])
        self.assertEqual([item.source_filename for item in plan.blocked], [UNDECIDED_IMAGE])

    def test_plan_remembers_where_it_will_land(self):
        plan = plan_batch(_scan(CONFIRMED), [Decision(CONFIRMED, "Link1", "Group")], TARGET)

        self.assertEqual(plan.target_directory, TARGET)


if __name__ == "__main__":
    unittest.main()

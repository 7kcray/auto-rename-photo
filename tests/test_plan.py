"""计划器：逐张决定（ENV + 类别）→ 谁可以落盘、谁卡在哪儿。

未定、ENV 未点、文件名不合规的图只是被挡在门外，不拖累同批其余图。
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

    def test_the_machine_confirmed_for_the_group_brings_its_own_pcname_and_number(self):
        """组头选定的机器说了算：PCNAME 与数字一次带出，不逐张填。"""
        plan = plan_batch(
            _scan(CONFIRMED),
            [Decision(CONFIRMED, env="Link1", category="Spec", pcname="BB", number="82335369")],
            TARGET,
        )

        self.assertEqual(plan.ready[0].target_name, "(Link1)82335369_BB-Spec.png")
        self.assertEqual(plan.ready[0].pcname, "BB")

    def test_without_a_confirmed_machine_the_filename_identity_stands(self):
        plan = plan_batch(
            _scan(CONFIRMED),
            [Decision(CONFIRMED, env="Server", category="Spec", pcname="", number="")],
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

    def test_non_compliant_filename_is_blocked_whatever_was_decided(self):
        broken = "82331647_111024.png"
        plan = plan_batch(
            _scan(broken),
            [Decision(broken, env="Server", category="Spec")],
            TARGET,
        )

        self.assertEqual(plan.ready, ())
        self.assertEqual(plan.blocked[0].reason, "文件名不合规")


class CollisionNumberingTest(unittest.TestCase):
    """同机同类多张：首张不带数字后缀，第二张起 `-2`、`-3`，互不覆盖。"""

    FIRST = "82331647_TCSB218112026_111024.png"
    SECOND = "82331647_TCSB218112026_111027.png"
    THIRD = "82331647_TCSB218112026_111030.png"

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

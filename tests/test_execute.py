"""批量执行核心（主缝）：源目录 + 逐张决定 → 落盘目录内容 + 日志行。

只断言外部行为：目标目录里出现了哪些文件、rename-log.csv 里写了什么、
源目录有没有被动过。不碰内部函数。
"""

import csv
import os
import tempfile
import unittest
from pathlib import Path

from autorename.executor import LOG_FILENAME, TargetUnusable, apply_plan
from autorename.plan import Decision, plan_batch
from autorename.scanner import scan_directory

CONFIRMED = "82331647_TCSB218112026_111024.png"
UNDECIDED = "82331647_TCSB218112026_111027.png"
BROKEN = "82331647_111030.png"
STAMP = "2026-11-19 16:00:00"

PNG_BODY = b"\x89PNG\r\n\x1a\n" + b"body" * 20


class ExecutorTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "shots"
        self.source.mkdir()
        self.target = self.root / "shots" / "Renamed"

    def make_source(self, *filenames: str) -> None:
        for filename in filenames:
            (self.source / filename).write_bytes(PNG_BODY + filename.encode())

    def run_batch(self, decisions: list[Decision]):
        scan = scan_directory(str(self.source))
        plan = plan_batch(scan, decisions, str(self.target))
        return apply_plan(plan, clock=lambda: STAMP)

    def log_rows(self) -> list[dict[str, str]]:
        with (self.target / LOG_FILENAME).open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def target_names(self) -> list[str]:
        return sorted(path.name for path in self.target.glob("*.png"))


class CopyTest(ExecutorTestCase):
    def test_confirmed_image_lands_in_the_target_directory_under_its_new_name(self):
        self.make_source(CONFIRMED)

        self.run_batch([Decision(CONFIRMED, env="Server", category="Spec")])

        self.assertEqual(self.target_names(), ["(Server)82331647_TCSB2-Spec.png"])

    def test_copy_keeps_the_bytes_of_the_original(self):
        self.make_source(CONFIRMED)

        self.run_batch([Decision(CONFIRMED, env="Link1", category="Group")])

        copied = self.target / "(Link1)82331647_TCSB2-Group.png"
        self.assertEqual(copied.read_bytes(), (self.source / CONFIRMED).read_bytes())


class SourceStaysReadOnlyTest(ExecutorTestCase):
    def test_source_names_count_and_mtime_are_untouched(self):
        self.make_source(CONFIRMED, UNDECIDED, BROKEN)
        before = {
            path.name: (path.stat().st_size, path.stat().st_mtime_ns)
            for path in self.source.glob("*.png")
        }

        self.run_batch([Decision(CONFIRMED, env="Server", category="Spec")])

        after = {
            path.name: (path.stat().st_size, path.stat().st_mtime_ns)
            for path in self.source.glob("*.png")
        }
        self.assertEqual(after, before)

    def test_no_target_file_is_written_next_to_the_originals(self):
        self.make_source(CONFIRMED)

        self.run_batch([Decision(CONFIRMED, env="Server", category="Spec")])

        self.assertEqual(sorted(p.name for p in self.source.glob("*.png")), [CONFIRMED])


class LogTest(ExecutorTestCase):
    def test_log_lives_in_the_target_directory_with_the_seven_agreed_columns(self):
        self.make_source(CONFIRMED)

        self.run_batch([Decision(CONFIRMED, env="Server", category="Spec")])

        self.assertTrue((self.target / LOG_FILENAME).is_file())
        rows = self.log_rows()
        self.assertEqual(
            list(rows[0].keys()),
            ["源文件名", "目标文件名", "机器", "ENV", "类别", "状态", "时间戳"],
        )

    def test_log_row_records_the_whole_story_of_one_image(self):
        self.make_source(CONFIRMED)

        self.run_batch([Decision(CONFIRMED, env="Server", category="Spec")])

        self.assertEqual(
            self.log_rows()[0],
            {
                "源文件名": CONFIRMED,
                "目标文件名": "(Server)82331647_TCSB2-Spec.png",
                "机器": "TCSB2",
                "ENV": "Server",
                "类别": "Spec",
                "状态": "已复制",
                "时间戳": STAMP,
            },
        )


class PartialBatchTest(ExecutorTestCase):
    def test_undecided_and_broken_images_do_not_block_the_confirmed_one(self):
        self.make_source(CONFIRMED, UNDECIDED, BROKEN)

        result = self.run_batch(
            [
                Decision(CONFIRMED, env="Server", category="Spec"),
                Decision(UNDECIDED, env="Link1", category="未定"),
            ]
        )

        self.assertEqual(self.target_names(), ["(Server)82331647_TCSB2-Spec.png"])
        self.assertEqual(result.copied, 1)
        self.assertEqual(
            sorted(item.source_filename for item in result.blocked), sorted([UNDECIDED, BROKEN])
        )
        self.assertEqual([row["源文件名"] for row in self.log_rows()], [CONFIRMED])


class ExistingTargetTest(ExecutorTestCase):
    def test_existing_target_is_left_alone_and_logged_as_a_conflict(self):
        self.make_source(CONFIRMED)
        decision = [Decision(CONFIRMED, env="Server", category="Spec")]
        self.run_batch(decision)
        copied = self.target / "(Server)82331647_TCSB2-Spec.png"
        copied.write_bytes(b"x" * copied.stat().st_size)
        marker = copied.stat().st_mtime_ns

        result = self.run_batch(decision)

        self.assertEqual(result.conflicts, 1)
        self.assertEqual(copied.stat().st_mtime_ns, marker)
        self.assertEqual(self.log_rows()[-1]["状态"], "冲突")

    def test_two_images_that_would_share_a_name_do_not_silently_drop_one(self):
        """防撞名编号是后面的事；这一版只保证不静默覆盖、且冲突看得见。"""
        first = "82331647_TCSB218112026_111024.png"
        second = "82331647_TCSB218112026_111025.png"
        self.make_source(first, second)

        result = self.run_batch(
            [
                Decision(first, env="Server", category="Spec"),
                Decision(second, env="Server", category="Spec"),
            ]
        )

        self.assertEqual(result.copied, 1)
        self.assertEqual(result.conflicts, 1)
        self.assertEqual(len(self.target_names()), 1)


class TargetDirectoryTest(ExecutorTestCase):
    def test_target_directory_that_is_the_source_is_refused(self):
        """源目录只读：落盘目录指回源目录时宁可报错，也不往原目录里写。"""
        self.make_source(CONFIRMED)
        plan = plan_batch(
            scan_directory(str(self.source)),
            [Decision(CONFIRMED, env="Server", category="Spec")],
            str(self.source),
        )

        with self.assertRaises(TargetUnusable):
            apply_plan(plan, clock=lambda: STAMP)

        self.assertEqual(sorted(path.name for path in self.source.iterdir()), [CONFIRMED])

    def test_target_directory_that_is_an_existing_file_is_refused_readably(self):
        self.make_source(CONFIRMED)
        occupied = self.root / "not-a-directory"
        occupied.write_text("x", encoding="utf-8")
        plan = plan_batch(
            scan_directory(str(self.source)),
            [Decision(CONFIRMED, env="Server", category="Spec")],
            str(occupied),
        )

        with self.assertRaises(TargetUnusable) as raised:
            apply_plan(plan, clock=lambda: STAMP)

        self.assertIn("落盘目录用不了", str(raised.exception))


class SecondBatchTest(ExecutorTestCase):
    def test_second_batch_appends_to_the_same_log_without_a_second_header(self):
        self.make_source(CONFIRMED, UNDECIDED)

        self.run_batch([Decision(CONFIRMED, env="Server", category="Spec")])
        self.run_batch([Decision(UNDECIDED, env="Link1", category="Group")])

        rows = self.log_rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["状态"] for row in rows], ["已复制", "已复制"])


if __name__ == "__main__":
    unittest.main()

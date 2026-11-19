"""落盘器：按计划把图复制进落盘目录，并写 `rename-log.csv`。

源目录只读：不重命名、不删除、不写入——落盘目录指到源目录上直接拒绝。
日志写在落盘目录里，跟着产出走，事后查「哪张改成了什么」不用回头找源目录。

重跑同一批要幂等，所以目标文件已存在时不覆盖，按大小分流：

- 大小相同 → 上一遍已经落好了，记一行「跳过」。中途失败后重跑，只补缺的那几张。
- 大小不同 → 那是别人的同名文件，既不跳过（跳过等于谎报已落好）也不覆盖，记一行「冲突」。

日志只压掉重复的「跳过」：同一张图的「跳过」记一行就够，再跑几遍也不会一直变长。
「已复制」照实记——删掉一张再重跑补回来，那一遍确实复制了，日志里要留这一次。
"""

import csv
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

from autorename.plan import BlockedImage, Plan, PlannedCopy

LOG_FILENAME = "rename-log.csv"
SOURCE_COLUMN = "源文件名"
TARGET_COLUMN = "目标文件名"
STATUS_COLUMN = "状态"
LOG_HEADER = (SOURCE_COLUMN, TARGET_COLUMN, "机器", "ENV", "类别", STATUS_COLUMN, "时间戳")

STATUS_COPIED = "已复制"
STATUS_SKIPPED = "跳过"
STATUS_CONFLICT = "冲突"
STATUS_FAILED = "失败"


class TargetUnusable(Exception):
    """落盘目录用不了：是源目录、是个文件、或者建不出来。消息直接给用户看。"""


@dataclass(frozen=True)
class AppliedRow:
    """日志里的一行：一张图从哪个名字变成了哪个名字。"""

    copy: PlannedCopy
    status: str
    timestamp: str
    detail: str = ""

    def as_csv_row(self) -> list[str]:
        return [
            self.copy.source_filename,
            self.copy.target_name,
            self.copy.pcname,
            self.copy.env,
            self.copy.category,
            self.status,
            self.timestamp,
        ]


@dataclass(frozen=True)
class ApplyResult:
    target_directory: str
    log_path: str
    rows: tuple[AppliedRow, ...]
    blocked: tuple[BlockedImage, ...]

    def count(self, status: str) -> int:
        return sum(1 for row in self.rows if row.status == status)

    @property
    def copied(self) -> int:
        return self.count(STATUS_COPIED)

    @property
    def skipped(self) -> int:
        return self.count(STATUS_SKIPPED)

    @property
    def conflicts(self) -> int:
        return self.count(STATUS_CONFLICT)

    @property
    def failed(self) -> int:
        return self.count(STATUS_FAILED)

    def to_payload(self) -> dict:
        return {
            "target_directory": self.target_directory,
            "log_path": self.log_path,
            "copied": self.copied,
            "skipped": self.skipped,
            "conflicts": self.conflicts,
            "failed": self.failed,
            "blocked": [
                {"filename": item.source_filename, "reason": item.reason}
                for item in self.blocked
            ],
            "rows": [
                {
                    "source": row.copy.source_filename,
                    "target": row.copy.target_name,
                    "status": row.status,
                    "detail": row.detail,
                }
                for row in self.rows
            ],
        }


def apply_plan(plan: Plan, clock: Callable[[], str] | None = None) -> ApplyResult:
    """照计划复制。单张失败只记一行「失败」，不中断整批。"""
    stamp = (clock or _now)()
    target_directory = _prepare_target(plan.source_directory, plan.target_directory)
    source_directory = Path(plan.source_directory)

    rows = [
        _apply_one(copy, source_directory, target_directory, stamp)
        for copy in plan.ready
    ]

    log_path = target_directory / LOG_FILENAME
    _append_log(log_path, rows)

    return ApplyResult(
        target_directory=str(target_directory),
        log_path=str(log_path),
        rows=tuple(rows),
        blocked=plan.blocked,
    )


def _apply_one(
    copy: PlannedCopy, source_directory: Path, target_directory: Path, stamp: str
) -> AppliedRow:
    status, detail = _place(source_directory / copy.source_filename, target_directory / copy.target_name)
    return AppliedRow(copy=copy, status=status, timestamp=stamp, detail=detail)


def _prepare_target(source_directory: str, target_directory: str) -> Path:
    """确认落盘目录能用：不能是源目录，得建得出来。"""
    source = Path(source_directory)
    target = Path(target_directory)
    try:
        if target.resolve() == source.resolve():
            raise TargetUnusable("落盘目录不能是源目录：源目录只读，不能往里写。")
        target.mkdir(parents=True, exist_ok=True)
    except TargetUnusable:
        raise
    except OSError as error:
        raise TargetUnusable(
            f"落盘目录用不了：{target_directory}（{error.strerror or error}）"
        ) from error

    return target


def _place(source: Path, target: Path) -> tuple[str, str]:
    """复制一张图，返回状态与一句细节。目标已存在时按大小分流，见模块开头。"""
    try:
        if target.exists():
            return _judge_existing(source, target)
        shutil.copy2(source, target)
        return STATUS_COPIED, ""
    except OSError as error:
        return STATUS_FAILED, str(error.strerror or error)


def _judge_existing(source: Path, target: Path) -> tuple[str, str]:
    """目标已存在：大小一样就是同一张图，不一样就是别人的文件。"""
    source_size = source.stat().st_size
    target_size = target.stat().st_size
    if source_size == target_size:
        return STATUS_SKIPPED, "目标文件已存在且大小相同，跳过"
    return STATUS_CONFLICT, (
        f"目标文件已存在且大小不同（源 {source_size} 字节 / 目标 {target_size} 字节），没有覆盖"
    )


def _append_log(log_path: Path, rows: Sequence[AppliedRow]) -> None:
    """追加写日志；第一次写时补表头。UTF-8 BOM 只为让 Excel 认出中文。

    重复的「跳过」压掉，其余照实追加——见模块开头的取舍。
    """
    if not rows:
        return

    skipped = _logged_skips(log_path)
    fresh = not log_path.exists() or log_path.stat().st_size == 0
    try:
        with log_path.open("a", encoding="utf-8-sig" if fresh else "utf-8", newline="") as handle:
            writer = csv.writer(handle)
            if fresh:
                writer.writerow(LOG_HEADER)
            for row in rows:
                if row.status == STATUS_SKIPPED:
                    identity = (row.copy.source_filename, row.copy.target_name)
                    if identity in skipped:
                        continue
                    skipped.add(identity)
                writer.writerow(row.as_csv_row())
    except OSError:
        # 日志写不出来不该让已经落好的图变成一次失败。
        pass


def _logged_skips(log_path: Path) -> set[tuple[str, str]]:
    """日志里已经记过「跳过」的（源文件名, 目标文件名）。

    读不出来就当没记过——宁可多写一行重复，也不能因为旧日志坏了而漏记这一批。
    """
    if not log_path.is_file():
        return set()

    try:
        with log_path.open(encoding="utf-8-sig", newline="") as handle:
            return {
                (row.get(SOURCE_COLUMN) or "", row.get(TARGET_COLUMN) or "")
                for row in csv.DictReader(handle)
                if row.get(STATUS_COLUMN) == STATUS_SKIPPED
            }
    except (OSError, UnicodeDecodeError, csv.Error):
        return set()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

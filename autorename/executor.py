"""落盘器：按计划把图复制进落盘目录，并写 `rename-log.csv`。

源目录只读：不重命名、不删除、不写入——落盘目录指到源目录上直接拒绝。
日志写在落盘目录里，跟着产出走，事后查「哪张改成了什么」不用回头找源目录。

目标文件已存在时一律不覆盖，记一行「冲突」：同批重名（计划器已经排过 `-2`/`-3`，
这里还撞上就是落盘目录里本来就有同名文件）和重跑同一批都会走到这里，静默覆盖等于丢图。
"""

import csv
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

from autorename.plan import BlockedImage, Plan, PlannedCopy

LOG_FILENAME = "rename-log.csv"
LOG_HEADER = ("源文件名", "目标文件名", "机器", "ENV", "类别", "状态", "时间戳")

STATUS_COPIED = "已复制"
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
    """复制一张图，返回状态与一句细节。已存在的目标文件一律不覆盖。"""
    try:
        if target.exists():
            return STATUS_CONFLICT, "目标文件已存在，没有覆盖"
        shutil.copy2(source, target)
        return STATUS_COPIED, ""
    except OSError as error:
        return STATUS_FAILED, str(error.strerror or error)


def _append_log(log_path: Path, rows: Sequence[AppliedRow]) -> None:
    """追加写日志；第一次写时补表头。UTF-8 BOM 只为让 Excel 认出中文。"""
    if not rows:
        return

    fresh = not log_path.exists() or log_path.stat().st_size == 0
    try:
        with log_path.open("a", encoding="utf-8-sig" if fresh else "utf-8", newline="") as handle:
            writer = csv.writer(handle)
            if fresh:
                writer.writerow(LOG_HEADER)
            for row in rows:
                writer.writerow(row.as_csv_row())
    except OSError:
        # 日志写不出来不该让已经落好的图变成一次失败。
        pass


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

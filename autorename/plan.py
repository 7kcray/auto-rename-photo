"""计划器（纯函数）：扫描结果 + 逐张决定 → 目标文件名清单与阻塞原因。

只管「谁叫什么、谁被挡在门外」，不碰磁盘。落盘由 executor 按这份清单执行。
挡住的图只影响它自己：未定一张，其余照样落盘。
"""

from dataclasses import dataclass
from typing import Sequence

from autorename.naming import build_target_name
from autorename.scanner import ScanResult
from autorename.vocabulary import CATEGORIES, UNDECIDED, canonical_env


@dataclass(frozen=True)
class Decision:
    """页面上对一张图的决定。两个下拉都默认空着，空着就是没点。"""

    filename: str
    env: str = ""
    category: str = ""


@dataclass(frozen=True)
class PlannedCopy:
    """一张可以落盘的图：从哪个名字复制成哪个名字。"""

    source_filename: str
    target_name: str
    pcname: str
    env: str
    category: str


@dataclass(frozen=True)
class BlockedImage:
    source_filename: str
    reason: str


@dataclass(frozen=True)
class Plan:
    source_directory: str
    target_directory: str
    ready: tuple[PlannedCopy, ...]
    blocked: tuple[BlockedImage, ...]


def plan_batch(
    scan: ScanResult, decisions: Sequence[Decision], target_directory: str
) -> Plan:
    """按扫描顺序逐张过一遍决定，分成能落盘与落不了盘两摞。"""
    by_filename = {decision.filename: decision for decision in decisions}

    ready: list[PlannedCopy] = []
    blocked: list[BlockedImage] = []

    for image in scan.images:
        if image.parsed is None:
            blocked.append(BlockedImage(image.filename, "文件名不合规"))
            continue

        decision = by_filename.get(image.filename) or Decision(image.filename)
        env = canonical_env(decision.env)
        category = decision.category

        problems = []
        if not category or category == UNDECIDED:
            problems.append("类别未定")
        elif category not in CATEGORIES:
            problems.append(f"类别不在词表里：{category}")
        if not env:
            problems.append("ENV 未选")

        if problems:
            blocked.append(BlockedImage(image.filename, "、".join(problems)))
            continue

        parsed = image.parsed
        ready.append(
            PlannedCopy(
                source_filename=image.filename,
                target_name=build_target_name(
                    number=parsed.number, pcname=parsed.pcname, env=env, category=category
                ),
                pcname=parsed.pcname,
                env=env,
                category=category,
            )
        )

    return Plan(
        source_directory=scan.directory,
        target_directory=target_directory,
        ready=tuple(ready),
        blocked=tuple(blocked),
    )

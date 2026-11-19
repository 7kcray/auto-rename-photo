"""计划器（纯函数）：扫描结果 + 逐张决定 → 目标文件名清单与阻塞原因。

只管「谁叫什么、谁被挡在门外」，不碰磁盘。落盘由 executor 按这份清单执行。
挡住的图只影响它自己：未定一张，其余照样落盘。
"""

from dataclasses import dataclass, replace
from typing import Sequence

from autorename.naming import build_target_name, with_sequence
from autorename.scanner import ScanResult
from autorename.vocabulary import CATEGORIES, UNDECIDED, canonical_env


@dataclass(frozen=True)
class Decision:
    """页面上对一张图的决定。两个下拉都默认空着，空着就是没点。

    `pcname` / `number` 是组头选定机器后带出来的那一份；空着就用文件名解析出的。
    """

    filename: str
    env: str = ""
    category: str = ""
    pcname: str = ""
    number: str = ""


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


@dataclass(frozen=True)
class _Candidate:
    """一张待编号的图：目标名与它的时间片段（当天第几秒）。"""

    copy: PlannedCopy
    seconds: int


def plan_batch(
    scan: ScanResult, decisions: Sequence[Decision], target_directory: str
) -> Plan:
    """按扫描顺序逐张过一遍决定，分成能落盘与落不了盘两摞。"""
    by_filename = {decision.filename: decision for decision in decisions}

    candidates: list[_Candidate] = []
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
        pcname = (decision.pcname or "").strip() or parsed.pcname
        number = (decision.number or "").strip() or parsed.number
        candidates.append(
            _Candidate(
                copy=PlannedCopy(
                    source_filename=image.filename,
                    target_name=build_target_name(
                        number=number, pcname=pcname, env=env, category=category
                    ),
                    pcname=pcname,
                    env=env,
                    category=category,
                ),
                seconds=parsed.seconds,
            )
        )

    return Plan(
        source_directory=scan.directory,
        target_directory=target_directory,
        ready=tuple(_number_collisions(candidates)),
        blocked=tuple(blocked),
    )


def _number_collisions(candidates: Sequence[_Candidate]) -> list[PlannedCopy]:
    """同名候选排个号：首张原样，第二张起 `-2`、`-3`。

    排序只认文件名里的时间片段（`seconds`）；同一秒再按文件名，纯粹为了结果稳定——
    同秒本来就没有先后可言。不看 mtime，也不看落盘先后：编号只为防撞名，
    改文件时间戳不该改变谁拿 `-2`。不同机器、不同类别、不同 ENV 的目标名本来就不同，
    自然不会共用一个计数器。
    """
    indexes_by_name: dict[str, list[int]] = {}
    for index, candidate in enumerate(candidates):
        indexes_by_name.setdefault(candidate.copy.target_name, []).append(index)

    numbered = [candidate.copy for candidate in candidates]
    for name, indexes in indexes_by_name.items():
        if len(indexes) < 2:
            continue
        in_time_order = sorted(
            indexes,
            key=lambda i: (candidates[i].seconds, candidates[i].copy.source_filename),
        )
        for rank, index in enumerate(in_time_order, start=1):
            numbered[index] = replace(numbered[index], target_name=with_sequence(name, rank))

    return numbered

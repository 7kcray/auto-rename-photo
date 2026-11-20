"""计划器（纯函数）：扫描结果 + 逐张决定 → 目标文件名清单与阻塞原因。

只管「谁叫什么、谁被挡在门外」，不碰磁盘。落盘由 executor 按这份清单执行。
挡住的图只影响它自己：未定一张，其余照样落盘。
"""

from dataclasses import dataclass, replace
from typing import Sequence

from autorename.naming import build_target_name, with_sequence
from autorename.scanner import ScanResult
from autorename.vocabulary import (
    CATEGORIES,
    UNDECIDED,
    canonical_env,
    is_ultraviewer_id,
    is_valid_pcname,
)


@dataclass(frozen=True)
class Decision:
    """页面上对一张图的决定。两个下拉都默认空着，空着就是没点。

    `pcname` / `ultraviewer_id` 是页面上带出来的那一份：组头选定的机器、本卡手改的
    PCNAME、手输的 ID，三处都从这里下来。空着就用文件名解析出的——文件名不合规时
    没有可回退的值，缺什么就挡什么。手改的 PCNAME 会原样进文件名，所以它也得过
    「合法 PCNAME」那一关。
    """

    filename: str
    env: str = ""
    category: str = ""
    pcname: str = ""
    ultraviewer_id: str = ""


@dataclass(frozen=True)
class PlannedCopy:
    """一张可以落盘的图：从哪个名字复制成哪个名字。

    `ultraviewer_id` 单独留一份，是为了日志能单列一栏，不必回头从目标文件名里拆。
    """

    source_filename: str
    target_name: str
    pcname: str
    env: str
    category: str
    ultraviewer_id: str


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
    """一张待编号的图：目标名与它的时间片段（当天第几秒）。

    不合规的图没有时间片段，`seconds` 是 None——排号时排到最后。
    """

    copy: PlannedCopy
    seconds: int | None


def plan_batch(
    scan: ScanResult, decisions: Sequence[Decision], target_directory: str
) -> Plan:
    """按扫描顺序逐张过一遍决定，分成能落盘与落不了盘两摞。

    文件名不合规不再直接判死：只要人把缺的那几项补齐（Ultraviewer ID、PCNAME、
    类别、ENV），它就和合规的图一样进落盘清单；没补齐的照旧挡住，只影响它自己。
    """
    by_filename = {decision.filename: decision for decision in decisions}

    candidates: list[_Candidate] = []
    blocked: list[BlockedImage] = []

    for image in scan.images:
        decision = by_filename.get(image.filename) or Decision(image.filename)
        parsed = image.parsed

        env = canonical_env(decision.env)
        category = decision.category
        # 页面带出的（手输 ID、组头选机器）优先，空着才回退文件名解析出的；
        # 文件名不合规时没有可回退的值，缺什么就挡什么。
        pcname = (decision.pcname or "").strip() or (parsed.pcname if parsed else "")
        ultraviewer_id = (decision.ultraviewer_id or "").strip() or (
            parsed.ultraviewer_id if parsed else ""
        )

        problems = _problems_of(category, env, pcname, ultraviewer_id)
        if problems:
            blocked.append(BlockedImage(image.filename, "、".join(problems)))
            continue

        candidates.append(
            _Candidate(
                copy=PlannedCopy(
                    source_filename=image.filename,
                    target_name=build_target_name(
                        ultraviewer_id=ultraviewer_id, pcname=pcname, env=env, category=category
                    ),
                    pcname=pcname,
                    env=env,
                    category=category,
                    ultraviewer_id=ultraviewer_id,
                ),
                seconds=parsed.seconds if parsed else None,
            )
        )

    return Plan(
        source_directory=scan.directory,
        target_directory=target_directory,
        ready=tuple(_disambiguate_collisions(candidates)),
        blocked=tuple(blocked),
    )


def _problems_of(category: str, env: str, pcname: str, ultraviewer_id: str) -> list[str]:
    """挡住一张图的理由；空列表就是可以落盘。

    文件名不合规的图在这里补齐：缺 ID、缺 PCNAME 各算一条，人补哪一条就少哪一条。
    合规的图通常从文件名就能补齐这两项，所以只会因类别或 ENV 被挡；组头选了机器时，
    这两项改由登记带出，同样不会缺。

    手改的 PCNAME 会原样进文件名，所以填进来的非法字符也算一条挡住的理由——
    这一关不能只靠页面标红。
    """
    problems: list[str] = []
    if not category or category == UNDECIDED:
        problems.append("类别未定")
    elif category not in CATEGORIES:
        problems.append(f"类别不在词表里：{category}")
    if not env:
        problems.append("ENV 未选")
    if not pcname:
        problems.append("PCNAME 未定")
    elif not is_valid_pcname(pcname):
        # 页面会标红，但绕过页面直接打 API 也得挡住：名字会原样进文件名。
        problems.append(f"PCNAME 含非法字符：{pcname}")
    if not ultraviewer_id:
        problems.append("Ultraviewer ID 未填")
    elif not is_ultraviewer_id(ultraviewer_id):
        problems.append(f"Ultraviewer ID 必须是纯数字：{ultraviewer_id}")
    return problems


def _disambiguate_collisions(candidates: Sequence[_Candidate]) -> list[PlannedCopy]:
    """同名候选排个号：首张原样，第二张起 `-2`、`-3`。

    排序只认文件名里的时间片段（`seconds`）；同一秒再按文件名，纯粹为了结果稳定——
    同秒本来就没有先后可言。没有时间片段的手动补全图排在最后，彼此按文件名。
    不看 mtime，也不看落盘先后：编号只为防撞名，改文件时间戳不该改变谁拿 `-2`。
    不同机器、不同类别、不同 ENV 的目标名本来就不同，自然不会共用一个计数器。
    """
    indexes_by_name: dict[str, list[int]] = {}
    for index, candidate in enumerate(candidates):
        indexes_by_name.setdefault(candidate.copy.target_name, []).append(index)

    final = [candidate.copy for candidate in candidates]
    for name, indexes in indexes_by_name.items():
        if len(indexes) < 2:
            continue
        in_time_order = sorted(
            indexes,
            key=lambda i: (
                candidates[i].seconds is None,
                candidates[i].seconds or 0,
                candidates[i].copy.source_filename,
            ),
        )
        for rank, index in enumerate(in_time_order, start=1):
            final[index] = replace(final[index], target_name=with_sequence(name, rank))

    return final

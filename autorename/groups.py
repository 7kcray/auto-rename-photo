"""扫描结果按机器分组：组头写清顾客与机器，一眼看出哪张图属于哪台机器。

分组只解决「别把客户端的图记到服务器名下」：机器由文件名里的 PCNAME + Ultraviewer ID
决定，绝不从屏幕内容猜。没登记过的机器自成一个组，文件名不合规的图另放最后一组——
那一组没有文件名可依据，PCNAME 靠组头选机器补，ID 靠人填。

ENV 线索贴在每张图旁边，只提示、不预填——分组不替人点 ENV。
"""

from dataclasses import dataclass
from typing import Sequence

from autorename.machines import Machine, MachineRegistry, env_hint
from autorename.scanner import ScanResult, ScannedImage

UNREGISTERED_LABEL = "未登记"
NON_COMPLIANT_LABEL = "不合规"


@dataclass(frozen=True)
class ImageGroup:
    """一组同一台机器的图。`machine_index` 指向登记表里的那台机器，没有就是未登记。"""

    customer: str
    label: str
    pcname: str
    ultraviewer_id: str
    machine_index: int | None
    images: tuple[ScannedImage, ...]

    @property
    def registered(self) -> bool:
        return self.machine_index is not None

    @property
    def non_compliant(self) -> bool:
        """这一组是不是「文件名不合规」那组。按组名认，不从「PCNAME 恰好为空」反推。"""
        return self.label == NON_COMPLIANT_LABEL

    def to_payload(self) -> dict:
        return {
            "customer": self.customer,
            "label": self.label,
            "pcname": self.pcname,
            "ultraviewer_id": self.ultraviewer_id,
            "machine_index": self.machine_index,
            "registered": self.registered,
            # 不合规组没有 PCNAME 可依据：页面据此决定要不要给组头配「机器」下拉。
            "non_compliant": self.non_compliant,
            "images": [image.filename for image in self.images],
        }


def group_images(
    images: Sequence[ScannedImage], registry: MachineRegistry
) -> tuple[ImageGroup, ...]:
    """按（PCNAME, Ultraviewer ID）分堆；顺序是登记顺序 → 未登记（按出现先后）→ 不合规。"""
    buckets: dict[tuple[str, str], list[ScannedImage]] = {}
    appearance: dict[tuple[str, str], int] = {}

    for image in images:
        key = _key_of(image)
        if key not in buckets:
            buckets[key] = []
            appearance[key] = len(appearance)
        buckets[key].append(image)

    ranks = _registry_ranks(registry)
    ordered = sorted(buckets, key=lambda key: _order_key(key, appearance[key], ranks))

    return tuple(_group_of(key, buckets[key], registry) for key in ordered)


def build_payload(scan: ScanResult, registry: MachineRegistry) -> dict:
    """扫描结果的页面载荷：逐张线索 + 分组 + 可选的机器清单。"""
    payload = scan.to_payload()

    hints = {
        image.filename: env_hint(image.ocr_text, registry, own=_machine_of(image, registry))
        for image in scan.images
    }
    for item in payload["images"]:
        item["env_hint"] = hints.get(item["filename"])

    payload["groups"] = [group.to_payload() for group in group_images(scan.images, registry)]
    payload["machines"] = [machine.to_payload() for machine in registry.machines]
    if registry.warning:
        payload["machine_warning"] = registry.warning
    return payload


def _group_of(
    key: tuple[str, str], members: list[ScannedImage], registry: MachineRegistry
) -> ImageGroup:
    pcname, ultraviewer_id = key
    if not pcname:
        return ImageGroup("", NON_COMPLIANT_LABEL, "", "", None, tuple(members))

    index = registry.index_of(pcname, ultraviewer_id)
    if index is None:
        return ImageGroup("", UNREGISTERED_LABEL, pcname, ultraviewer_id, None, tuple(members))

    machine = registry.machines[index]
    return ImageGroup(machine.customer, machine.label, pcname, ultraviewer_id, index, tuple(members))


def _machine_of(image: ScannedImage, registry: MachineRegistry) -> Machine | None:
    parsed = image.parsed
    if parsed is None:
        return None
    return registry.find(parsed.pcname, parsed.ultraviewer_id)


def _key_of(image: ScannedImage) -> tuple[str, str]:
    parsed = image.parsed
    if parsed is None:
        return ("", "")
    return (parsed.pcname, parsed.ultraviewer_id)


def _registry_ranks(registry: MachineRegistry) -> dict[tuple[str, str], int]:
    """登记顺序；PCNAME 与 Ultraviewer ID 都对上才算同一台机器。"""
    ranks: dict[tuple[str, str], int] = {}
    for index, machine in enumerate(registry.machines):
        ranks.setdefault((machine.pcname.casefold(), machine.ultraviewer_id), index)
    return ranks


def _order_key(
    key: tuple[str, str], appeared: int, ranks: dict[tuple[str, str], int]
) -> tuple[int, int, int]:
    pcname, ultraviewer_id = key
    if not pcname:
        return (2, 0, appeared)
    rank = ranks.get((pcname.casefold(), ultraviewer_id))
    if rank is None:
        return (1, appeared, 0)
    return (0, rank, appeared)

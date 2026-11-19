"""扫描结果按机器分组：组头写清顾客与机器，一眼看出哪张图属于哪台机器。

分组只解决「别把客户端的图记到服务器名下」：机器由文件名里的 PCNAME + 数字
决定，绝不从屏幕内容猜。没登记过的机器自成一个组，文件名不合规的图另放最后一组。

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
    number: str
    machine_index: int | None
    images: tuple[ScannedImage, ...]

    @property
    def registered(self) -> bool:
        return self.machine_index is not None

    def to_payload(self) -> dict:
        return {
            "customer": self.customer,
            "label": self.label,
            "pcname": self.pcname,
            "number": self.number,
            "machine_index": self.machine_index,
            "registered": self.registered,
            "images": [image.filename for image in self.images],
        }


def group_images(
    images: Sequence[ScannedImage], registry: MachineRegistry
) -> tuple[ImageGroup, ...]:
    """按（PCNAME, 数字）分堆；顺序是登记顺序 → 未登记（按出现先后）→ 不合规。"""
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
    pcname, number = key
    if not pcname:
        return ImageGroup("", NON_COMPLIANT_LABEL, "", "", None, tuple(members))

    index = registry.index_of(pcname, number)
    if index is None:
        return ImageGroup("", UNREGISTERED_LABEL, pcname, number, None, tuple(members))

    machine = registry.machines[index]
    return ImageGroup(machine.customer, machine.label, pcname, number, index, tuple(members))


def _machine_of(image: ScannedImage, registry: MachineRegistry) -> Machine | None:
    parsed = image.parsed
    if parsed is None:
        return None
    return registry.find(parsed.pcname, parsed.number)


def _key_of(image: ScannedImage) -> tuple[str, str]:
    parsed = image.parsed
    if parsed is None:
        return ("", "")
    return (parsed.pcname, parsed.number)


def _registry_ranks(registry: MachineRegistry) -> dict[tuple[str, str], int]:
    """登记顺序；PCNAME 与数字都对上才算同一台机器。"""
    ranks: dict[tuple[str, str], int] = {}
    for index, machine in enumerate(registry.machines):
        ranks.setdefault((machine.pcname.casefold(), machine.number), index)
    return ranks


def _order_key(
    key: tuple[str, str], appeared: int, ranks: dict[tuple[str, str], int]
) -> tuple[int, int, int]:
    pcname, number = key
    if not pcname:
        return (2, 0, appeared)
    rank = ranks.get((pcname.casefold(), number))
    if rank is None:
        return (1, appeared, 0)
    return (0, rank, appeared)

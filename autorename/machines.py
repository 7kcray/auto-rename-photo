r"""机器登记：从本地配置读「顾客 → 机器」，以及从 OCR 文本看出的 ENV 线索。

每台机器带 PCNAME、Ultraviewer ID，和一个用于匹配 UNC 前缀的机器名（`hostname` 缺省就是
PCNAME）。配置缺失或格式坏掉时给出能读懂的一句话，不崩整批：本批的图全归到
「未登记」组，ENV 照常逐张点。

线索只提示，不预填：图里出现 `\\<别的机器名>\` 说明它是在客户端上拍的（要访问
那台机器上的共享）；引用的正是本机共享、或者出现本地盘符 `C:\`，说明图就在
服务器本机。点哪一格仍由人决定。
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from autorename import config

_SHARE_PATH = re.compile(r"\\\\\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*\\")
_LOCAL_DRIVE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")

_UNREGISTERED_SUFFIX = "本批的图都归到「未登记」组，ENV 照常逐张点。"
_MISSING = "还没有机器登记：找不到 {path}。" + _UNREGISTERED_SUFFIX
_UNREADABLE = "机器登记读不了（{error}）：{path}。" + _UNREGISTERED_SUFFIX
_NOT_AN_OBJECT = "机器登记格式不对：{path} 里应该是一个对象。" + _UNREGISTERED_SUFFIX
_NO_CUSTOMERS = "配置里还没有「顾客 → 机器」登记：{path}。" + _UNREGISTERED_SUFFIX
_CUSTOMERS_NOT_A_LIST = "配置里的 customers 应该是一个数组：{path}。" + _UNREGISTERED_SUFFIX
_NO_MACHINES = "配置里没有可用的「顾客 → 机器」登记：{path}。" + _UNREGISTERED_SUFFIX
_SKIPPED = "有 {count} 条机器登记格式不对，已跳过：{path}。"


@dataclass(frozen=True)
class Machine:
    """一台登记过的机器：属于哪个顾客、叫什么、PCNAME 与 Ultraviewer ID、UNC 里怎么出现。"""

    customer: str
    label: str
    pcname: str
    ultraviewer_id: str
    hostname: str

    def to_payload(self) -> dict:
        return {
            "customer": self.customer,
            "label": self.label,
            "pcname": self.pcname,
            "ultraviewer_id": self.ultraviewer_id,
            "hostname": self.hostname,
        }


@dataclass(frozen=True)
class MachineRegistry:
    """配置里的全部机器，以及读配置时要说给用户听的一句话。"""

    machines: tuple[Machine, ...] = ()
    path: str = ""
    warning: str | None = None

    def index_of(self, pcname: str, ultraviewer_id: str) -> int | None:
        """按 PCNAME + Ultraviewer ID 找机器。ID 是机器身份的一部分，不猜。"""
        name = _as_text(pcname).casefold()
        wanted = _as_text(ultraviewer_id)
        if not name or not wanted:
            return None

        for index, machine in enumerate(self.machines):
            if machine.pcname.casefold() == name and machine.ultraviewer_id == wanted:
                return index
        return None

    def find(self, pcname: str, ultraviewer_id: str) -> Machine | None:
        index = self.index_of(pcname, ultraviewer_id)
        return self.machines[index] if index is not None else None

    def find_by_hostname(self, hostname: str) -> Machine | None:
        key = _as_text(hostname).casefold()
        if not key:
            return None
        for machine in self.machines:
            if machine.hostname.casefold() == key:
                return machine
        return None


def load_registry(path: Path | None = None) -> MachineRegistry:
    resolved = Path(path) if path is not None else config.config_path()
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _failed(resolved, _MISSING.format(path=resolved))
    except (OSError, ValueError) as error:
        return _failed(resolved, _UNREADABLE.format(error=error, path=resolved))

    if not isinstance(raw, dict):
        return _failed(resolved, _NOT_AN_OBJECT.format(path=resolved))

    customers = raw.get(config.CUSTOMERS_KEY)
    if customers is None:
        return _failed(resolved, _NO_CUSTOMERS.format(path=resolved))
    if not isinstance(customers, list):
        return _failed(resolved, _CUSTOMERS_NOT_A_LIST.format(path=resolved))

    machines, skipped = _read_customers(customers)
    if not machines:
        return _failed(resolved, _NO_MACHINES.format(path=resolved))

    warning = _SKIPPED.format(count=skipped, path=resolved) if skipped else None
    return MachineRegistry(machines=machines, path=str(resolved), warning=warning)


def env_hint(text: str, registry: MachineRegistry, own: Machine | None = None) -> str | None:
    """从 OCR 文本里读 ENV 线索。只给一句提示，不替人选 ENV。

    `own` 是这张图按文件名认出来的机器：它引用的若是自己的共享，那是服务器本机。
    """
    if not text:
        return None

    share = _SHARE_PATH.search(text)
    if share:
        host = share.group(1)
        if own is not None and own.hostname.casefold() == host.casefold():
            return f"疑似服务器：引用了本机共享 \\\\{host}\\"

        machine = registry.find_by_hostname(host)
        where = f"（{machine.customer} · {machine.label}）" if machine else ""
        return f"疑似客户端：引用了 \\\\{host}\\ 共享{where}"

    drive = _LOCAL_DRIVE.search(text)
    if drive:
        return f"疑似服务器：出现本地盘符 {drive.group(0)}"

    return None


def _failed(resolved: Path, message: str) -> MachineRegistry:
    return MachineRegistry(path=str(resolved), warning=message)


def _read_customers(customers: list) -> tuple[tuple[Machine, ...], int]:
    machines: list[Machine] = []
    skipped = 0

    for customer in customers:
        if not isinstance(customer, dict):
            skipped += 1
            continue

        name = _as_text(customer.get("name"))
        listed = customer.get("machines")
        if not name or not isinstance(listed, list):
            skipped += 1
            continue

        for entry in listed:
            machine = _machine_of(name, entry)
            if machine is None:
                skipped += 1
                continue
            machines.append(machine)

    return tuple(machines), skipped


def _machine_of(customer: str, entry: object) -> Machine | None:
    if not isinstance(entry, dict):
        return None

    pcname = _as_text(entry.get("pcname"))
    ultraviewer_id = _as_text(entry.get("ultraviewer_id"))
    if not pcname or not ultraviewer_id:
        return None

    label = _as_text(entry.get("label")) or pcname
    hostname = _as_text(entry.get("hostname")) or pcname
    return Machine(customer=customer, label=label, pcname=pcname, ultraviewer_id=ultraviewer_id, hostname=hostname)


def _as_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return ""

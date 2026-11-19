"""分类器（纯函数）：OCR 文本 → 7 类之一，或「未定」。

规则按优先级排序，第一条命中就收工。顺序不是随手排的：

- `Analyse` 最先：分析结果页里到处是 `Data`、`Version`、`Logon`。
- `Group` 在 `Data` 前面：`SQL Account Database Group` 里有个 `Database`。
- `Spec` 在 `Version` 前面：规格页上写着 `Version 22H2`。
- `Main` 最后：桌面触发词最泛（`This PC`、`Recycle Bin`），放前面会吞掉别的页。
  `This PC` 单独出现算 `Spec`（「此电脑」规格页），但桌面截图里有回收站、
  搜索框，那是主屏——所以 `Spec` 那条规则带一个排除条件。

判不出来一律 `未定`：宁可让人点一下，也不猜一个错类别。
产出只会是 `CATEGORIES` 里的词或 `UNDECIDED`，`Database` / `Goup` 一个字都不会流出去。
"""

from dataclasses import dataclass
from typing import Iterable

from autorename.vocabulary import CATEGORIES, UNDECIDED


@dataclass(frozen=True)
class Rule:
    """一条规则：文本里出现任一触发词就算命中；出现任一排除词则跳过。"""

    category: str
    phrases: tuple[str, ...]
    unless: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # 词表只有一份：规则写错一个类别名，导入时就炸，不会漏到文件名里。
        if self.category not in CATEGORIES:
            raise ValueError(f"类别不在封闭词表里：{self.category!r}")


RULES: tuple[Rule, ...] = (
    Rule(
        "Analyse",
        (
            "analyse data integrity",
            "analyze data integrity",
            "data integrity",
            "start analyse",
            "start analyze",
            "analyse items",
            "analyze items",
            "analyse completed",
        ),
    ),
    Rule(
        "Group",
        (
            "sql account database group",
            "dcf group",
            "create group",
            "add group",
            "goup",
        ),
    ),
    Rule(
        "Spec",
        (
            "device specifications",
            "windows specifications",
            "rename this pc",
            "projecting to this pc",
            "installed ram",
            "device name",
            "system type",
            "product id",
            "this pc",
        ),
        unless=("recycle bin", "type here to search"),
    ),
    Rule(
        "Test",
        (
            "test connection",
            "connection status",
            "connection active",
            "firebird server configuration",
            "elapsed time",
        ),
    ),
    Rule(
        "Data",
        (
            "dcf database",
            "create new database",
            "create sample database",
            "find database",
            "add database link",
            "database folder",
            "database engine",
            "database",
        ),
    ),
    Rule(
        "Version",
        (
            "log on",
            "try demo",
            "local demo",
            "cloud demo",
        ),
    ),
    Rule(
        "Main",
        (
            "this pc",
            "recycle bin",
            "type here to search",
            "control panel",
            "learn about this picture",
        ),
    ),
)


def classify(text: Iterable[str] | str) -> str:
    """OCR 文本行 → 类别。空文本、认不出的文本都给「未定」。"""
    normalized = _normalize(text)
    if not normalized:
        return UNDECIDED

    for rule in RULES:
        if any(excluded in normalized for excluded in rule.unless):
            continue
        if any(phrase in normalized for phrase in rule.phrases):
            return rule.category

    return UNDECIDED


def _normalize(text: Iterable[str] | str) -> str:
    """收成一行小写文本：大小写不敏感，换行与多空格折成一个空格。"""
    if isinstance(text, str):
        joined = text
    else:
        joined = "\n".join(line for line in text if isinstance(line, str))
    return " ".join(joined.casefold().split())

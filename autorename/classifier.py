"""分类器（纯函数）：OCR 文本 → 词表里的某一类，或「未定」。

词表 16 类，规则覆盖其中 12 类：前七个（`Analyse`、`Data`、`Group`、`Main`、`Spec`、
`Test`、`Version`）加后九个里的五个（`Financial_Date`、`Negative`、`License`、
`Report_Header`、`Bank`）。`SSM`、`TIN`、`Company_Profile`、`Other` 没有规则，
扫描后一律落在「未定」，由人逐张点。`Other` 尤其不许做兜底——它不在「未定」里，
兜底等于把认不出的图自动放过、直接落盘，拆掉「宁可让人点一下」这条底线。

一条规则可以有两类证据，命中任意一类就算数：

- `phrases`：归一化文本里的固定短语。OCR 会把界面文字读错（`File`→`Eile`、
  `Purchase`→`2urchase`、`Account`→`Account I`），所以短语要挑**读错概率低的整句标签**，
  不挑单词。单词级触发词是误判的主要来源。
- `shapes`：结构证据，对归一化文本跑的正则。许可证号那种「8 组 4 位、连字符分隔」的
  形状几乎不可能误撞，比任何短语都硬——标题被截掉、字被读丢，它照样能兜住。

只有两类值得写 `shapes`：格式本身有强辨识度（许可证号、注册号）。日期、银行、
负数没有可校验的格式，`1/4/2025` 这种形状满屏都是，拿它当证据只会制造误判——
所以那三类只用短语。

规则按优先级排序，第一条命中就收工。顺序不是随手排的：

- `Analyse` 最先：分析结果页里到处是 `Data`、`Version`、`Logon`。
- `Group` 在 `Data` 前面：`SQL Account Database Group` 里有个 `Database`。
- `License` 在 `Spec` 前面：激活窗口里有 `Product ID`，与规格页撞词；两者的分野是
  激活码/产品号，不是 `Product ID` 这四个字。
- `Spec` 在 `Version` 前面：规格页上写着 `Version 22H2`。
- `Financial_Date` 与 `Negative` 都是 `Options` 对话框（连标签页都一样），只能靠
  各自的字段/复选框文字区分：`Financial Start Period` 与 `Negative Stock Quantity`。
- `Report_Header` 的窗口标题就是 `Company Profile`——将来若给 `Company_Profile`
  加规则，必须排在它后面，否则这一页会被抢走。
- `Bank` 刻意不用 `Foreign Bank` / `Bank Reconciliation`：许可证窗口里这两个词都有。
- `Main` 最后：桌面触发词最泛（`This PC`、`Recycle Bin`），放前面会吞掉别的页。
  `This PC` 单独出现算 `Spec`（「此电脑」规格页），但桌面截图里有回收站、
  搜索框，那是主屏——所以 `Spec` 那条规则带一个排除条件。

判不出来一律 `未定`：宁可让人点一下，也不猜一个错类别。
产出只会是 `CATEGORIES` 里的词或 `UNDECIDED`，`Database` / `Goup` 一个字都不会流出去。
"""

import re
from dataclasses import dataclass, field
from typing import Iterable

from autorename.vocabulary import CATEGORIES, UNDECIDED

# 许可证号：8 组 4 位，连字符分隔（`VMKS-X8VP-…-JKCW`）。位数固定，误撞概率极低。
LICENSE_KEY = r"(?:[a-z0-9]{4}-){7}[a-z0-9]{4}"
# 产品号：`001.318299.2880.3224`。与 Windows 的 5 段产品 ID 形状不同，不会串。
PRODUCT_ID = r"\b\d{3}\.\d{6}\.\d{4}\.\d{4}\b"
# 注册号标签：OCR 会在 `Reg.` 的点、`(New)` 的空格上抖，形状放宽一点。
REGISTRATION_LABEL = r"reg\.?\s?no\s?\(new\)"


@dataclass(frozen=True)
class Rule:
    """一条规则：短语或结构命中任一即算命中；出现任一排除词则整条作废。"""

    category: str
    phrases: tuple[str, ...] = ()
    unless: tuple[str, ...] = ()
    shapes: tuple[str, ...] = ()
    _compiled: tuple[re.Pattern[str], ...] = field(
        init=False, repr=False, compare=False, default=()
    )

    def __post_init__(self) -> None:
        # 词表只有一份：规则写错一个类别名，导入时就炸，不会漏到文件名里。
        if self.category not in CATEGORIES:
            raise ValueError(f"类别不在封闭词表里：{self.category!r}")
        if not self.phrases and not self.shapes:
            # 两类证据都空 = 这条规则永远不可能命中，是写错了，不是「暂时不用」。
            raise ValueError(f"规则没有任何证据：{self.category!r}")
        try:
            compiled = tuple(re.compile(shape) for shape in self.shapes)
        except re.error as error:
            raise ValueError(f"规则的正则写坏了：{self.category!r} · {error}") from error
        object.__setattr__(self, "_compiled", compiled)

    def matches(self, normalized: str) -> bool:
        """归一化文本是否命中：排除词先否决，再比短语，最后比结构。"""
        if any(excluded in normalized for excluded in self.unless):
            return False
        if any(phrase in normalized for phrase in self.phrases):
            return True
        return any(pattern.search(normalized) for pattern in self._compiled)


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
    # 激活窗口：`Product ID` 与规格页撞词，所以排在 Spec 前面；
    # 短语被读坏时，32 位的许可证号还能独立作证。
    Rule(
        "License",
        (
            "product activation",
            "activation code",
            "print activation request",
            "registration successful",
        ),
        shapes=(LICENSE_KEY, PRODUCT_ID),
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
    # 总账选项里的「财务起始期间」——与 Negative 同为 Options 对话框，靠这个标签分开。
    Rule(
        "Financial_Date",
        (
            "financial start period",
            "system conversion date",
        ),
    ),
    Rule(
        "Negative",
        (
            "negative stock quantity",
            "prompt negative stock",
        ),
    ),
    # 窗口标题是 `Company Profile`，但这一页属于报表页眉——`Company_Profile` 的规则
    # 若将来要加，必须排在这条之后。
    Rule(
        "Report_Header",
        (
            "set report header",
            "report footer",
            "this software is licensed to company name",
        ),
        shapes=(REGISTRATION_LABEL,),
    ),
    # 只用 `Bank Account` / `Cash At Bank`：许可证窗口里也有 `Foreign Bank` 与
    # `Bank Reconciliation`，拿它们当判据会把激活页判成银行页。
    Rule(
        "Bank",
        (
            "bank account",
            "cash at bank",
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
        if rule.matches(normalized):
            return rule.category

    return UNDECIDED


def _normalize(text: Iterable[str] | str) -> str:
    """收成一行小写文本：大小写不敏感，换行与多空格折成一个空格。"""
    if isinstance(text, str):
        joined = text
    else:
        joined = "\n".join(line for line in text if isinstance(line, str))
    return " ".join(joined.casefold().split())

"""封闭词表：16 个类别、ENV 选项、ENV 的大小写规范，以及「什么算合法 PCNAME」。

类别是封闭的：判不准就留在「未定」，不允许出现同义异名——`Database` 归 `Data`、
`Goup` 归 `Group`，这两个错拼一个字都不许进文件名。

写法也固定：大小写按词表原样，不做归一。`SSM`、`TIN` 是缩写，`Ssm`、`Tin` 是错的；
`Financial_Date` 里的下划线也照留——它只影响肉眼扫目录，工具从不反解目标名。

ENV 的写法固定为「首字母大写、其余小写」：`Server`、`Link1`。配置里的默认值、
下拉里的显示文本、落盘文件名三处共用这一套写法，磁盘上旧示意稿的全大写不照抄。
"""

# 顺序不是随手排的：前七个是 OCR 认得的（规则见 classifier.py），后九个暂时只能手点。
# 后九个按业务含义排（财务 / 负数 / 执照 / 报告头 → 系统项 → 银行 / 公司 → 其他），
# 不按字母序重排——排出来的顺序比字母序更有信息量。
CATEGORIES = (
    "Analyse",
    "Data",
    "Group",
    "Main",
    "Spec",
    "Test",
    "Version",
    "Financial_Date",
    "Negative",
    "License",
    "Report_Header",
    "SSM",
    "TIN",
    "Bank",
    "Company_Profile",
    "Other",
)
UNDECIDED = "未定"
DEFAULT_ENVS = ("Server", "Link1", "Link2", "Link3")

# Windows 文件名里不许出现的九个字符。PCNAME 会原样进目标文件名，所以它也得躲开它们。
PCNAME_FORBIDDEN = '\\/:*?"<>|'


def canonical_env(value: str) -> str:
    """把任意写法收成 `Server` / `Link1`；空串原样返回空串。"""
    text = (value or "").strip()
    if not text:
        return ""
    return text[:1].upper() + text[1:].lower()


def is_ultraviewer_id(value: str) -> bool:
    """Ultraviewer ID 只认 ASCII 数字。

    `str.isdigit()` 会放行全角数字和 `²`，它们进不了文件名——文件名里读到的、
    页面上手输的都得过这一关，所以判据只此一份。
    """
    return bool(value) and all("0" <= character <= "9" for character in value)


def is_valid_pcname(value: str) -> bool:
    """合法 PCNAME：去掉首尾空格后非空，且不含 Windows 文件名非法字符。

    大小写不做归一：`tcsb2` 就是 `tcsb2`，工具不替人改成 `TCSB2`。
    页面上的红框与服务端的拦截共用这一条判据，避免两边各说一套。
    """
    text = (value or "").strip()
    return bool(text) and not any(character in PCNAME_FORBIDDEN for character in text)

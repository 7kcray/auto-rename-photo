"""封闭词表：7 个类别、ENV 选项，以及 ENV 的大小写规范。

类别是封闭的：判不准就留在「未定」，不允许出现同义异名——`Database` 归 `Data`、
`Goup` 归 `Group`，这两个错拼一个字都不许进文件名。

ENV 的写法固定为「首字母大写、其余小写」：`Server`、`Link1`。配置里的默认值、
下拉里的显示文本、落盘文件名三处共用这一套写法，磁盘上旧示意稿的全大写不照抄。
"""

CATEGORIES = ("Analyse", "Data", "Group", "Main", "Spec", "Test", "Version")
UNDECIDED = "未定"
DEFAULT_ENVS = ("Server", "Link1", "Link2", "Link3")


def canonical_env(value: str) -> str:
    """把任意写法收成 `Server` / `Link1`；空串原样返回空串。"""
    text = (value or "").strip()
    if not text:
        return ""
    return text[:1].upper() + text[1:].lower()

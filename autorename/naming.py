"""目标文件名：`(ENV)数字_PCNAME-类别.png`。

日期段丢弃——它既不是截图时间也不是需要的字段；扩展名恒为小写 `.png`。
ENV 在落笔这一刻再规范一次，配置里写错大小写也进不了文件名。

模板只此一份：页面的实时预览也用服务端发下去的 `TEMPLATE` 填，不另抄一遍。
"""

import os

from autorename.nameparse import PNG_EXTENSION
from autorename.vocabulary import CATEGORIES, canonical_env

TARGET_DIRECTORY_NAME = "Renamed"
TEMPLATE = "({env}){number}_{pcname}-{category}" + PNG_EXTENSION


def build_target_name(number: str, pcname: str, env: str, category: str) -> str:
    """拼一个目标文件名。ENV 空着、类别不在封闭词表里都算调用方出错。"""
    env_text = canonical_env(env)
    if not env_text:
        raise ValueError("ENV 不能为空")
    if category not in CATEGORIES:
        raise ValueError(f"类别不在封闭词表里：{category!r}")

    return TEMPLATE.format(env=env_text, number=number, pcname=pcname, category=category)


def default_target_directory(source_directory: str) -> str:
    """默认落盘目录是源目录下的 `Renamed/`。"""
    return os.path.join(source_directory, TARGET_DIRECTORY_NAME)

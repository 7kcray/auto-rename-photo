"""名称解析：系统生成的截图文件名 → Ultraviewer ID、PCNAME、时间片段。

文件名形如 `82331647_TCSB218112026_111024.png`，三段以 `_` 分隔：

- Ultraviewer ID：系统给的一串数字，屏幕上不存在，只能从文件名解。
- PCNAME + 日期：`TCSB2` + `18112026`（DDMMYYYY），日期段丢弃。
- 时间片段：`HHMMSS`，但时/分/秒三段都不补零，拼成一串——任一段小于 10 时
  那一位的 0 就没了。所以 5 位片段既可能是秒丢了 0（`11156` = 11:15:06），
  也可能是分丢了 0（`11835` = 11:08:35），不能硬解成 6 位。

解析是纯函数：不碰 IO、不抛异常，解不出就返回 None，由调用方标「不合规」。
"""

from dataclasses import dataclass

from autorename.vocabulary import is_ultraviewer_id

PNG_EXTENSION = ".png"


@dataclass(frozen=True)
class ParsedName:
    """一个合规文件名的解析结果。时间同时给原始片段和补零后的钟点。"""

    ultraviewer_id: str
    pcname: str
    time_fragment: str
    hour: int
    minute: int
    second: int

    @property
    def clock(self) -> str:
        return f"{self.hour:02d}:{self.minute:02d}:{self.second:02d}"

    @property
    def seconds(self) -> int:
        """当天第几秒。排序只用它，不碰 mtime。"""
        return self.hour * 3600 + self.minute * 60 + self.second


def parse_filename(filename: str) -> ParsedName | None:
    """解析文件名；不合规（缺段、非数字、日期或时间越界）时返回 None。"""
    stem = _strip_extension(filename)
    if stem is None:
        return None

    parts = stem.split("_")
    if len(parts) != 3:
        return None

    ultraviewer_id, machine_and_date, time_fragment = parts

    # 只认 ASCII 数字：全角 ID 会解析成「合规」，页面上却没有输入框可改，就成了死路。
    if not is_ultraviewer_id(ultraviewer_id):
        return None

    pcname = _pcname_of(machine_and_date)
    if pcname is None:
        return None

    clock = _parse_time_fragment(time_fragment)
    if clock is None:
        return None

    hour, minute, second = clock
    return ParsedName(
        ultraviewer_id=ultraviewer_id,
        pcname=pcname,
        time_fragment=time_fragment,
        hour=hour,
        minute=minute,
        second=second,
    )


def _strip_extension(filename: str) -> str | None:
    if not filename.lower().endswith(PNG_EXTENSION):
        return None
    return filename[: -len(PNG_EXTENSION)]


def _pcname_of(machine_and_date: str) -> str | None:
    """去掉尾部的 DDMMYYYY，剩下的就是 PCNAME。"""
    date_length = 8
    if len(machine_and_date) <= date_length:
        return None

    pcname = machine_and_date[:-date_length]
    date = machine_and_date[-date_length:]
    if not date.isdigit():
        return None

    day, month, year = int(date[:2]), int(date[2:4]), int(date[4:])
    if not (1 <= day <= 31 and 1 <= month <= 12 and year >= 1900):
        return None

    return pcname


def _parse_time_fragment(fragment: str) -> tuple[int, int, int] | None:
    """只认 5 位和 6 位：更短就是缺段，不是「丢了 0」。

    5 位时先按「秒丢了 0」读（`11156` → 11:15:06，规格举的例子），
    读不通再按「分丢了 0」读（`11835` → 11:08:35，实拍图里出现过）。
    """
    if not fragment.isdigit() or len(fragment) not in (5, 6):
        return None

    for hour_length in (2, 1):
        for minute_length in (2, 1):
            second_length = len(fragment) - hour_length - minute_length
            if not 1 <= second_length <= 2:
                continue

            hour = int(fragment[:hour_length])
            minute = int(fragment[hour_length : hour_length + minute_length])
            second = int(fragment[hour_length + minute_length :])
            if hour > 23 or minute > 59 or second > 59:
                continue

            return hour, minute, second

    return None

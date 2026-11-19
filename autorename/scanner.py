"""截图目录的扫描：目录 → 一批待处理的 PNG 条目。

只读：不重命名、不删除、不写入源目录。不合规的文件名照常入列，
只把解析结果留空，由页面标「不合规」，一张坏图不拖累整批。
"""

import os
from dataclasses import dataclass

from autorename.nameparse import PNG_EXTENSION, ParsedName, parse_filename


class DirectoryUnusable(Exception):
    """目录不存在、不是目录或读不了。消息直接给用户看。"""


@dataclass(frozen=True)
class ScannedImage:
    filename: str
    parsed: ParsedName | None

    @property
    def compliant(self) -> bool:
        return self.parsed is not None

    @property
    def sort_key(self) -> tuple:
        """合规的按时间片段升序，不合规的排到最后。"""
        if self.parsed is None:
            return (True, 0, self.filename)
        return (False, self.parsed.seconds, self.filename)

    def to_payload(self) -> dict:
        parsed = self.parsed
        return {
            "filename": self.filename,
            "compliant": self.compliant,
            "number": parsed.number if parsed else None,
            "pcname": parsed.pcname if parsed else None,
            "time_fragment": parsed.time_fragment if parsed else None,
            "clock": parsed.clock if parsed else None,
        }


@dataclass(frozen=True)
class ScanResult:
    directory: str
    images: list[ScannedImage]

    @property
    def compliant_count(self) -> int:
        return sum(1 for image in self.images if image.compliant)

    @property
    def non_compliant_count(self) -> int:
        return len(self.images) - self.compliant_count

    def to_payload(self) -> dict:
        return {
            "directory": self.directory,
            "count": len(self.images),
            "compliant_count": self.compliant_count,
            "non_compliant_count": self.non_compliant_count,
            "images": [image.to_payload() for image in self.images],
        }


def scan_directory(directory: str) -> ScanResult:
    """列出目录下的 PNG（扩展名大小写不敏感）并逐个解析文件名。"""
    resolved = os.path.abspath(os.path.expanduser(directory.strip().strip('"')))
    if not os.path.isdir(resolved):
        raise DirectoryUnusable(f"找不到目录：{directory}")

    try:
        names = os.listdir(resolved)
    except OSError as error:
        raise DirectoryUnusable(f"读不了目录：{directory}（{error.strerror}）") from error

    images = [
        ScannedImage(filename=name, parsed=parse_filename(name))
        for name in names
        if os.path.splitext(name)[1].lower() == PNG_EXTENSION
        and os.path.isfile(os.path.join(resolved, name))
    ]
    images.sort(key=lambda image: image.sort_key)

    return ScanResult(directory=resolved, images=images)

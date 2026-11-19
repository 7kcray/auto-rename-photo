"""截图目录的扫描：目录 → 一批待处理的 PNG 条目。

只读：不重命名、不删除、不写入源目录。不合规的文件名照常入列，只把解析结果留空，
由页面标「不合规」并留给人手动补全，一张坏图不拖累整批。

OCR 是可选的第二遍：给了 `OcrProvider` 就把每张图的文本读出来、预判类别，
填进页面下拉供人确认；不给就一律「未定」，其余行为完全一样。
"""

import os
from dataclasses import dataclass, replace

from autorename.classifier import classify
from autorename.nameparse import PNG_EXTENSION, ParsedName, parse_filename
from autorename.ocr import OcrProvider
from autorename.vocabulary import UNDECIDED


class DirectoryUnusable(Exception):
    """目录不存在、不是目录或读不了。消息直接给用户看。"""


@dataclass(frozen=True)
class ScannedImage:
    filename: str
    parsed: ParsedName | None
    ocr_text: str = ""
    predicted: str = UNDECIDED

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
            "ultraviewer_id": parsed.ultraviewer_id if parsed else None,
            "pcname": parsed.pcname if parsed else None,
            "time_fragment": parsed.time_fragment if parsed else None,
            "clock": parsed.clock if parsed else None,
            "predicted_category": self.predicted,
            "ocr_text": self.ocr_text,
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


def scan_directory(directory: str, ocr: OcrProvider | None = None) -> ScanResult:
    """列出目录下的 PNG（扩展名大小写不敏感）并逐个解析文件名。

    给了 `ocr` 再跑一遍识别：合规的、不合规的都读——不合规的图手动补全后一样要落盘，
    类别预判与 ENV 线索对它同样有用。
    """
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

    if ocr is not None:
        images = _with_predictions(images, resolved, ocr)

    return ScanResult(directory=resolved, images=images)


def _with_predictions(images: list[ScannedImage], directory: str, ocr: OcrProvider) -> list[ScannedImage]:
    """读一遍文本，把预判类别贴回每张图。读不出字的落在「未定」。

    不合规的图也读：它补全后一样要落盘，预判和线索没有理由只给合规的图。
    """
    if not images:
        return images

    texts = list(ocr.read_texts([os.path.join(directory, image.filename) for image in images]))
    texts += ["" for _ in range(len(images) - len(texts))]
    texts_by_name = dict(zip((image.filename for image in images), texts))

    annotated: list[ScannedImage] = []
    for image in images:
        text = texts_by_name.get(image.filename, "")
        annotated.append(replace(image, ocr_text=text, predicted=classify(text)))
    return annotated

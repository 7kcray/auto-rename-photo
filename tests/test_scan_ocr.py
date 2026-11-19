"""OCR 这条缝：换掉提供者，只影响「预判类别」，不影响落盘。

测试喂录好的文本，不跑真 OCR。
"""

import json
import tempfile
import unittest
from pathlib import Path

from autorename.ocr import WindowsOcr
from autorename.plan import Decision, plan_batch
from autorename.scanner import scan_directory
from autorename.vocabulary import UNDECIDED

FIXTURES = Path(__file__).parent / "fixtures" / "ocr_texts.json"
TARGET = "C:/shots/Renamed"

SPEC_IMAGE = "82331647_TCSB218112026_11835.png"
DATA_IMAGE = "82331647_TCSB218112026_111027.png"
BROKEN_IMAGE = "82331647_111024.png"


class RecordedOcr:
    """录好的文本：文件名 → 文本行。缺的就给空串。"""

    def __init__(self, texts: dict[str, list[str]]):
        self.texts = texts
        self.asked: list[str] = []

    def read_texts(self, paths):
        self.asked = [Path(path).name for path in paths]
        return ["\n".join(self.texts.get(Path(path).name, [])) for path in paths]


class ScanWithOcrTest(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.directory = Path(self._folder.name)
        self.texts = json.loads(FIXTURES.read_text(encoding="utf-8"))

    def tearDown(self):
        self._folder.cleanup()

    def _touch(self, *names: str) -> None:
        for name in names:
            (self.directory / name).write_bytes(b"png")

    def test_predicted_category_comes_from_the_recorded_text(self):
        self._touch(SPEC_IMAGE, DATA_IMAGE)

        result = scan_directory(str(self.directory), RecordedOcr(self.texts))
        predicted = {image.filename: image.predicted for image in result.images}

        self.assertEqual(predicted[SPEC_IMAGE], "Spec")
        self.assertEqual(predicted[DATA_IMAGE], "Data")

    def test_payload_carries_the_prediction_and_the_text_for_checking(self):
        self._touch(SPEC_IMAGE)

        image = scan_directory(str(self.directory), RecordedOcr(self.texts)).images[0]
        payload = image.to_payload()

        self.assertEqual(payload["predicted_category"], "Spec")
        self.assertIn("Rename this PC", payload["ocr_text"])

    def test_without_a_provider_every_row_stays_undecided(self):
        self._touch(SPEC_IMAGE)

        image = scan_directory(str(self.directory)).images[0]

        self.assertEqual(image.predicted, UNDECIDED)
        self.assertEqual(image.ocr_text, "")

    def test_non_compliant_filenames_are_sent_to_ocr_too(self):
        """不合规的图补全后一样要落盘，预判与 ENV 线索对它同样有用。"""
        self._touch(SPEC_IMAGE, BROKEN_IMAGE)
        provider = RecordedOcr(self.texts)

        scan_directory(str(self.directory), provider)

        self.assertEqual(sorted(provider.asked), sorted([SPEC_IMAGE, BROKEN_IMAGE]))

    def test_text_that_reads_nothing_leaves_the_row_undecided(self):
        self._touch(SPEC_IMAGE)

        image = scan_directory(str(self.directory), RecordedOcr({})).images[0]

        self.assertEqual(image.predicted, UNDECIDED)
        self.assertTrue(image.compliant)


class ProviderSwapTest(unittest.TestCase):
    """换 OCR 提供者不影响落盘：计划只看人点的下拉，不看预判。"""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.directory = Path(self._folder.name)
        self.texts = json.loads(FIXTURES.read_text(encoding="utf-8"))
        (self.directory / SPEC_IMAGE).write_bytes(b"png")

    def tearDown(self):
        self._folder.cleanup()

    def test_two_providers_produce_the_same_plan_for_the_same_decisions(self):
        decisions = [Decision(SPEC_IMAGE, env="Server", category="Spec")]

        with_ocr = plan_batch(scan_directory(str(self.directory), RecordedOcr(self.texts)), decisions, TARGET)
        without = plan_batch(scan_directory(str(self.directory)), decisions, TARGET)

        self.assertEqual(with_ocr.ready, without.ready)
        self.assertEqual(with_ocr.blocked, without.blocked)

    def test_a_wrong_prediction_never_reaches_the_target_name(self):
        """预判说 Spec，人改成 Test：落盘听人的。"""
        scan = scan_directory(str(self.directory), RecordedOcr(self.texts))
        plan = plan_batch(scan, [Decision(SPEC_IMAGE, env="Server", category="Test")], TARGET)

        self.assertEqual(plan.ready[0].target_name, "(Server)82331647_TCSB2-Test.png")


class WindowsOcrFallbackTest(unittest.TestCase):
    """OCR 脚本起不来时全部空串：扫描照常返回，人照样能手点。"""

    def test_failed_script_yields_one_empty_string_per_image(self):
        provider = WindowsOcr(runner=lambda script, paths, timeout: None)

        self.assertEqual(provider.read_texts(["a.png", "b.png"]), ["", ""])

    def test_no_images_means_no_subprocess(self):
        calls = []
        provider = WindowsOcr(runner=lambda script, paths, timeout: calls.append(paths) or [])

        self.assertEqual(provider.read_texts([]), [])
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()

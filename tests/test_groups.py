"""扫描结果按机器分组：组头写清顾客与机器，一眼看出哪张图属于哪台机器。

分组只解决「别把客户端的图记到服务器名下」，不替人点 ENV：每张图的 ENV 仍然
默认空着，线索只写在旁边。
"""

import unittest

from autorename.groups import build_payload, group_images
from autorename.machines import Machine, MachineRegistry
from autorename.nameparse import parse_filename
from autorename.scanner import ScanResult, ScannedImage
from autorename.vocabulary import UNDECIDED

SERVER_IMAGE = "82331647_TCSB218112026_111027.png"
CLIENT_IMAGE = "82335369_BB18112026_111042.png"
STRANGER_IMAGE = "99999999_ZZ18112026_111030.png"
BROKEN_IMAGE = "82331647_111024.png"

CLIENT_TEXT = "\\\\TCSB2\\eStream\\SQLAccounting\\Share\\Default.DCF"
SERVER_TEXT = "C:\\eStream\\SQLAccounting\\Share\\Default.DCF"

REGISTRY = MachineRegistry(
    machines=(
        Machine(customer="Akarumi", label="Server", pcname="TCSB2", ultraviewer_id="82331647", hostname="TCSB2"),
        Machine(customer="Akarumi", label="Link1", pcname="BB", ultraviewer_id="82335369", hostname="BB"),
    ),
    path="C:/config.json",
)


def _image(filename: str, text: str = "") -> ScannedImage:
    return ScannedImage(filename=filename, parsed=parse_filename(filename), ocr_text=text, predicted=UNDECIDED)


def _scan(*images: ScannedImage) -> ScanResult:
    return ScanResult(directory="C:/shots", images=list(images))


class GroupingTest(unittest.TestCase):
    def test_images_split_by_the_machine_in_their_filename(self):
        groups = group_images([_image(SERVER_IMAGE), _image(CLIENT_IMAGE)], REGISTRY)

        self.assertEqual([group.label for group in groups], ["Server", "Link1"])
        self.assertEqual([group.customer for group in groups], ["Akarumi", "Akarumi"])
        self.assertEqual([image.filename for image in groups[0].images], [SERVER_IMAGE])
        self.assertEqual([image.filename for image in groups[1].images], [CLIENT_IMAGE])
        self.assertTrue(all(group.registered for group in groups))

    def test_a_machine_that_is_not_registered_gets_its_own_group(self):
        groups = group_images([_image(STRANGER_IMAGE)], REGISTRY)

        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertFalse(group.registered)
        self.assertEqual(group.label, "未登记")
        self.assertEqual(group.customer, "")
        self.assertEqual(group.pcname, "ZZ")
        self.assertEqual(group.ultraviewer_id, "99999999")

    def test_a_known_pcname_with_another_id_stays_unregistered(self):
        """ID 对不上就不认这台机器，免得拿登记的 ID 悄悄改掉文件名里的。"""
        other = _image("88888888_BB18112026_111042.png")

        groups = group_images([other], REGISTRY)

        self.assertFalse(groups[0].registered)
        self.assertEqual(groups[0].pcname, "BB")
        self.assertEqual(groups[0].ultraviewer_id, "88888888")

    def test_non_compliant_images_form_their_own_trailing_group(self):
        groups = group_images([_image(BROKEN_IMAGE), _image(SERVER_IMAGE)], REGISTRY)

        self.assertEqual([group.label for group in groups], ["Server", "不合规"])
        self.assertEqual([image.filename for image in groups[-1].images], [BROKEN_IMAGE])
        self.assertFalse(groups[-1].registered)

    def test_registered_groups_follow_the_registry_order(self):
        groups = group_images([_image(CLIENT_IMAGE), _image(SERVER_IMAGE)], REGISTRY)

        self.assertEqual([group.label for group in groups], ["Server", "Link1"])

    def test_unregistered_groups_come_after_registered_ones(self):
        groups = group_images([_image(STRANGER_IMAGE), _image(CLIENT_IMAGE)], REGISTRY)

        self.assertEqual([group.label for group in groups], ["Link1", "未登记"])


class BatchPayloadTest(unittest.TestCase):
    def test_payload_carries_groups_machines_and_the_group_counts(self):
        payload = build_payload(_scan(_image(SERVER_IMAGE), _image(CLIENT_IMAGE)), REGISTRY)

        self.assertEqual(len(payload["groups"]), 2)
        self.assertEqual(len(payload["machines"]), 2)
        self.assertEqual(payload["groups"][0]["pcname"], "TCSB2")
        self.assertEqual(payload["groups"][0]["ultraviewer_id"], "82331647")
        self.assertEqual(payload["groups"][0]["machine_index"], 0)
        self.assertEqual(payload["groups"][1]["machine_index"], 1)
        self.assertEqual(payload["groups"][0]["images"], [SERVER_IMAGE])

    def test_each_image_carries_its_own_env_hint(self):
        payload = build_payload(
            _scan(_image(CLIENT_IMAGE, CLIENT_TEXT), _image(SERVER_IMAGE, SERVER_TEXT)), REGISTRY
        )
        hints = {item["filename"]: item["env_hint"] for item in payload["images"]}

        self.assertIn("疑似客户端", hints[CLIENT_IMAGE])
        self.assertIn("疑似服务器", hints[SERVER_IMAGE])

    def test_a_hint_never_prefills_the_env(self):
        payload = build_payload(_scan(_image(CLIENT_IMAGE, CLIENT_TEXT)), REGISTRY)

        self.assertNotIn("env", payload["images"][0])

    def test_the_non_compliant_group_is_flagged_for_the_page(self):
        """页面靠这个标记决定组头要不要配机器下拉、计数按哪一套文案算。"""
        payload = build_payload(_scan(_image(SERVER_IMAGE), _image(BROKEN_IMAGE)), REGISTRY)

        flags = {group["label"]: group["non_compliant"] for group in payload["groups"]}

        self.assertEqual(flags, {"Server": False, "不合规": True})

    def test_the_machine_list_spans_every_customer_for_the_non_compliant_group(self):
        """不合规组没有顾客归属：组头下拉得能选到任何顾客名下的机器。"""
        two_customers = MachineRegistry(
            machines=(
                Machine(customer="Akarumi", label="Server", pcname="TCSB2", ultraviewer_id="82331647", hostname="TCSB2"),
                Machine(customer="Bakery", label="Link1", pcname="BB", ultraviewer_id="82335369", hostname="BB"),
            ),
            path="C:/config.json",
        )

        payload = build_payload(_scan(_image(BROKEN_IMAGE)), two_customers)

        self.assertEqual(payload["groups"][0]["label"], "不合规")
        self.assertEqual(
            [(machine["customer"], machine["label"]) for machine in payload["machines"]],
            [("Akarumi", "Server"), ("Bakery", "Link1")],
        )

    def test_broken_config_warning_travels_with_the_payload(self):
        broken = MachineRegistry(path="C:/config.json", warning="机器登记读不了：C:/config.json")

        payload = build_payload(_scan(_image(CLIENT_IMAGE)), broken)

        self.assertEqual(payload["machine_warning"], broken.warning)
        self.assertEqual(payload["groups"][0]["label"], "未登记")


if __name__ == "__main__":
    unittest.main()

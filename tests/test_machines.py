r"""机器登记：从本地配置读「顾客 → 机器」，以及从 OCR 文本看出的 ENV 线索。

每台机器带 PCNAME、数字，和一个用于匹配 UNC 前缀的机器名（`hostname` 缺省就是
PCNAME）。配置缺失或格式坏掉时给出能读懂的一句话，不崩整批：本批的图全归到
「未登记」，ENV 照常逐张点。

线索只提示，不预填：UNC 前缀 `\\<机器名>\` 说明图是在客户端上拍的（它要访问
服务器上的共享），本地盘符 `C:\` 说明图就在服务器本机。判断留给点 ENV 的人。
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

from autorename.config import ensure_default_config
from autorename.machines import Machine, MachineRegistry, env_hint, load_registry

CLIENT_TEXT = "\n".join(
    [
        "Server Root Path:",
        "\\\\TCSB2\\eStream\\SQLAccounting\\Share\\Default.DCF",
    ]
)
SERVER_TEXT = "\n".join(
    [
        "Server Root Path:",
        "C:\\eStream\\SQLAccounting\\Share\\Default.DCF",
    ]
)


def _registry(*machines: Machine) -> MachineRegistry:
    return MachineRegistry(machines=tuple(machines), path="C:/config.json")


AKARUMI = _registry(
    Machine(customer="Akarumi", label="服务器", pcname="TCSB2", number="82331647", hostname="TCSB2"),
    Machine(customer="Akarumi", label="客户端", pcname="BB", number="82335369", hostname="BB"),
)


class RegistryFromConfigTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "config.json"

    def _write(self, payload: object) -> None:
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_reads_customers_and_their_machines(self):
        self._write(
            {
                "customers": [
                    {
                        "name": "Akarumi",
                        "machines": [
                            {"label": "服务器", "pcname": "TCSB2", "number": "82331647", "hostname": "TCSR2"},
                            {"label": "客户端", "pcname": "BB", "number": 82335369},
                        ],
                    }
                ]
            }
        )

        registry = load_registry(self.path)

        self.assertIsNone(registry.warning)
        self.assertEqual([machine.customer for machine in registry.machines], ["Akarumi", "Akarumi"])
        self.assertEqual([machine.label for machine in registry.machines], ["服务器", "客户端"])
        self.assertEqual(registry.machines[0].hostname, "TCSR2")
        self.assertEqual(registry.machines[1].number, "82335369")

    def test_hostname_falls_back_to_pcname(self):
        self._write({"customers": [{"name": "A", "machines": [{"pcname": "TCSB2", "number": "1"}]}]})

        machine = load_registry(self.path).machines[0]

        self.assertEqual(machine.hostname, "TCSB2")
        self.assertEqual(machine.label, "TCSB2")

    def test_missing_config_warns_and_offers_no_machines(self):
        registry = load_registry(self.path)

        self.assertEqual(registry.machines, ())
        self.assertIn(str(self.path), registry.warning)
        self.assertIn("未登记", registry.warning)

    def test_broken_json_warns_instead_of_raising(self):
        self.path.write_text("{ 这不是 JSON", encoding="utf-8")

        registry = load_registry(self.path)

        self.assertEqual(registry.machines, ())
        self.assertIn(str(self.path), registry.warning)

    def test_customers_that_are_not_a_list_warn(self):
        self._write({"customers": "Akarumi"})

        registry = load_registry(self.path)

        self.assertEqual(registry.machines, ())
        self.assertTrue(registry.warning)

    def test_malformed_machine_entries_are_skipped_one_by_one(self):
        self._write(
            {
                "customers": [
                    {
                        "name": "Akarumi",
                        "machines": [
                            {"label": "没有数字", "pcname": "X"},
                            {"label": "好的", "pcname": "BB", "number": "82335369"},
                            "这不是一台机器",
                        ],
                    }
                ]
            }
        )

        registry = load_registry(self.path)

        self.assertEqual([machine.pcname for machine in registry.machines], ["BB"])
        self.assertIn("跳过", registry.warning)

    def test_customers_without_a_single_usable_machine_warn(self):
        self._write({"customers": [{"name": "Akarumi", "machines": []}]})

        registry = load_registry(self.path)

        self.assertEqual(registry.machines, ())
        self.assertTrue(registry.warning)


class DefaultConfigTest(unittest.TestCase):
    def test_the_written_template_is_already_a_usable_registry(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "config.json"

        ensure_default_config(path)
        registry = load_registry(path)

        self.assertIsNone(registry.warning)
        self.assertTrue(registry.machines)
        self.assertTrue(all(machine.customer for machine in registry.machines))


class FindMachineTest(unittest.TestCase):
    def test_number_and_pcname_find_the_machine(self):
        self.assertEqual(AKARUMI.find("TCSB2", "82331647").label, "服务器")

    def test_pcname_is_matched_case_insensitively(self):
        self.assertEqual(AKARUMI.find("tcsb2", "82331647").label, "服务器")

    def test_a_new_number_does_not_borrow_another_machines_identity(self):
        """数字是机器身份的一部分：对不上就是没登记，不能拿登记的数字顶替。"""
        self.assertIsNone(AKARUMI.find("BB", "99999999"))

    def test_unknown_pcname_finds_nothing(self):
        self.assertIsNone(AKARUMI.find("ZZ", "82331647"))

    def test_hostname_finds_the_machine_behind_a_unc_prefix(self):
        self.assertEqual(AKARUMI.find_by_hostname("tcsb2").label, "服务器")


class EnvHintTest(unittest.TestCase):
    def test_unc_prefix_reads_as_a_client(self):
        hint = env_hint(CLIENT_TEXT, AKARUMI)

        self.assertIn("疑似客户端", hint)
        self.assertIn("\\\\TCSB2\\", hint)

    def test_the_hint_names_the_registered_machine_when_it_knows_it(self):
        self.assertIn("服务器", env_hint(CLIENT_TEXT, AKARUMI))

    def test_local_drive_reads_as_a_server(self):
        hint = env_hint(SERVER_TEXT, AKARUMI)

        self.assertIn("疑似服务器", hint)
        self.assertIn("C:\\", hint)

    def test_unc_wins_when_both_kinds_of_path_appear(self):
        self.assertIn("疑似客户端", env_hint(SERVER_TEXT + "\n" + CLIENT_TEXT, AKARUMI))

    def test_a_machine_referencing_its_own_share_reads_as_the_server(self):
        own = AKARUMI.machines[0]

        hint = env_hint(CLIENT_TEXT, AKARUMI, own=own)

        self.assertIn("疑似服务器", hint)
        self.assertIn("本机共享", hint)

    def test_an_unregistered_share_still_reads_as_a_client(self):
        self.assertIn("疑似客户端", env_hint("\\\\OTHERPC\\share\\x.dcf", AKARUMI))

    def test_plain_screen_text_gives_no_hint(self):
        self.assertIsNone(env_hint("SQL Account Database\nBackup\nRestore", AKARUMI))

    def test_ocr_noise_with_single_backslashes_is_not_a_share(self):
        self.assertIsNone(env_hint("B2 \\eSt rea m KSO LAccountina\\S ha Default. DCF", AKARUMI))

    def test_empty_text_gives_no_hint(self):
        self.assertIsNone(env_hint("", AKARUMI))

    def test_drive_hint_works_without_any_registry(self):
        self.assertIn("疑似服务器", env_hint(SERVER_TEXT, MachineRegistry()))


if __name__ == "__main__":
    unittest.main()

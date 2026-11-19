"""页面看到的预览名，必须与落盘时真正写下去的名字一模一样。

预览走 `/api/preview`，落盘走 `/api/rename`，两条路共用同一个计划器——
这里从 HTTP 这一层钉住它们不会分叉，尤其是同机同类的 `-2`、`-3` 编号。
"""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from autorename.server import create_server

PNG_BODY = b"\x89PNG\r\n\x1a\n" + b"body" * 20
NAMES = [f"82331647_TCSB218112026_1110{second}.png" for second in ("24", "27", "30")]


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "shots"
        self.source.mkdir()

        self.server = create_server(0, str(self.source))
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def make_source(self, *filenames: str) -> None:
        for filename in filenames:
            (self.source / filename).write_bytes(PNG_BODY + filename.encode())

    def post(self, route: str, payload: dict) -> dict:
        request = urllib.request.Request(
            self.base + route,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))

    def decisions(self, *filenames: str) -> dict:
        return {
            "directory": str(self.source),
            "decisions": [
                {
                    "filename": name,
                    "env": "Server",
                    "category": "Spec",
                    "pcname": "",
                    "ultraviewer_id": "",
                }
                for name in filenames
            ],
        }


class PreviewTest(ServerTestCase):
    def test_preview_names_are_exactly_the_names_the_batch_lands(self):
        self.make_source(*NAMES)
        body = self.decisions(*NAMES)

        preview = self.post("/api/preview", body)
        landed = self.post("/api/rename", body)

        self.assertEqual(
            [item["target"] for item in preview["ready"]],
            [
                "(Server)82331647_TCSB2-Spec.png",
                "(Server)82331647_TCSB2-Spec-2.png",
                "(Server)82331647_TCSB2-Spec-3.png",
            ],
        )
        self.assertEqual(
            {item["source"]: item["target"] for item in preview["ready"]},
            {row["source"]: row["target"] for row in landed["rows"]},
        )
        self.assertEqual(
            sorted(path.name for path in (self.source / "Renamed").glob("*.png")),
            sorted(item["target"] for item in preview["ready"]),
        )

    def test_preview_writes_nothing(self):
        self.make_source(*NAMES)

        self.post("/api/preview", self.decisions(*NAMES))

        self.assertFalse((self.source / "Renamed").exists())
        self.assertEqual(sorted(path.name for path in self.source.glob("*.png")), sorted(NAMES))

    def test_undecided_images_are_left_out_instead_of_being_named(self):
        self.make_source(*NAMES)
        body = self.decisions(*NAMES)
        body["decisions"][1]["category"] = "未定"

        preview = self.post("/api/preview", body)

        self.assertEqual(
            [item["source"] for item in preview["ready"]], [NAMES[0], NAMES[2]]
        )


class NonCompliantCompletionTest(ServerTestCase):
    """文件名不合规的图补齐后走同一条落盘通道：预览名就是最终落下的名字。"""

    BROKEN = "82331647_111024.png"

    def body(self, *decisions: dict) -> dict:
        return {"directory": str(self.source), "decisions": list(decisions)}

    def filled(self, **overrides) -> dict:
        decision = {
            "filename": self.BROKEN,
            "env": "Server",
            "category": "Spec",
            "pcname": "TCSB2",
            "ultraviewer_id": "82331647",
        }
        decision.update(overrides)
        return decision

    def test_a_completed_non_compliant_image_lands_under_the_previewed_name(self):
        self.make_source(self.BROKEN)
        body = self.body(self.filled())

        preview = self.post("/api/preview", body)
        landed = self.post("/api/rename", body)

        self.assertEqual(
            preview["ready"],
            [{"source": self.BROKEN, "target": "(Server)82331647_TCSB2-Spec.png"}],
        )
        self.assertEqual(landed["rows"][0]["target"], preview["ready"][0]["target"])
        self.assertTrue((self.source / "Renamed" / preview["ready"][0]["target"]).is_file())

    def test_a_hand_typed_id_that_is_not_digits_is_refused_at_the_api_too(self):
        """页面会标红，但绕过页面直接打 API 也得挡住。"""
        self.make_source(self.BROKEN)

        preview = self.post("/api/preview", self.body(self.filled(ultraviewer_id="82-331")))

        self.assertEqual(preview["ready"], [])

    def test_an_unfilled_non_compliant_image_does_not_hold_back_the_compliant_ones(self):
        self.make_source(self.BROKEN, NAMES[0])
        body = self.body(
            self.filled(env="", category="未定", pcname="", ultraviewer_id=""),
            {
                "filename": NAMES[0],
                "env": "Server",
                "category": "Spec",
                "pcname": "",
                "ultraviewer_id": "",
            },
        )

        preview = self.post("/api/preview", body)
        landed = self.post("/api/rename", body)

        self.assertEqual([item["source"] for item in preview["ready"]], [NAMES[0]])
        self.assertEqual(landed["copied"], 1)
        self.assertEqual([item["filename"] for item in landed["blocked"]], [self.BROKEN])


class PreviewGuardTest(ServerTestCase):
    def test_requests_that_are_not_json_from_this_page_are_refused(self):
        self.make_source(NAMES[0])
        request = urllib.request.Request(
            self.base + "/api/preview",
            data=json.dumps(self.decisions(NAMES[0])).encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            method="POST",
        )

        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request)

        self.assertEqual(raised.exception.code, 403)


if __name__ == "__main__":
    unittest.main()

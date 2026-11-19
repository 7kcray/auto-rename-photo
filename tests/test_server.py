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
                    "number": "",
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

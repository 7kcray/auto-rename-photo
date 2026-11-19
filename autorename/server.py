"""只绑回环地址的本地 HTTP 服务：把工具页、扫描结果和图片喂给浏览器。

刻意只用标准库。不发起任何外部请求，页面里也没有外部资源。
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from autorename import state
from autorename.nameparse import PNG_EXTENSION
from autorename.scanner import DirectoryUnusable, scan_directory

LOOPBACK = "127.0.0.1"
_WEB_ROOT = Path(__file__).parent / "web"


class ToolRequestHandler(BaseHTTPRequestHandler):
    initial_directory: str | None = None
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 的接口
        url = urlparse(self.path)
        route = url.path

        if route in ("/", "/index.html"):
            self._send_bytes(_WEB_ROOT.joinpath("index.html").read_bytes(), "text/html; charset=utf-8")
        elif route == "/api/state":
            self._send_json(
                {
                    "initial_directory": self.initial_directory,
                    "last_directory": state.load_last_directory(),
                }
            )
        elif route == "/api/scan":
            self._handle_scan(parse_qs(url.query))
        elif route == "/api/image":
            self._handle_image(parse_qs(url.query))
        else:
            self._send_error_page(404, "没有这个页面")

    def _handle_scan(self, query: dict[str, list[str]]) -> None:
        directory = _first(query, "directory")
        if not directory:
            self._send_error_json("先给一个截图目录")
            return

        try:
            result = scan_directory(directory)
        except DirectoryUnusable as error:
            self._send_error_json(str(error))
            return

        state.save_last_directory(result.directory)
        self._send_json(result.to_payload())

    def _handle_image(self, query: dict[str, list[str]]) -> None:
        path = _resolve_image(_first(query, "directory"), _first(query, "filename"))
        if path is None:
            self._send_error_page(404, "找不到这张图")
            return

        self._send_bytes(path.read_bytes(), "image/png")

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _send_error_json(self, message: str) -> None:
        self._send_json({"error": message}, status=400)

    def _send_error_page(self, status: int, message: str) -> None:
        body = f"<!doctype html><meta charset='utf-8'><p>{message}</p>".encode()
        self._send_bytes(body, "text/html; charset=utf-8", status)

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - 签名由基类决定
        # 一张图一行日志太吵，只留扫描和错误。
        if "/api/image" in (args[0] if args else ""):
            return
        super().log_message(format, *args)


def _first(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or [""]
    return values[0]


def _resolve_image(directory: str, filename: str) -> Path | None:
    """只认「扫描目录 + 纯文件名」，把路径穿越挡在外面。"""
    if not directory or not filename:
        return None
    if os.path.basename(filename) != filename or not filename.lower().endswith(PNG_EXTENSION):
        return None

    path = Path(os.path.abspath(directory)) / filename
    if not path.is_file():
        return None
    return path


def create_server(port: int, initial_directory: str | None) -> ThreadingHTTPServer:
    """把 initial_directory 绑到一个一次性子类上——基类构造函数不收额外参数。"""

    class BoundHandler(ToolRequestHandler):
        pass

    BoundHandler.initial_directory = initial_directory
    return ThreadingHTTPServer((LOOPBACK, port), BoundHandler)

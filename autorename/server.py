"""只绑回环地址的本地 HTTP 服务：把工具页、扫描结果和图片喂给浏览器。

刻意只用标准库。不发起任何外部请求，页面里也没有外部资源。
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from autorename import config, state
from autorename.executor import TargetUnusable, apply_plan
from autorename.naming import TEMPLATE, default_target_directory
from autorename.nameparse import PNG_EXTENSION
from autorename.plan import Decision, plan_batch
from autorename.scanner import DirectoryUnusable, scan_directory
from autorename.vocabulary import CATEGORIES, UNDECIDED

LOOPBACK = "127.0.0.1"
_WEB_ROOT = Path(__file__).parent / "web"
_MAX_BODY_BYTES = 4 * 1024 * 1024
_LOCAL_HOSTS = ("127.0.0.1", "localhost")


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
        elif route == "/api/config":
            self._handle_config()
        elif route == "/api/scan":
            self._handle_scan(parse_qs(url.query))
        elif route == "/api/image":
            self._handle_image(parse_qs(url.query))
        else:
            self._send_error_page(404, "没有这个页面")

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 的接口
        route = urlparse(self.path).path
        if route != "/api/rename":
            self._send_error_page(404, "没有这个页面")
            return

        if not self._accepts_this_request():
            # 落盘会写文件：只认本工具页面自己发来的 JSON 请求。
            self._send_error_json("只接受本机页面的请求", status=403)
            return

        self._handle_rename()

    def _accepts_this_request(self) -> bool:
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type != "application/json":
            return False

        origin = self.headers.get("Origin")
        if origin:
            return urlparse(origin).hostname in _LOCAL_HOSTS
        return True

    def _handle_config(self) -> None:
        options = config.load_env_options()
        self._send_json(
            {
                "envs": list(options.envs),
                "categories": list(CATEGORIES),
                "undecided": UNDECIDED,
                "template": TEMPLATE,
                "config_path": options.path,
                "warning": options.warning,
            }
        )

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
        payload = result.to_payload()
        payload["default_target_directory"] = default_target_directory(result.directory)
        self._send_json(payload)

    def _handle_rename(self) -> None:
        body = self._read_json()
        if body is None:
            return

        directory = _text(body.get("directory"))
        if not directory:
            self._send_error_json("先给一个截图目录")
            return

        try:
            scan = scan_directory(directory)
        except DirectoryUnusable as error:
            self._send_error_json(str(error))
            return

        target_directory = _absolute(_text(body.get("target_directory"))) or default_target_directory(
            scan.directory
        )
        plan = plan_batch(scan, _decisions_from(body.get("decisions")), target_directory)
        try:
            result = apply_plan(plan)
        except TargetUnusable as error:
            self._send_error_json(str(error))
            return

        self._send_json(result.to_payload())

    def _handle_image(self, query: dict[str, list[str]]) -> None:
        path = _resolve_image(_first(query, "directory"), _first(query, "filename"))
        if path is None:
            self._send_error_page(404, "找不到这张图")
            return

        self._send_bytes(path.read_bytes(), "image/png")

    def _read_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0

        if length <= 0 or length > _MAX_BODY_BYTES:
            # 不读走请求体就没法复用这条连接，直接断开，免得把残留字节当下一个请求。
            self.close_connection = True
            self._send_error_json("请求体读不了")
            return None

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self._send_error_json("请求体不是合法的 JSON")
            return None

        if not isinstance(payload, dict):
            self._send_error_json("请求体不是一个对象")
            return None
        return payload

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _send_error_json(self, message: str, status: int = 400) -> None:
        self._send_json({"error": message}, status=status)

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


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _absolute(value: str) -> str:
    """用户手写的路径可能带引号、`~` 或相对段。"""
    return os.path.abspath(os.path.expanduser(value.strip().strip('"'))) if value else ""


def _decisions_from(raw: object) -> list[Decision]:
    """页面传来的逐张决定。坏条目直接丢掉——少一张决定只会被挡住，不会误落盘。"""
    if not isinstance(raw, list):
        return []

    decisions: list[Decision] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        filename = _text(item.get("filename"))
        if not filename:
            continue
        decisions.append(
            Decision(filename=filename, env=_text(item.get("env")), category=_text(item.get("category")))
        )
    return decisions


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

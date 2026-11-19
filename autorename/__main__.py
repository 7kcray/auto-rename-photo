"""双击 .bat 的入口：起服务、开浏览器。"""

import argparse
import os
import threading
import webbrowser
from http.server import ThreadingHTTPServer

from autorename import state
from autorename.server import create_server

DEFAULT_PORT = 8765
_PORT_ATTEMPTS = 20
_DIRECTORY_ENV = "AUTORENAME_DIR"


def main() -> int:
    parser = argparse.ArgumentParser(description="截图批量重命名工具")
    parser.add_argument("--dir", dest="directory", help="截图目录（可直接把文件夹拖到 .bat 上）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"端口，默认 {DEFAULT_PORT}")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    initial_directory = args.directory or os.environ.get(_DIRECTORY_ENV) or state.load_last_directory()
    server = _bind(args.port, initial_directory)
    url = f"http://127.0.0.1:{server.server_address[1]}/"

    print(f"工具页已启动：{url}")
    print("关掉这个窗口即停止服务。")

    if not args.no_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()
    return 0


def _bind(preferred_port: int, initial_directory: str | None) -> ThreadingHTTPServer:
    """端口被占就往后找，都不行再退回系统分配。"""
    last_error: OSError | None = None
    for port in range(preferred_port, preferred_port + _PORT_ATTEMPTS):
        try:
            return create_server(port, initial_directory)
        except OSError as error:
            last_error = error

    try:
        return create_server(0, initial_directory)
    except OSError as error:
        raise SystemExit(f"起不了本地服务：{error or last_error}") from error


if __name__ == "__main__":
    raise SystemExit(main())

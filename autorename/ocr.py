r"""OCR 适配器：截图 → 文本行。

真实实现调 Windows 内置 `Windows.Media.Ocr`（一个 PowerShell 脚本，不装任何包）；
测试喂录好的文本，永远不跑真 OCR。

脚本先按 2 倍 Cubic 放大再识别：截图里的路径文字只有几个像素高，原生尺寸下
引擎读不出 `\\TCSB2\` 和 `C:\`，ENV 线索就没有据可依。

对外只有一条缝：`read_texts(paths)` 按顺序给出每张图的文本，读不出的给空串。
失败自己吞掉——OCR 挂了只是让类别落在「未定」，不该拖垮整批扫描。
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol, Sequence

SCRIPT_PATH = Path(__file__).parent / "ocr_windows.ps1"
TIMEOUT_SECONDS = 180
_CREATE_NO_WINDOW = 0x08000000


class OcrProvider(Protocol):
    """能按顺序给出每张图文本的任何东西。测试用它换掉真 OCR。"""

    def read_texts(self, paths: Sequence[str]) -> list[str]:
        ...


class WindowsOcr:
    """一次子进程跑完整批：省掉每张图一次 PowerShell 启动。

    `runner` 只在测试里替换，用来验证「脚本失败 → 全部空串」这条降级路径。
    """

    def __init__(self, script_path: Path | None = None, timeout: int = TIMEOUT_SECONDS, runner=None):
        self.script_path = Path(script_path) if script_path is not None else SCRIPT_PATH
        self.timeout = timeout
        self._run = runner or run_powershell_ocr

    def read_texts(self, paths: Sequence[str]) -> list[str]:
        targets = [str(path) for path in paths]
        if not targets:
            return []

        return _fit(self._run(self.script_path, targets, self.timeout), len(targets))


def run_powershell_ocr(script_path: Path, paths: Sequence[str], timeout: int) -> list[str] | None:
    """跑一遍脚本，把结果 JSON 读回来；起不来或读不出就返回 None。"""
    with tempfile.TemporaryDirectory(prefix="autorename-ocr-") as folder:
        result_path = Path(folder) / "ocr.json"
        command = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-Out",
            str(result_path),
            *paths,
        ]

        try:
            subprocess.run(
                command,
                capture_output=True,
                timeout=timeout,
                check=False,
                creationflags=_CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        return _read_result(result_path)


def _read_result(path: Path) -> list[str] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None

    texts = payload.get("texts") if isinstance(payload, dict) else None
    if isinstance(texts, str):
        # PowerShell 把单元素数组压成了一个字符串。
        texts = [texts]
    if not isinstance(texts, list):
        return None

    return [text if isinstance(text, str) else "" for text in texts]


def _fit(texts: list[str] | None, count: int) -> list[str]:
    """不管脚本给多给少，都凑成与输入等长的一列：缺的补空串。"""
    if not texts:
        return ["" for _ in range(count)]
    return (texts + ["" for _ in range(count)])[:count]

"""上次用过的目录：存在本机用户目录下，下次双击 .bat 自动回填。"""

import json
import os
from pathlib import Path


def state_file_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return Path(base) / "AutoRenamePhoto" / "state.json"


def load_last_directory() -> str | None:
    path = state_file_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    last = data.get("last_directory")
    return last if isinstance(last, str) and last else None


def save_last_directory(directory: str) -> None:
    path = state_file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"last_directory": directory}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        # 记不住上次的目录不影响本批工作，静默放弃。
        pass

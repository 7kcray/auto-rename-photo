"""把一批实拍图的 OCR 文本重录成 fixture——真 OCR 只在开发机上跑这一次。

    python tools/record_ocr_fixtures.py "Akarumi Before Edit"
    python tools/record_ocr_fixtures.py "Sample4Train" --merge

默认整份覆盖：只录一个目录时，旧条目会一起没掉。加 `--merge` 则是合并——录哪个
目录就更新哪些条目，其余原样留着（新一批样本进来时用这个）。

跑完会覆盖 `tests/fixtures/ocr_texts.json` 里对应文件的文本行；测试本身永远不跑 OCR，
只读这份录好的文本。
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autorename.ocr import WindowsOcr  # noqa: E402 - 先把仓库根放进 sys.path

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "ocr_texts.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="录实拍图的 OCR 文本")
    parser.add_argument("directory", help="实拍图所在目录")
    parser.add_argument("--out", default=str(FIXTURE), help=f"fixture 路径，默认 {FIXTURE}")
    parser.add_argument("--merge", action="store_true", help="与已有 fixture 合并，不覆盖其他条目")
    args = parser.parse_args()

    folder = Path(args.directory)
    if not folder.is_dir():
        print(f"找不到目录：{folder}")
        return 1

    paths = sorted(path.resolve() for path in folder.glob("*.png") if path.is_file())
    if not paths:
        print(f"目录里没有 PNG：{folder}")
        return 1

    texts = WindowsOcr().read_texts([str(path) for path in paths])
    recorded = {
        path.name: text.splitlines() for path, text in zip(paths, texts) if text.strip()
    }

    out = Path(args.out)
    if args.merge and out.exists():
        # 合并：已有条目按原顺序留着，本次录到的覆盖同名条目、新的追加在后面。
        try:
            existing = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = {}
        if isinstance(existing, dict):
            existing.update(recorded)
            recorded = existing

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(recorded, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"录下 {len(recorded)} 张图的文本 → {out}")
    for path, text in zip(paths, texts):
        if not text.strip():
            print(f"  读不出字：{path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

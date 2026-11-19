"""本机配置：ENV 下拉的选项集合。

默认给 `Server` 与 `Link1`…`Link3`。本批有几条链路，就在 `config.json` 的 `envs` 里
加几个（`Link4`、`Link5`…），下次扫描即生效。

配置缺失或坏掉时退回默认值，并给一句能读懂的话——配置坏掉不该拖垮整批。
写进来的值统一收成 `Server` / `Link1` 这种首字母大写、其余小写。
"""

import json
from dataclasses import dataclass
from pathlib import Path

from autorename.state import app_data_dir
from autorename.vocabulary import DEFAULT_ENVS, canonical_env

CONFIG_FILENAME = "config.json"


@dataclass(frozen=True)
class EnvOptions:
    """下拉里能选的 ENV，以及读配置时要说给用户听的一句话。"""

    envs: tuple[str, ...]
    path: str
    warning: str | None = None


def config_path() -> Path:
    return app_data_dir() / CONFIG_FILENAME


def load_env_options(path: Path | None = None) -> EnvOptions:
    resolved = Path(path) if path is not None else config_path()
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return EnvOptions(envs=DEFAULT_ENVS, path=str(resolved))
    except (OSError, ValueError) as error:
        return EnvOptions(
            envs=DEFAULT_ENVS,
            path=str(resolved),
            warning=f"配置文件读不了（{error}）：{resolved}。先用默认选项 Server、Link1…Link3。",
        )

    envs = _read_envs(raw)
    if not envs:
        return EnvOptions(
            envs=DEFAULT_ENVS,
            path=str(resolved),
            warning=f"配置文件里没有可用的 envs：{resolved}。先用默认选项 Server、Link1…Link3。",
        )

    return EnvOptions(envs=envs, path=str(resolved))


def ensure_default_config(path: Path | None = None) -> None:
    """第一次运行时留一份能直接改的 config.json；已有文件一律不动。"""
    resolved = Path(path) if path is not None else config_path()
    if resolved.exists():
        return

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps({"envs": list(DEFAULT_ENVS)}, ensure_ascii=False, indent=2)
        resolved.write_text(body + "\n", encoding="utf-8")
    except OSError:
        # 写不出配置文件不影响用默认选项开工。
        pass


def _read_envs(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, dict):
        return ()

    listed = raw.get("envs")
    if not isinstance(listed, list):
        return ()

    seen: set[str] = set()
    envs: list[str] = []
    for item in listed:
        if not isinstance(item, str):
            continue
        env = canonical_env(item)
        if env and env not in seen:
            seen.add(env)
            envs.append(env)
    return tuple(envs)

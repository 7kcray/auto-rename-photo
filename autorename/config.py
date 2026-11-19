"""本机配置：ENV 下拉的选项集合，以及「顾客 → 机器」登记。

默认给 `Server` 与 `Link1`…`Link3`。本批有几条链路，就在 `config.json` 的 `envs` 里
加几个（`Link4`、`Link5`…），下次扫描即生效。

`customers` 是本机的机器登记：每个顾客下面列几台机器，每台带 `pcname`、`number`
和可选的 `hostname`（UNC 里出现的机器名，缺省等于 PCNAME）。第一次运行会写一份
带 Akarumi 示例的模板，照着自己的顾客改即可；本版没有增删改界面。

配置缺失或坏掉时退回默认值，并给一句能读懂的话——配置坏掉不该拖垮整批。
写进来的值统一收成 `Server` / `Link1` 这种首字母大写、其余小写。
"""

import json
from dataclasses import dataclass
from pathlib import Path

from autorename.state import app_data_dir
from autorename.vocabulary import DEFAULT_ENVS, canonical_env

CONFIG_FILENAME = "config.json"
CUSTOMERS_KEY = "customers"

# 第一次运行时写进 config.json 的机器登记样板：换顾客、换机器就改这几行。
# `label` 用 ENV 里的叫法（`Server`、`Link1`），组头和下拉里显示的就是它。
SAMPLE_CUSTOMERS = (
    {
        "name": "Akarumi",
        "machines": (
            {"label": "Server", "pcname": "TCSB2", "number": "82331647", "hostname": "TCSB2"},
            {"label": "Link1", "pcname": "BB", "number": "82335369", "hostname": "BB"},
        ),
    },
)


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
        body = json.dumps(
            {"envs": list(DEFAULT_ENVS), CUSTOMERS_KEY: list(SAMPLE_CUSTOMERS)},
            ensure_ascii=False,
            indent=2,
        )
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

# 截图批量重命名

把系统生成的截图文件名批量改成能交付的名字。本机运行，双击一个 `.bat` 就能用。

```
82331647_TCSB218112026_111024.png   →   (Server)82331647_TCSB2-Spec.png
82335369_BB18112026_110835.png      →   (Link1)82335369_BB-Group.png
```

源目录只读：工具只把图**复制**到落盘目录，不改名、不删除、不覆盖。

## 快速开始

要求：Windows 10/11，Python 3.10 或更新（安装时勾选 “Add python.exe to PATH”）。

1. 双击 `启动工具.bat`。
2. 浏览器自动打开工具页（`http://127.0.0.1:8765/`）。
3. 填截图目录，或直接把文件夹拖到 `.bat` 上，点「扫描」。

也可以走命令行：

```bat
python -m autorename --dir "D:\Shots"
python -m autorename --port 9000 --no-browser
```

关掉那个黑窗口即停止服务。

## 使用流程

1. **扫描**：列出目录下所有 PNG，解析文件名里的数字、PCNAME、时间，并调 Windows 内置 OCR 预判类别。
2. **核对**：图按机器分组，组头标明顾客与机器；每张图两个下拉——类别（OCR 预判可改）和 ENV。ENV 旁会提示「疑似服务器 / 疑似客户端」，但**不预填**，点哪一格由人决定。
3. **落盘**：点「落盘」，图被复制到落盘目录（默认 `<源目录>\Renamed`），同时写 `rename-log.csv`。

类别未定、ENV 未选、文件名不合规的图会被挡住，只影响它自己，不拖累整批。

## 命名规则

```
(ENV)数字_PCNAME-类别.png
```

- **ENV** 统一写成 `Server`、`Link1` 这种「首字母大写、其余小写」，配置里写错大小写也进不了文件名。
- **类别** 是封闭词表，只有七个：`Analyse`、`Data`、`Group`、`Main`、`Spec`、`Test`、`Version`。判不准就是 `未定`，不会出现 `Database`、`Goup` 这类同义异名。
- **数字与 PCNAME** 默认取自文件名，组头选定机器后以机器登记为准。
- **同机同类多张**时按时间片段升序排号：首张是 `…-类别.png`，第二张起 `…-类别-2.png`、`…-类别-3.png`。编号只为防撞名，不表达顺序语义——改文件 mtime 不会改变谁拿 `-2`；不同机器、不同类别、不同 ENV 各自独立编号。

页面上的预览名走 `/api/preview`，与落盘共用同一个计划器，所以预览里带 `-2` 的那一行，落盘就是 `-2`。

原文件名形如 `82331647_TCSB218112026_111024.png`，三段以 `_` 分隔：

| 段 | 含义 | 处理 |
| --- | --- | --- |
| `82331647` | 系统给的数字，屏幕上不存在 | 保留 |
| `TCSB2` + `18112026` | PCNAME + 日期（DDMMYYYY） | 取 PCNAME，日期丢弃 |
| `111024` | 时间片段，时/分/秒不补零 | 仅用于排序 |

时间片段只认 5 位和 6 位。5 位时先按「秒丢了 0」读（`11156` → 11:15:06），读不通再按「分丢了 0」读（`11835` → 11:08:35）。

## 配置

第一次运行会在 `%LOCALAPPDATA%\AutoRenamePhoto\config.json` 写一份带示例的模板：

```json
{
  "envs": ["Server", "Link1", "Link2", "Link3"],
  "customers": [
    {
      "name": "Akarumi",
      "machines": [
        { "label": "Server", "pcname": "TCSB2", "number": "82331647", "hostname": "TCSB2" },
        { "label": "Link1", "pcname": "BB", "number": "82335369", "hostname": "BB" }
      ]
    }
  ]
}
```

- `envs`：ENV 下拉的选项。本批有几条链路就加几个（`Link4`、`Link5`…）。
- `customers`：顾客 → 机器登记。`pcname` 与 `number` 一起才认作一台机器；`hostname` 是 UNC 路径里出现的机器名，缺省等于 `pcname`，用于给 ENV 提示。
- 配置坏掉不会崩：退回默认选项、所有图归入「未登记」组，页面上给一句能读懂的话。
- 上次用过的目录记在同一个目录下的 `state.json`，下次自动回填。

本版没有增删改配置的界面，改 JSON 后刷新页面即生效。

## 安全边界

- 服务只绑 `127.0.0.1`，不联网，页面里没有外部资源。
- 落盘接口只接受本机页面发来的 JSON 请求（校验 `Content-Type` 与 `Origin`）。
- 落盘目录指到源目录上会被直接拒绝。
- 目标文件已存在时一律不覆盖，日志里记一行「冲突」。
- 只用 Python 标准库，OCR 走系统自带的 `Windows.Media.Ocr`，不需要 `pip install` 任何东西。

## 已知限制与路线图

- **重跑幂等未做**：同一批重跑会产生一批「冲突」记录，尚未按文件大小跳过（issue #7）。
- **实拍整批验收待做**：目前靠录制的 OCR 样本测试，12 张真图的整批比对还没跑（issue #8）。
- 只有 Windows 版；OCR 与 `.bat` 启动器都依赖 Windows。

## 开发

```bat
python -m unittest discover -s tests -t .
```

109 个用例，全部通过。OCR 在测试里一律喂 `tests/fixtures/ocr_texts.json` 里录好的真实文本，不跑真引擎。

```
autorename/
  __main__.py     入口：起本地服务、开浏览器
  server.py       回环 HTTP 服务与 API
  scanner.py      目录 → PNG 清单（只读）
  nameparse.py    文件名解析（纯函数）
  naming.py       目标文件名模板
  vocabulary.py   封闭词表：类别与 ENV
  classifier.py   OCR 文本 → 类别（按优先级排序的规则）
  ocr.py          Windows OCR 适配器（PowerShell 子进程，2 倍放大后识别）
  machines.py     顾客 → 机器登记、ENV 线索
  groups.py       按机器分组
  plan.py         扫描结果 + 逐张决定 → 落盘清单（纯函数）
  executor.py     复制落盘、写 rename-log.csv
  config.py       本机配置
  state.py        上次用过的目录
  web/index.html  工具页（单文件，无构建步骤）
tests/            unittest 用例与录制的 OCR 文本
tools/            录制 OCR 样本的小脚本
docs/agents/      agent 协作约定（issue tracker、triage 标签、领域文档）
启动工具.bat      双击启动
```

设计上的取舍写在模块 docstring 里，改动前先读一遍对应文件的开头。

## 协作

- 规格与任务都在 GitHub Issues（[#1 规格](https://github.com/7kcray/auto-rename-photo/issues/1)）。
- Issue 约定见 `docs/agents/issue-tracker.md`，标签见 `docs/agents/triage-labels.md`。
- 提交信息用 `feat:` / `chore:` 前缀，并带上对应的 issue 编号。

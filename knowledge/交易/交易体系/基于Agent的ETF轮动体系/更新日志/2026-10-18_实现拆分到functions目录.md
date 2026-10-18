---
title: 实现拆分到 functions 目录、清理死代码 | 2026-10-18
summary: "ETF轮动体系 MCP 由单文件 447 行拆为入口 154 行 + `functions/` 四个模块（paths / parameters / market / artifacts），函数体逐字搬运；同时删除三个无调用点定义（`list_tools_legacy`、`call_tool_legacy`、`process_dir`）。验证：24 个顶层定义逐字比对仅上述三个被删；真实 stdio 握手工具面不变（list_systems／get_manifest／validate_parameters／is_trading_day／render）；拆分前后 `get_manifest`（归一化路径后）、`validate_parameters`、`is_trading_day`、`render(dry_run)` 输出逐字段一致；`params/`、`templates/` 未改，参数哈希 `9b0f04cb…` 不变。"
date: 2026-10-18
reason: 用户 2026-10-18 裁定「轮动第 3 项（单文件）要拆」，并沿用双网格／双债LOF 的 `functions/` 样板
tags:
  - 交易体系
  - 更新日志
  - ETF轮动
system-id: agent_etf_rotation_system
system-name: 基于Agent的ETF轮动体系
---

# 实现拆分到 functions 目录、清理死代码 | 2026-10-18

## 一、动因与范围

`mcp_server.py` 447 行单文件同时承载路径与 IO、参数校验（含候选池校验）、tushare 客户端与交易日历、复盘文档规范化与渲染、工具注册与路由。按用户裁定拆分为「入口 + `functions/`」，并清理死的定义。范围限本体系运行定义，**未改** `params/`、`templates/` 与任务注册。

## 二、变更

| 对象 | 变更 |
|:--|:--|
| `mcp_server.py` | 447 → 154 行，只留 `TOOLS`、`server`、`list_tools_result`、`call_tool_result` 与 stdio 装配；加 `sys.path` 自举后从 `functions/` 导入 |
| `functions/paths.py` | 常量（`SYSTEM_ROOT`／`REPO_ROOT`／`PARAMS_ROOT`／`TEMPLATES_ROOT`／`SYSTEM_ID`／`SYSTEM_NAME`／`SYSTEM_VERSION`／`PARAMETER_FILES`／`CONTENT_ROOT_NAMES`／`REVIEW_ARTIFACTS`）、`load_env`、`normalize_date`、`read_json`、`logical_root`、`logical_process_root`、`review_dir`、`params/` 存在性守卫 |
| `functions/parameters.py` | `fail`／`require_*` 校验族、`load_parameters`、`validate_parameters`、`validate_universe`（含 `CODE_PATTERN`、`UNIVERSE_FIELDS`）、`parameter_metadata` |
| `functions/market.py` | `get_client`、`fetch_trade_calendar`（2026-10-18 新增的交易日判断） |
| `functions/artifacts.py` | `normalize_review_document`、`render_review` |
| 删除定义 | `list_tools_legacy`、`call_tool_legacy`（兼容分支走 `hasattr` 判断，不经过它们）、`process_dir`（定义后无任何引用） |

## 三、验证

- 逐字搬运：新旧 27 个顶层定义逐一比对，除上述 3 个被删定义外**完全一致**；被删定义在全部文件中无残留。
- 工具面：真实 stdio 握手 5 个工具不变（`list_systems`／`get_manifest`／`validate_parameters`／`is_trading_day`／`render`）。
- 行为对照（拆分前副本 vs 拆分后，同输入）：`get_manifest`（路径归一化后逐字段一致）、`validate_parameters`（`valid=true`、`parameter_hash 9b0f04cb…`）、`is_trading_day`（10-16 开市／10-18 休市）、`render(dry_run=true)` 输出一致；体系不符等错误路径一致。
- 副作用：仅实现文件与新增 `functions/`；沙盒目录 `/tmp/rot_orig_dir` 用后已删。

## 四、遗留

- 运行中的 MCP 子进程仍加载拆分前单文件（行为已验证一致），重启或新会话后加载新结构。
- `functions/paths.py` 的 `CONTENT_ROOT_NAMES` 目前无引用（轮动不读归档双头），保留作为常量声明；若确认长期无用可随下次改动删除。

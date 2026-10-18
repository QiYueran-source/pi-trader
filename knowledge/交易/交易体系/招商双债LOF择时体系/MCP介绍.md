---
title: 招商双债LOF择时体系 MCP 介绍
summary: "双债LOF体系 MCP `zslof-timing-trade` 介绍：服务与运行定义位置、五个工具与入参（`signal`／`replay_check`）、过程产物写入位置、跨日状态的存放与读取规则（knowledge → archive 双头）、错误与降级口径、依赖与已退役脚本清单。"
date: 2026-10-17
tags:
  - 交易体系
  - 择时
  - LOF
  - MCP
system-id: zslof_timing_trade
---

# 招商双债LOF择时体系 MCP 介绍

## 服务与运行定义

信号计算与报告渲染统一通过 MCP 服务 `zslof-timing-trade` 完成，注册见 `.pi/mcp.json`，工具命名空间 `mcp__zslof_timing_trade__*`。运行定义目录：

```text
.pi/mcp-servers/trade-system/zslof_timing_trade/
├── mcp_server.py       # 服务入口（只做工具注册与路由）
├── functions/          # 实现模块（paths / parameters / market / state / signals / artifacts）
├── system.yml          # 运行契约：身份、账户、操作、参数与模板位置、产物契约、状态规则、边界
├── params/             # 参数唯一来源（instrument / timing / runtime）
└── templates/          # 模板唯一来源（signal_report.md.j2）
```

调用口径（命名规则、入参约定、自检与迁入步骤）见 `trade-system` 技能的 `reference/mcp.md`。

## 工具与入参

`date` 支持 `YYYY-MM-DD` 或 `YYYYMMDD`，产物目录按 `YYYY-MM-DD` 命名；`system_id` 必填且必须为 `zslof_timing_trade`；本体系**不接受** `positions`／`cash`（不查询账户）。

| 工具 | 入参 | 返回 / 产物 |
|---|---|---|
| `list_systems` | — | 本服务实现的体系 |
| `get_manifest` | `system_id` | 运行定义路径、支持的操作、产物落盘位置 |
| `validate_parameters` | `system_id` | `valid`、`files`、`parameter_version`、`parameter_hash`、`schema_versions` |
| `calculate` | `system_id`、`operation`（`signal`／`replay_check`）、`date`、`dry_run`（可选） | `signal`：`strategy_state`＋`signal_facts` 两份事实，`dry_run=false` 时写入过程资料；`replay_check`：从锚日重放并与存储状态比对（只读） |
| `render` | `system_id`、`artifact`（`signal_report`）、`date`、`document`（可选）、`state`（可选） | `signal_report.md`；省略 `document`/`state` 时读同日过程资料 |

约定：

- `signal` 一次调用完成「推进状态 + 判定信号」，同时落盘 `strategy_state.json` 与 `signal_facts.json`；重复调用同一日期为幂等（状态已推进到该日则不再重复推进）。
- 取数窗口固定为目标日前 `params/runtime.json#history_lookback_calendar_days` 个自然日；状态推进只处理晚于「上一已处理交易日」的行。
- 每次调用重新读取并校验 `params/` 下 3 个参数文件。
- 非交易日或目标日无行情时按无数据报错，不使用其它日期数据替代。

## 跨日状态

- **存放**：当日的 `strategy_state.json` 写在当日过程资料目录 `交易/过程资料/<日期>/招商双债LOF择时体系/`（落 `knowledge/`），随该日期目录一起被归档；归档只改物理位置，逻辑路径不变。
- **读取**（`state_lookup = latest_prior_process_date`）：取目标日之前最近一个存在状态的过程日 `交易/过程资料/<日期>/招商双债LOF择时体系/strategy_state.json`（读 `knowledge/`→`archive/`）；两处都存在时以 `knowledge/` 为准（本体系明确规则，见 `交易/交易体系/招商双债LOF择时体系/体系运作流程.md` 2.1；不使用 `duplicate` 报告语义）。
- **留痕**：产物记录 `source_state`（逻辑路径）与 `source_state_detail`（实际位置与来源日期）；找不到任何先前状态时按初始空仓状态推进，`source_state` 为 `null`。
- **禁止**读取未来日期状态（`allow_future_state = false`）。

## 过程产物

统一写入：

```text
交易/过程资料/{date}/招商双债LOF择时体系/    （落 `knowledge/`；归档后同一逻辑路径位于 `archive/`）
```

- `strategy_state.json`：理论策略状态（peak／trough／计数／锚／上一已处理交易日）；
- `signal_facts.json`：当日收盘信号与次日动作，含 `market`、`checks`（结构化判据）、`note`（判据摘要）、`state_anchors`、`parameters`；
- `signal_report.md`：由运行定义模板渲染的可读报告。

契约细节以运行定义 `system.yml` 的 `process_output` 为准。交易计划由任务按 `交易/交易体系/招商双债LOF择时体系/体系运作流程.md` 第 2.4 节写入 `交易/交易计划/`（落 `knowledge/`），MCP 不写计划。

## 重放校验（replay_check）

从 `params/runtime.json#state_anchor_date` 起重放收盘价序列（只读，不写产物），返回重放状态、信号序列与对照状态，并给出 `matched` 与 `diff_fields`。用途：参数或实现变更后的验算、状态可疑时排查。

## 错误与降级

- 调用失败返回 `{"ok": false, "error": "..."}`，不产生产物；缺失必填参数、体系不符与非法操作在入口层被拦截。
- 失败时记录失败阶段与错误信息并停止依赖该事实的下游步骤；不估算、不编造、不用历史产物冒充当日结果。
- 服务不可用时如实报告，不改为直接执行仓库内的历史脚本。

## 依赖

- 服务由 `/opt/venv/bin/python` 启动（`.pi/mcp.json` 已配置），依赖含 `mcp`、`tushare`、`jinja2`。
- Tushare token 读取项目 MCP 的 `.pi/mcp-servers/tushare/.env`，不写入仓库其它文件。
- `/opt/venv` 属 root 且不在挂载点上（随容器可写层）：容器重建后若报 `ModuleNotFoundError`，由 root 执行 `uv pip install --python /opt/venv/bin/python jinja2` 补回。
- 行情与交易日历的取数接口见 `tushare` 技能；账户与持仓事实见 `trade-management` 技能（本体系只读理论状态，不查账户）。

## 已退役

- 迁入 MCP 时删除知识库内的脚本 `timing_signal.py`、`render.py`、`runtime_support.py`，能力全部由本服务实现（可在 git 历史中查阅）；旧脚本曾依赖 `HERMES_REPO_ROOT` 环境变量，该口径一并退役。

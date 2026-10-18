---
title: 热门板块回调低吸体系 MCP 介绍
summary: "热门板块回调低吸体系 MCP `hot-sector-pullback-system` 介绍：服务与运行定义位置、五个工具与入参、四段事实与全市场板块环境的产物清单、`positions` 输入结构、分钟线降级与错误口径、依赖说明与已退役脚本清单。"
date: 2026-10-17
tags:
  - 交易体系
  - 热门板块回调低吸
  - MCP
system-id: hot_sector_pullback_system
---

# 热门板块回调低吸体系 MCP 介绍

## 服务与运行定义

体系计算、参数校验与渲染统一通过 MCP 服务 `hot-sector-pullback-system` 完成，注册见 `.pi/mcp.json`，工具命名空间 `mcp__hot_sector_pullback_system__*`。运行定义目录：

```text
.pi/mcp-servers/trade-system/hot_sector_pullback_system/
├── mcp_server.py       # 服务入口与实现（四段事实、板块环境、渲染）
├── system.yml          # 运行契约：身份、账户、操作、参数与模板位置、产物契约、边界
├── params/             # 参数唯一来源（selection / sector_heat / entry / risk / runtime）
└── templates/          # 模板唯一来源（渲染用 4 个 `.j2` + 复盘／过程文档模板）
```

调用口径（命名规则、入参约定、自检与迁入步骤）见 `trade-system` 技能的 `reference/mcp.md`。

## 工具与入参

`date` 支持 `YYYY-MM-DD` 或 `YYYYMMDD`，产物目录按 `YYYY-MM-DD` 命名；`system_id` 必填且必须为 `hot_sector_pullback_system`。

| 工具 | 入参 | 返回 / 产物 |
|---|---|---|
| `list_systems` | — | 本服务实现的体系 |
| `get_manifest` | `system_id` | 运行定义路径、支持的操作、产物落盘位置 |
| `validate_parameters` | `system_id` | `valid`、`files`、`parameter_version`、`parameter_hash`、`schema_versions` |
| `is_trading_day` | `system_id`、`date`（可选，默认今天） | 该日期是否交易日（`is_open`）与上一交易日（`pretrade_date`）；数据源 tushare.trade_cal/SSE，**本服务自带判断，不依赖其它 MCP** |
| `calculate` | `system_id`、`operation`、`date`、`industries`（可选）、`positions`（`risk_signal` 必填）、`dry_run`（可选） | 事实 JSON；`dry_run=false` 时写入过程资料 |
| `render` | `system_id`、`artifact`、`date`、`document`（可选）、`dry_run`（可选） | 同名 Markdown，返回落盘路径 |

`calculate` 的四个操作：

| `operation` | 用途 | 关键入参 | 产物 |
|---|---|---|---|
| `select_candidates` | 候选筛选 | `industries` 缺省＝全市场；传入行业数组＝热门行业候选 | `full_market_candidate.json` ／ `hottest_industry_candidate.json` |
| `sector_heat` | 候选行业热度与全市场板块环境 | 前置：当日 `full_market_candidate.json` | `sector_heat.json`、`sector_environment.json` |
| `entry_signal` | 放量突破信号 | `industries` 传入时读 `hottest_industry_candidate.json`，缺省读 `full_market_candidate.json` | `entry_signal.json` |
| `risk_signal` | 持仓风控 | `positions`（必填，缺省时读当日 `positions.json`） | `risk_signal.json`、`state.json`、`prudent_tags.json`、`positions.json` |

- `sector_heat` 一次调用落两份产物；全市场板块环境由本体系自算，不读取其它体系产物。
- `render` 的 `artifact` 取 `candidates`／`sector_heat`／`entry_signal`／`risk_signal`；`document` 省略时按 `date` + `artifact` 读同日过程资料。
- 每次调用重新读取并校验 `params/`，参数改动后无需重启服务。
- 非交易日或当日无行情时按无数据报错，不使用其它日期数据替代。

## 过程产物

统一写入：

```text
交易/过程资料/{date}/热门板块回调低吸体系/    （落 `knowledge/`；归档后同一逻辑路径位于 `archive/`）
```

- `full_market_candidate.json`：全市场候选；
- `hottest_industry_candidate.json`：按行业筛选后的候选；
- `sector_heat.json`：候选行业热度（`short_ma_pct`／`long_ma_pct`／`trend`／`volume_ratio`／`limit_up_count`／`limit_up_clean`）；
- `sector_environment.json`：市场宽度、涨跌停家数、成交额与放量、涨停行业分布、最高连板、大盘三档；
- `entry_signal.json`：放量突破信号；
- `risk_signal.json`：三层风控动作与每只持仓的取数通道；
- `state.json`、`prudent_tags.json`：MA5 观察状态与审慎标签；
- `candidates.md`、`sector_heat.md`、`entry_signal.md`、`risk_signal.md`：`render` 渲染的阅读版。

字段与口径以运行定义 `system.yml`、`params/` 及规则文档为准，本文件不复制阈值。

## 输入结构

`positions`（`calculate(operation="risk_signal")` 入参）是「代码 → 买入价」的映射，由 `trade-management` MCP 的 `portfolio_snapshot` 生成（MNZH 模拟账户），不用估算值：

```json
{
  "positions": {
    "000536.SZ": 3.6
  }
}
```

空仓时传 `{}`；服务按空仓契约把 `state.json`、`prudent_tags.json` 置为空仓位结构，不继承旧快照。

## 错误与降级

- 调用失败返回 `{"ok": false, "error": "..."}`，不产生产物；体系不符、非法操作与缺失必填参数在入口层被拦截。
- 上游产物缺失时报错（如 `sector_heat`、`entry_signal` 缺当日候选产物），不自动补跑、不用历史产物替代。
- 开盘段分钟线按 `params/risk.json` 的 `fallback_sources`（默认 `["official","promax"]`）顺序降级；全失败标 `unavailable`，仍产出 `risk_signal.json`、`state.json`、`prudent_tags.json`，且不刷新审慎标签。
- 服务不可用时如实报告，不改为执行仓库内的历史脚本。

## 依赖

- 服务由 `/opt/venv/bin/python` 启动（`.pi/mcp.json` 已配置），依赖含 `mcp`、`tushare`、`pandas`、`jinja2`。
- Tushare token 读取项目 MCP 的 `.pi/mcp-servers/tushare/.env`，不写入仓库其它文件。
- 官方 `stk_mins` 限频实测 1 次/小时，与 19:00／19:10／19:25 三个任务同处一小时，降级口径见 `交易/交易体系/热门板块回调低吸体系/风控.md`。
- 行情取数接口见 `tushare` 技能；交易日判断用本服务自带的 `is_trading_day`（tushare.trade_cal/SSE）；账户、成交、持仓与现金事实见 `trade-management` 技能。

## 已退役

- 七个知识库脚本已由本服务实现取代，不再作为运行入口（历史版本见 git）：`select_candidates.py`、`sector_heat.py`、`entry_signal.py`、`risk_signal.py`、`render.py`、`runtime_support.py`、`prepare_shared_sector_context.py`。
- `shared_sector_context.json` 停用：跨体系读取（双网格 `sector_facts`）取消，全市场板块环境由本体系 `sector_heat` 自算为 `sector_environment.json`；历史产物保留为证据。
- 知识库内的 `params/`、`scripts/`、`templates/`、`system.yml` 已删除，能力由运行定义目录承载（历史版本见 git）；跳日期证据与案例移到 `笔记/实证分析/`，复盘与过程文档模板随运行定义 `templates/` 一并提供。

---
title: 基于Agent的ETF轮动体系 MCP 介绍
summary: "ETF轮动体系 MCP `agent-etf-rotation-system` 介绍：服务与运行定义位置、四个工具与入参、复盘渲染的 document 结构与产物路径、过程资料与计划产物、行情与账户工具入口（含科创50补充口径）、错误与降级、依赖与边界。本服务不做计算与判定。"
date: 2026-10-17
tags:
  - 交易体系
  - ETF轮动
  - MCP
system-id: agent_etf_rotation_system
---

# 基于Agent的ETF轮动体系 MCP 介绍

## 服务与运行定义

运行契约、参数与模板统一放在运行定义目录，注册见 `.pi/mcp.json`，工具命名空间 `mcp__agent_etf_rotation_system__*`：

```text
.pi/mcp-servers/trade-system/agent_etf_rotation_system/
├── mcp_server.py       # 服务入口与实现（契约、参数校验、复盘渲染）
├── system.yml          # 运行契约：身份、成熟度、账户、操作、参数与模板位置、产物契约、边界
├── params/             # 契约参数唯一来源（runtime：路径与文件名；universe：候选池与费率；不含判定阈值）
└── templates/          # 模板唯一来源（review.md.j2 复盘结构）
```

调用口径（命名规则、入参约定、自检与迁入步骤）见 `trade-system` 技能的 `reference/mcp.md`。

## 本服务不做什么

- **不获取行情**：ETF、指数与宏观数据由 Agent 经 `tushare-data` MCP 获取。
- **不查询账户**：持仓、现金、成交由 Agent 经 `trade-management` MCP 获取与登记。
- **不做计算与判定**：环境评估、候选比较、调仓判断与风控审查由 Agent 依 `规则库/` 执行；本服务不含任何阈值、打分或状态机。
- **不写交易计划**：计划由 18:50 任务按 `交易/交易体系/基于Agent的ETF轮动体系/体系运作流程.md` 与 `规则库/` 生成。

## 工具与入参

`date` 支持 `YYYY-MM-DD` 或 `YYYYMMDD`，产物目录按 `YYYY-MM-DD` 命名；`system_id` 必填且必须为 `agent_etf_rotation_system`。

| 工具 | 入参 | 返回 / 产物 |
|---|---|---|
| `list_systems` | — | 本服务实现的体系 |
| `get_manifest` | `system_id` | 运行定义路径、成熟度、支持的操作、产物契约、边界 |
| `validate_parameters` | `system_id` | `valid`、`files`、`parameter_version`、`parameter_hash`、`schema_versions` |
| `render` | `system_id`、`artifact`（`review`）、`date`、`document`、`dry_run`（可选） | 复盘 Markdown；`dry_run=true` 只返回全文不落盘 |

## 复盘渲染（render, artifact=review）

`document` 必填字段（缺一即报错，不做静默补全）：

| 字段 | 说明 |
|---|---|
| `date` | 必须与入参 `date` 一致 |
| `summary` | 1–2 句概括当日复盘 |
| `trade_summary` | 交易执行摘要（有交易列成交；无交易写「无交易 — 维持持币状态（…）」并引用计划佐证） |
| `exec_review` | 数组，每项 `{item, value}`，至少含计划动作、实际执行、偏差、执行评价 |
| `holdings` | 数组，当前持仓、成本、现金、总资产估算、仓位状态 |
| `market` | 数组，市场环境观察（指数、成交额、板块热点、风险主线，带来源） |
| `improvements` | 数组，体系改进建议（观察记录，不改规则库） |
| `decision_refs` | 数组，给下一交易日计划的决策参考 |

可选字段：`signal_check`（数组，危险/积极信号逐项核对）、`risk_state`（字符串，风控状态）。

产物路径（逻辑路径，落物理根 `knowledge/`）：

```text
交易/交易复盘/<YYYY-MM-DD>/基于Agent的ETF轮动体系_复盘.md
```

处理口径：重复渲染会覆盖同名文件，返回体给出 `overwrote`；结构化复盘先落盘再推送，不需要中间 JSON。渲染只按模板拼装调用端提供的 `document`——**回放与复盘中的事实必须来自 MCP 查询结果**，不得在 `document` 里补造价格、持仓或成交。

## 过程资料与计划产物

| 产物 | 路径（逻辑路径） | 写入方 |
|---|---|---|
| 环境评估与候选比较 | `交易/过程资料/<YYYY-MM-DD>/基于Agent的ETF轮动体系/ETF轮动-选股分析.md`（落 `knowledge/`） | 18:50 任务（Agent 手写） |
| 交易计划 | `交易/交易计划/<下一交易日>/基于Agent的ETF轮动体系_交易计划.md`（落 `knowledge/`） | 18:50 任务 |
| 交易复盘 | `交易/交易复盘/<日期>/基于Agent的ETF轮动体系_复盘.md`（落 `knowledge/`） | 体系 MCP `render` |
| 简报 | `摘要/.abstract/<日期>_agent-etf-rotation-<阶段>.txt`（落 `knowledge/`） | 三个任务 |

历史形态：2026-10-16 及以前的选股分析落在日期目录根层 `交易/过程资料/<日期>/ETF轮动-选股分析.md`（archive 侧同样），保持原路径不改。

## 行情与账户工具入口

Agent 通过 `tushare-data` MCP 获取市场数据、通过 `trade-management` MCP 获取与登记账户事实；不读取 Token，不直接调用 `tushare` Python 客户端。

| 数据 | 工具 | 主要用途 |
|---|---|---|
| 交易日历 | `get_trade_calendar` | 判断交易日与下一交易日 |
| ETF 日线 | `get_fund_daily` | 区间收益、波动、回撤、成交量 |
| ETF 复权因子 | `get_fund_adj` | 除权与收益口径核验 |
| ETF 分钟线 | `get_fund_minutes` | 按计划时点回放成交 |
| ETF 基础资料 | `get_fund_basic`／`etf_basic` | 费率、上市状态、跟踪指数核验 |
| A 股指数 | `get_index_daily` | 沪深300、科创50 等市场环境 |
| 海外指数 | `get_index_global` | 标普500 等海外环境 |
| CPI／PMI／Shibor／美债收益率 | `get_cpi`／`get_pmi`／`get_shibor`／`get_us_treasury_curve` | 通胀、景气、流动性与海外利率环境 |
| 账户、成交、持仓、现金 | `trade-management`（`portfolio_snapshot`／`trade_record` 等） | 模拟账户事实与记账 |

候选池、代码与费率以运行定义 `params/universe.json` 为准（`validate_parameters` 校验，`get_manifest` 的 `universe` 返回代码与费率；方法说明见 `规则库/ETF池.md`，本文件不重复标的表）。所有取数结果检查 `ok`、`row_count`、`source` 与 `warnings`；空结果要区分非交易日、权限不足、参数错误与真实无数据。

**科创50 补充口径**：复盘或回放缺少 `588000.SH` 精确收盘价、成交量或指数参照时，用 `get_fund_daily(ts_code="588000.SH", …)` 取 ETF 行情、`get_index_daily(ts_code="000688.SH", …)` 取科创50 指数、`get_fund_minutes(ts_code="588000.SH", freq="1min", …)` 取分钟线。ETF 必须用 `get_fund_daily`，不能用股票日线工具；科创50 指数后缀为 `.SH`（不套用 000xxx 段的股票规则）。数据缺失或代理降级要在复盘中注明。

## 错误与降级

- 调用失败返回 `{"ok": false, "error": "..."}`，不产生产物；入口 schema 会拦截缺失入参、非法 `artifact` 与体系不符。
- 渲染失败时把 `document` 留在回复中并说明失败阶段；不产出半成品文件。
- 服务不可用时如实报告，不改为直接执行仓库内的历史脚本。

## 依赖

- 服务由 `/opt/venv/bin/python` 启动（`.pi/mcp.json` 已配置），依赖含 `mcp`、`jinja2`。
- 服务不读取行情 Token；行情取数由 `tushare-data` MCP 负责（其 token 在 `.pi/mcp-servers/tushare/.env`）。
- `/opt/venv` 属 root 且不在挂载点上（随容器可写层）：容器重建后若报 `ModuleNotFoundError`，由 root 执行 `uv pip install --python /opt/venv/bin/python jinja2` 补回。

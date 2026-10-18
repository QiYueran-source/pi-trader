---
title: 红利科创ETF双网格体系 MCP 介绍
summary: "双网格体系 MCP `div-etf-grid-trade` 介绍：服务与运行定义位置、五个工具与入参、过程产物写入位置、`positions`/`human_review` 输入结构、错误与降级口径、依赖说明与已退役脚本清单。"
date: 2026-10-17
tags:
  - 交易体系
  - 红利科创ETF双网格体系
  - MCP
system-id: div_etf_grid_trade
---

# 红利科创ETF双网格体系 MCP 介绍

## 服务与运行定义

体系计算、参数校验与渲染统一通过 MCP 服务 `div-etf-grid-trade` 完成，注册见 `.pi/mcp.json`，工具命名空间 `mcp__div_etf_grid_trade__*`。运行定义目录：

```text
.pi/mcp-servers/trade-system/div_etf_grid_trade/
├── mcp_server.py       # 服务入口与实现
├── system.yml          # 运行契约：身份、账户、操作、参数与模板位置、产物契约、边界
├── params/             # 参数唯一来源
└── templates/          # 模板唯一来源
```

调用口径（命名规则、入参约定、自检与迁入步骤）见 `trade-system` 技能的 `reference/mcp.md`。术语与参数键名对照见 `交易/交易体系/红利科创ETF双网格体系/网格参数.md`。

## 工具与入参

`date` 支持 `YYYY-MM-DD` 或 `YYYYMMDD`，产物目录按 `YYYY-MM-DD` 命名；`system_id` 必填且必须为 `div_etf_grid_trade`。

| 工具 | 入参 | 返回 / 产物 |
|---|---|---|
| `list_systems` | — | 本服务实现的体系 |
| `get_manifest` | `system_id` | 运行定义路径、支持的操作、产物落盘位置 |
| `validate_parameters` | `system_id` | `valid`、`files`、`parameter_version`、`parameter_hash`、`schema_versions` |
| `calculate` | `system_id`、`operation`（`risk_facts`／`regulator_facts`／`sector_facts`）、`date`、`positions`（除 `sector_facts` 外必填）、`human_review`（可选）、`skip_emotion`（可选）、`dry_run`（可选） | 事实 JSON；`dry_run=false` 时写入过程资料 |
| `render` | `system_id`、`artifact`、`date`、`document`（可选；省略时按 `date` + `artifact` 读同日过程资料） | 同名 `.md`，返回落盘路径 |

- 每次调用重新读取并校验 `params/` 下 6 个参数文件，参数改动后无需重启服务。
- 非交易日或当日无行情时按无数据报错，不使用其它日期数据替代。
- 情绪涨跌停采用分板口径（主板 10%、创业板/科创板 20%、北交所 30%），与 `sector_facts` 一致。

## 过程产物

统一写入：

```text
交易/过程资料/{date}/红利科创ETF双网格体系/    （落 `knowledge/`；归档后同一逻辑路径位于 `archive/`）
```

- `calibration_check.json`：空仓时的基准价重设检查与参数校验；
- `positions.json`：运行前的实际持仓事实；
- `risk_facts.json`：风险事实（双标的）；
- `sector_facts.json`：板块事实；
- `regulator_facts.json`：硬闸占用、买卖两侧实际档距与份数、保底仓与卖腿开关、信号评估与建议防守档；
- `human_review.json`：防守档审批留痕（默认空）。

`regulator_facts.json` 的 `legs.<腿>.effective` 字段：`buy_step_ratio`、`buy_raw_step_ratio`、`step_cap`、`capped`、`buy_shares`、`buy_enabled`、`sell_step_ratio`、`sell_raw_step_ratio`、`sell_shares`、`sell_enabled`、`sell_disabled_reason`、`reserve_floor`（后两项用于保底仓停卖）。每个量吃哪些倍数由 `params/regulator.json#scaling` 声明：买入档距＝防守×资金且受买入上限；卖出档距＝防守且无上限；买卖份数＝防守份数倍数并按 100 份向下取整。

契约细节以运行定义 `system.yml` 的 `process_output` 为准；历史 `output/` 目录（v3 之前的产物布局）只作迁移前证据保留，体系 MCP 不读取也不写入。

## 输入结构

`positions`（`calculate` 入参）必须包含真实持仓与现金：

```json
{
  "positions": {
    "dividend": {"shares": 0, "market_value_amount": 0},
    "growth": {"shares": 0, "market_value_amount": 0}
  },
  "cash": 0
}
```

- `cash` 必填；缺失或非数值会被拒绝。
- `market_value_amount` 可省略，缺省时按 `shares × 当日收盘价` 计算。
- 体系不访问券商账户；调用端必须先用 `trade-management` MCP 生成真实持仓事实。

`human_review`（防守档审批留痕，可选）字段见运行定义 `params/regulator.json#approval`；其中 `level` 为体系级防守档，`per_leg`（如 `{"growth": "A2"}`）按腿覆盖、未写出的腿沿用 `level`。产物回显 `defense.effective_levels` 与 `legs[].defense_level`。

## 错误与降级

- 调用失败返回 `{"ok": false, "error": "..."}`，不产生产物；缺失必填参数、体系不符与非法操作在入口层被拦截。
- 失败时记录失败阶段与错误信息并停止依赖该事实的下游步骤；不估算、不编造、不用历史产物冒充当日结果。
- 服务不可用时如实报告，不改为直接执行仓库内的历史脚本。

## 依赖

- 服务由 `/opt/venv/bin/python` 启动（`.pi/mcp.json` 已配置），依赖含 `mcp`、`tushare`、`jinja2`。
- Tushare token 读取项目 MCP 的 `.pi/mcp-servers/tushare/.env`，不写入仓库其它文件。
- `/opt/venv` 属 root 且不在挂载点上（随容器可写层）：容器重建后若报 `ModuleNotFoundError`，由 root 执行 `uv pip install --python /opt/venv/bin/python jinja2` 补回。`uv` 的缓存 `/opt/uv/cache` 已对 node 用户开放。
- 行情与交易日历的取数接口见 `tushare` 技能；账户与持仓事实见 `trade-management` 技能。

## 已退役

- v4 收尾时删除知识库内的体系脚本 `collect_risk_facts.py`、`collect_regulator_facts.py`、`collect_sector_facts.py`、`render.py`、`runtime_support.py`，能力全部由本服务实现（可在 git 历史中查阅）。
- v4 之前已退役：`should_calibrate.py`、`calculate_grid.py`（回撤步长）、`apply_state_transition.py`、`build_switch_instruction.py`（状态机）。

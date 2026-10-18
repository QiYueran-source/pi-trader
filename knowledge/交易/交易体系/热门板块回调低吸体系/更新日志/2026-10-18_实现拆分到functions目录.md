---
title: 实现拆分到 functions 目录、清理死代码 | 2026-10-18
summary: "热门板块回调低吸体系 MCP 由单文件 1466 行拆为入口 221 行 + `functions/` 八个模块（paths / parameters / market / limitup / selection / sector_heat / signals / artifacts），函数体逐字搬运；并删除两个无调用点定义（`list_tools_legacy`、`call_tool_legacy`）。验证：59 个顶层定义逐字比对仅上述两个被删；真实 stdio 握手工具面不变（list_systems／get_manifest／validate_parameters／is_trading_day／calculate／render）；`get_manifest`（仅 minutes 文案按同日口径收口更新）、`validate_parameters`、`is_trading_day` 与两日四段 `calculate(dry_run)`（select_candidates／sector_heat／entry_signal／risk_signal）拆分前后逐字段一致。"
date: 2026-10-18
reason: 用户 2026-10-18 裁定「热门板块第 4 项（1440+ 行单文件）要拆」，沿用双网格／双债LOF／轮动的 `functions/` 样板
tags:
  - 交易体系
  - 更新日志
  - 热门板块
system-id: hot_sector_pullback_system
system-name: 热门板块回调低吸体系
---

# 实现拆分到 functions 目录、清理死代码 | 2026-10-18

## 一、动因与范围

单文件 1466 行、62 个顶层定义同时承载路径与 IO、参数校验、行情取数、涨跌停口径、候选、板块热度、建仓与风控信号、状态与审慎标签、渲染与工具路由。范围限本体系运行定义；**未改** `params/`（同日口径收口除外，见另篇日志）、`templates/` 与任务注册。

## 二、变更

| 模块 | 迁入内容 |
|:--|:--|
| `mcp_server.py` | 1466 → 221 行，只留 `TOOLS`、`tool_calculate`、`list_tools_result`、`call_tool_result` 与 stdio 装配；`sys.path` 自举后从 `functions/` 导入 |
| `functions/paths.py` | 常量、`load_env`、`normalize_date`、`read_json`/`write_json`、`logical_root`、`process_roots`/`process_dir`/`resolve_process_file`/`logical_process_path`/`load_process_document`/`latest_snapshot`、`params/` 存在性守卫 |
| `functions/parameters.py` | `fail`／`require_*` 校验族、`load_parameters`、`validate_parameters`、`parameter_metadata` |
| `functions/market.py` | `get_client`、`fetch_trade_days`／`fetch_trade_calendar`、`fetch_daily_market`、`fetch_stock_info`、`fetch_index_pct`、窗口计算 |
| `functions/limitup.py` | 分板阈值判定 `limit_pct`／`hit_limit`、`is_st`、新股与首日排除 |
| `functions/selection.py` | 均线、回调过滤、`build_candidates`、`build_signal`、`op_select_candidates` |
| `functions/sector_heat.py` | `build_sector_environment`、`sector_statistics`、`op_sector_heat` |
| `functions/signals.py` | `signalize`、开盘段形态与取数、审慎标签、`evaluate_risk`、`op_entry_signal`、`op_risk_signal` |
| `functions/artifacts.py` | `artifact`、`RENDER_TARGETS`、`render_artifact` |
| 删除定义 | `list_tools_legacy`、`call_tool_legacy`（兼容分支走 `hasattr` 判断，不经过它们） |

## 三、验证

- 逐字搬运：新旧 61 个顶层定义逐一比对，除上述 2 个被删定义外**完全一致**。
- 工具面：6 个工具不变（`list_systems`／`get_manifest`／`validate_parameters`／`is_trading_day`／`calculate`／`render`）。
- 行为对照（拆分前副本 vs 拆分后，同输入、`dry_run`）：2026-10-15 四段事实全部成功，2026-10-16 四段（其中 `sector_heat`／`entry_signal` 按上游缺失报错）——**逐字段一致**；`get_manifest` 仅 `fact_sources.minutes` 文案按同日口径收口更新，其余字段一致；`validate_parameters`（`valid=true`）、`is_trading_day`（10-16 开市）一致。
- 过程：拆分首轮遗漏若干模块级 import（`Path`／`hashlib`／`timedelta`／`defaultdict`／入口的 `logical_root`、`BENCHMARK_INDEX`、`fetch_trade_calendar`、`get_client`、`artifact`、`fail`），均在复算前发现并补齐；复算即以上述结果为准。

## 四、遗留

- 运行中的 MCP 子进程仍加载拆分前单文件（行为已验证一致），重启或新会话后加载新结构。

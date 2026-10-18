---
title: 实现拆分到 functions 目录、金额口径裁定与入口清理 | 2026-10-18
summary: "招商双债LOF择时体系按「服务实现结构」与「单一事实源」两套新要求收口：`mcp_server.py` 由 697 行拆为入口 141 行 + `functions/` 六个模块（paths/parameters/market/state/signals/artifacts），函数体逐字搬运；删除 3 个无调用点函数（`write_json`、`list_tools_legacy`、`call_tool_legacy`）。金额口径经流水对账后裁定为「按执行日当前可用现金执行」并落入 SOP §6.1，SOP 不再硬编码体系现金；跨日状态解析裁定为本体系自带、不抽共享模块。验证：35 个顶层定义逐字比对仅 3 个死代码被删；真实 stdio 握手 5 工具、参数哈希不变（`c289e221…`）；拆分前后 8 组调用（含 09-16 历史日、非交易日、非法 operation、体系不符）输出逐字段一致；`replay_check`（10-16）与渲染报告正文逐字一致。"
date: 2026-10-18
reason: 用户 2026-10-18 要求按新沉淀的「单一事实源」（`trade-system/reference/single-source.md`）与「服务实现结构」（`agent-dev/mcp-management`）优化本体系；并逐项裁定：金额按当前现金、拆分照做、状态模块不抽、`trading_day_only` 暂不改、死代码修复
tags:
  - 交易体系
  - 更新日志
  - 双债LOF
system-id: zslof_timing_trade
system-name: 招商双债LOF择时体系
---

# 实现拆分到 functions 目录、金额口径裁定与入口清理 | 2026-10-18

## 一、动因与范围

按 `trade-system` 技能的 `reference/single-source.md` 与 `agent-dev/mcp-management` 的「服务实现结构」复核本体系。范围：运行定义实现结构与入口清理、SOP 金额口径、关联计划文书；**未改** `params/`、`templates/`、`system.yml`、任务 prompt 与运行时注册。

## 二、变更清单

| 对象 | 变更 | 说明 |
|:--|:--|:--|
| `.pi/mcp-servers/trade-system/zslof_timing_trade/mcp_server.py` | 697 → 141 行，只留工具注册与路由 | 保留 `TOOLS`、`server`、`list_tools_result`、`call_tool_result`、`tool_calculate` 与 stdio 装配；加 `sys.path` 自举后从 `functions/` 导入 |
| 同目录新增 `functions/` | 六个模块 + `__init__.py` | `paths.py`（常量、路径、基础 IO）、`parameters.py`（校验与元数据）、`market.py`（客户端与日线）、`state.py`（初始状态、最近先前过程日、逐日推进）、`signals.py`（判据、信号与重放校验）、`artifacts.py`（产物与渲染）；函数体逐字搬运 |
| 同上 | 删除 3 个无调用点函数 | `write_json`（定义后从未调用）、`list_tools_legacy`／`call_tool_legacy`（兼容分支走 `hasattr` 判断，不经过它们） |
| `交易/交易体系/招商双债LOF择时体系/MCP介绍.md` | 运行定义目录树补 `functions/` 一行 | `mcp_server.py` 注释改为「服务入口（只做工具注册与路由）」 |
| `交易/交易体系/招商双债LOF择时体系/体系介绍.md` | 文件索引补 `functions/`（实现模块） | |
| `交易/交易体系/招商双债LOF择时体系/体系运作流程.md` | §6.1 金额口径由「未决」改为「已裁定」；体系现金改为当场查 `trade-management` | 用户裁定：不要硬编码体系现金，说明查流水即可 |
| `交易/交易计划/2026-10-16/招商双债LOF择时体系_交易计划.md` | `T-2026-10-16-12` 回填 `[x]` | 记决议与对账结论 |
| `交易/交易计划/2026-10-19/招商双债LOF择时体系_交易计划.md` | 摘要与风险段的口径由「未决」改「已裁定」 | 口径执行基准＝执行日当前可用现金 |

## 三、金额口径裁定依据（流水对账）

体系现金 24,861.19 的来源：注资 25,000（2026-08-03 两笔 10,000 + 15,000）− 6 笔买入 107,020.40 + 9 笔卖出（账本入账额）106,881.59 = **24,861.19**，与 `portfolio_snapshot(YHZQ, zslof_timing_trade)` 逐分一致（`trade_as_of` 2026-10-15 10:15:04，持仓为空）。

结论：25,000 是名义计划金额（注资额），差的 138.81 是已实现净亏（毛亏 107.60 + 10-15 三笔卖出扣费 31.21），非记账误差；先例为 10-09 信号买入按 15,000 份 × 1.654 = 24,810.00 执行。故裁定按执行日当前可用现金执行。

## 四、验证

- 逐字搬运：新旧文件 35 个顶层定义（含 async）逐一比对，除上述 3 个死代码外**完全一致**；删除项在全部文件中无残留。
- 加载：入口与 6 个模块均可导入；真实 stdio 握手 `initialize` → `tools/list` 5 个工具 → `get_manifest`（`system_root`／`parameter_root`／`template_root` 指向本目录）→ `validate_parameters` `valid=true`、`parameter_hash` 仍为 `c289e221…`。
- 行为对照（拆分前副本 vs 拆分后，同一输入）：`calculate(signal, 2026-10-16)`、`calculate(signal, 2026-09-16)`、`calculate(replay_check, 2026-10-16)`（`matched=true`）、非交易日（2026-10-17 无行情报错）、非法 operation（schema 拦截）、体系不符——**逐字段一致**；`render`（以当日新算 `signal_facts` 为 document，沙盒 `PI_PROJECT_DIR=/tmp/zslofverify`）报告正文忽略 `updated_at` 后**逐字一致**。
- 副作用：除 `mcp_server.py` 与新增 `functions/` 外无仓库写入；全程 `dry_run` 或沙盒项目目录。

## 五、裁定与遗留

- `params/runtime.json#trading_day_only` 只被校验类型、实现未使用：**已于 2026-10-18 删键**（见 `交易/交易体系/招商双债LOF择时体系/更新日志/2026-10-18_删除trading_day_only.md`）。
- 跨日状态解析（`knowledge/` 优先、`archive/` 兜底）：**不抽共享模块**，各体系自带一份；口径以各体系 SOP 为准（本体系见 §2.1，2026-10-17 用户确认）。
- 遗留待办：`T-2026-10-18-13`（删除 `timing.json#counter_semantics` 两条未被实现读取的英文口径）、`T-2026-10-18-14`（标注 `signal_timing`／`execution_timing` 为不可配置声明键）。
- 当前运行中的 MCP 子进程仍加载拆分前的单文件（行为已验证一致），下次重启或新会话即加载新结构。

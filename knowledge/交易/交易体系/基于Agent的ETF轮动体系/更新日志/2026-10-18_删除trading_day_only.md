---
title: 删除 trading_day_only（声明但实现从不读取） | 2026-10-18
summary: "按用户 2026-10-18 裁定删除 `params/runtime.json#trading_day_only`：该键只被校验器检查数据类型、实现从不读取，交易日限制实际由「非交易日取不到行情即报错」兜底，本服务现已自带 `is_trading_day` 工具承担交易日判断。`schema_version` 1→2，参数哈希由 9b0f04cb… 变为 ea326b03…；校验器同步移除该键。验证：`validate_parameters` 通过、`is_trading_day` 与本体系计算工具复测正常。"
date: 2026-10-18
reason: 用户 2026-10-18 裁定「这个挂账也处理，删掉键吧」
tags:
  - 交易体系
  - 更新日志
system-id: agent_etf_rotation_system
system-name: 基于Agent的ETF轮动体系
---

# 删除 trading_day_only（声明但实现从不读取） | 2026-10-18

## 一、动因

`params/runtime.json#trading_day_only` 一直只被校验器做类型检查，实现里没有任何读取点；非交易日的实际拦截靠「取不到行情报错」。本服务现已自带 `is_trading_day` 工具（2026-10-18 新增），交易日判断有正式入口，该键只会误导读者以为「已强制限制」。

## 二、变更

| 对象 | 变更 |
|:--|:--|
| `params/runtime.json` | 删除 `trading_day_only`；`schema_version` 1→2；加 `note` 说明删除原因与替代工具 |
| `functions/parameters.py` | 从 runtime 必填字段集合移除该键，并删除对应的 `require_bool` 校验 |
| 参数哈希 | `9b0f04cb…` → `ea326b03…`（`schema_versions.runtime = 2`） |

## 三、验证

- `validate_parameters`：`valid=true`，`schema_versions.runtime=2`。
- 工具复测：`is_trading_day`（2026-10-16 开市 / 2026-10-18 休市）与`get_manifest`／`render` 契约校验正常。
- 全仓扫描：`trading_day_only` 在四个体系的实现与参数中已无残留（历史更新日志按「历史不回改」保留）。

## 四、遗留

运行中的 MCP 子进程仍为改动前进程，需重启 Pi 或新会话后加载新参数（同时加载本服务的新工具与其它同批改动）。

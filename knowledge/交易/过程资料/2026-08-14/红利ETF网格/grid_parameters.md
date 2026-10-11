---
uuid: fa028f1e73965246a0f1c07d155aa46d
title: 红利ETF网格 - 网格参数 2026-08-14
tags:
  - 交易体系
  - 过程资料
  - 网格参数
updated: 2026-08-14 18:15:41

system-id: div_etf_grid_trade
---

# 网格参数 | 2026-08-14

> 来源：`/hermes-trader/knowledge/交易/过程资料/2026-08-14/红利ETF网格/grid_parameters.json`

| 标的 | 最新收盘 | 最大回撤 | 买步长 | 卖步长 | 买入份数 | 卖出份数 |
|---|---:|---:|---:|---:|---:|---:|
| 红利ETF易方达（515180.SH） | 1.4080 | 1.76% | 1.00% | 1.01% | 600 | 500 |
| 双创50ETF易方达（159781.SZ） | 1.1490 | 16.06% | 3.21% | 3.32% | 400 | 400 |


## 计算口径

- 数据窗口：各标的最近 10 个交易日。
- 买步长：max_drawdown_ratio * drawdown_coefficient。
- 卖步长：1 / (1 - buy_step_ratio) - 1。
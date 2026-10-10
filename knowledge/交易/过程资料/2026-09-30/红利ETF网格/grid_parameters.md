---
uuid: 3c3242edb4d157bb91840faf23850dfe
title: 红利ETF网格 - 网格参数 2026-09-30
tags:
  - 交易体系
  - 过程资料
  - 网格参数
updated: 2026-09-30 18:13:55
links: []
system-id: div_etf_grid_trade
---

# 网格参数 | 2026-09-30

> 来源：`/hermes-trader/knowledge/交易/过程资料/2026-09-30/红利ETF网格/grid_parameters.json`

| 标的 | 最新收盘 | 最大回撤 | 买步长 | 卖步长 | 买入份数 | 卖出份数 |
|---|---:|---:|---:|---:|---:|---:|
| 红利ETF易方达（515180.SH） | 1.4170 | 1.83% | 1.00% | 1.01% | 1000 | 800 |
| 双创50ETF易方达（159781.SZ） | 0.9800 | 9.68% | 1.94% | 1.97% | 1000 | 1000 |


## 计算口径

- 数据窗口：各标的最近 10 个交易日。
- 买步长：max_drawdown_ratio * drawdown_coefficient。
- 卖步长：1 / (1 - buy_step_ratio) - 1。
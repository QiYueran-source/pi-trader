---
uuid: 0e22689f30a3584a945fb3ce92eca47d
title: 红利ETF网格 - 网格参数 2026-09-18
tags:
  - 交易体系
  - 过程资料
  - 网格参数
updated: 2026-09-18 18:03:05
links: []
system-id: div_etf_grid_trade
---

# 网格参数 | 2026-09-18

> 来源：`/hermes-trader/knowledge/交易/过程资料/2026-09-18/红利ETF网格/grid_parameters.json`

| 标的 | 最新收盘 | 最大回撤 | 买步长 | 卖步长 | 买入份数 | 卖出份数 |
|---|---:|---:|---:|---:|---:|---:|
| 红利ETF易方达（515180.SH） | 1.4090 | 4.21% | 1.00% | 1.01% | 600 | 500 |
| 双创50ETF易方达（159781.SZ） | 1.0670 | 8.75% | 1.75% | 1.78% | 400 | 400 |


## 计算口径

- 数据窗口：红利最近 10 个交易日；双创最近 22 个交易日。
- 买步长：max_drawdown_ratio * drawdown_coefficient（不低于 minimum_step_ratio）。
- 卖步长：1 / (1 - buy_step_ratio) - 1。
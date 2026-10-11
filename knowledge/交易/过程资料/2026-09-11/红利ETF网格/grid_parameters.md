---
uuid: 749ffe1acf655fb89c8547064ed988f4
title: 红利ETF网格 - 网格参数 2026-09-11
tags:
  - 交易体系
  - 过程资料
  - 网格参数
updated: 2026-09-11 18:02:04

system-id: div_etf_grid_trade
---

# 网格参数 | 2026-09-11

> 来源：`/hermes-trader/knowledge/交易/过程资料/2026-09-11/红利ETF网格/grid_parameters.json`

| 标的 | 最新收盘 | 最大回撤 | 买步长 | 卖步长 | 买入份数 | 卖出份数 |
|---|---:|---:|---:|---:|---:|---:|
| 红利ETF易方达（515180.SH） | 1.4350 | 2.45% | 1.00% | 1.01% | 600 | 500 |
| 双创50ETF易方达（159781.SZ） | 1.0330 | 13.20% | 2.64% | 2.71% | 400 | 400 |


## 计算口径

- 数据窗口：各标的最近 10 个交易日。
- 买步长：max_drawdown_ratio * drawdown_coefficient。
- 卖步长：1 / (1 - buy_step_ratio) - 1。
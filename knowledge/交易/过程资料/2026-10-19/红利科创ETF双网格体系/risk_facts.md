---
title: 红利科创ETF双网格体系 - 风险事实 2026-10-19
summary: "2026-10-19 风险事实：双标的采集阈值与命中项（只陈述事实与阈值命中，不生成交易结论）。"
tags:
  - 交易体系
  - 过程资料
  - 风险事实
date: 2026-10-19
system-id: div_etf_grid_trade
---

# 风险事实 | 2026-10-19

> 来源：`交易/过程资料/2026-10-19/红利科创ETF双网格体系/risk_facts.json`。本报告只陈述事实和阈值命中，不生成交易结论；v4 起采集双标的，资本约束见 `params/regulator.json#capital_guard`。


## dividend

| 指标 | 值 |
|---|---:|
| 收盘价 | 1.3900 |
| 日涨跌幅 | 0.94% |
| 量比 | 1.19 |
| 平均振幅 | 1.27% |
| 连续下跌 | 0 个交易日（累计 0.00%） |
| 单腿权重（基数＝system_nav） | 14.49% |
| 价格边界（下/上） | 1.0822 / 1.8759 |

### 阈值命中

- `below_price_boundary`：否
- `above_price_boundary`：否
- `consecutive_down`：否
- `sharp_drop_with_volume`：否
- `sharp_rise_notice`：否
- `sharp_rise_take_profit_notice`：否


## growth

| 指标 | 值 |
|---|---:|
| 收盘价 | 0.8400 |
| 日涨跌幅 | -1.52% |
| 量比 | 0.91 |
| 平均振幅 | 3.05% |
| 连续下跌 | 6 个交易日（累计 11.02%） |
| 单腿权重（基数＝system_nav） | 39.42% |
| 价格边界（下/上） | 0.6608 / 1.2272 |

### 阈值命中

- `below_price_boundary`：否
- `above_price_boundary`：否
- `consecutive_down`：是
- `sharp_drop_with_volume`：否
- `sharp_rise_notice`：否
- `sharp_rise_take_profit_notice`：否

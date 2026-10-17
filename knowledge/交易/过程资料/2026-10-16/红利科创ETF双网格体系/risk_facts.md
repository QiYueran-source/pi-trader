---
title: 红利科创ETF双网格体系 - 风险事实 2026-10-16
tags:
  - 交易体系
  - 过程资料
  - 风险事实
date: 2026-10-16
system-id: div_etf_grid_trade
---

# 风险事实 | 2026-10-16

> 来源：`/pi-trader/knowledge/交易/过程资料/2026-10-16/红利科创ETF双网格体系/risk_facts.json`。本报告只陈述事实和阈值命中，不生成交易结论；v4 起采集双标的，资本约束见 `params/regulator.json#capital_guard`。


## dividend

| 指标 | 值 |
|---|---:|
| 收盘价 | 1.3770 |
| 日涨跌幅 | -3.57% |
| 量比 | 1.47 |
| 平均振幅 | 1.27% |
| 连续下跌 | 2 个交易日（累计 5.94%） |
| 单腿权重（基数＝system_nav） | 7.16% |
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
| 收盘价 | 0.8530 |
| 日涨跌幅 | -0.23% |
| 量比 | 1.29 |
| 平均振幅 | 3.06% |
| 连续下跌 | 5 个交易日（累计 9.64%） |
| 单腿权重（基数＝system_nav） | 39.93% |
| 价格边界（下/上） | 0.6608 / 1.2272 |

### 阈值命中

- `below_price_boundary`：否
- `above_price_boundary`：否
- `consecutive_down`：是
- `sharp_drop_with_volume`：否
- `sharp_rise_notice`：否
- `sharp_rise_take_profit_notice`：否



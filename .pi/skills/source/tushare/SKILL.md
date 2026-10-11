---
name: tushare
description: 通过 tushare-data MCP 获取股票、ETF、指数、交易日历和分钟行情；用于财经分析、交易体系事实采集和市场数据核验。
author: pi-trader
version: 2.0.0
---

# Tushare 数据

## 路由

需要实际查询行情、交易日历、股票资料或分钟线时，调用 `tushare-data` MCP。不要自行拼接 HTTP 请求，不要直接读取或输出 Token。

| 需求 | 工具 |
|---|---|
| 交易日判断 | `get_trade_calendar` |
| 单只股票日线 | `get_stock_daily` |
| 全市场股票日线 | `get_market_daily` |
| ETF/基金日线 | `get_fund_daily` |
| 指数日线 | `get_index_daily` |
| 股票基础资料 | `get_stock_basic` |
| 股票分钟线 | `get_stock_minutes` |

## 数据口径

- 股票代码必须带交易所后缀：`.SH`、`.SZ` 或 `.BJ`。
- ETF 和基金使用 `get_fund_daily`，不要用股票日线工具代替。
- 指数使用 `get_index_daily`，不要根据股票代码段推断指数交易所。
- 全市场涨停筛选使用 `get_market_daily`，传入交易日，不传股票代码。
- 日期使用 `YYYYMMDD` 或 `YYYY-MM-DD`；分钟线使用完整时间。
- 每次取数后检查 `ok`、`row_count`、请求日期和 `warnings`。
- 空数据必须区分非交易日、未上市、参数错误、权限不足和真实无数据。

## 数据源

- 日线、指数、基础资料和交易日历优先使用官方 Tushare。
- 分钟线官方失败后由 MCP 自动切换代理。
- 返回结果中的 `source` 表示实际数据源，`fallback_used` 表示是否发生降级。
- 代理数据必须检查 `trade_time` 日期；日期不一致时不得用于交易判断。
- 代理只用于读取数据，不用于交易提交、持仓修改或资金操作。

## 交易体系使用

热门板块回调低吸体系的主要数据对应关系：

- 全市场候选：`get_market_daily` + `get_stock_basic`；
- 大盘环境：`get_index_daily`；
- 个股均线和成交量：`get_stock_daily`；
- 开盘段风控：`get_stock_minutes`；
- 交易日顺延：`get_trade_calendar`。

体系脚本可以使用项目内共享数据客户端完成批量计算；Agent 的交互式取数统一使用 MCP。过程资料必须记录日期、接口、实际来源和异常信息。

## 限制处理

- 权限不足、频率限制和网络错误必须原样记录，不将失败伪装为空结果。
- 长区间或大量标的应分段获取，避免一次请求过大。
- 数据来源切换后，复盘中注明官方或代理来源。
- MCP 只提供数据，不替代交易体系的规则判断，也不执行真实交易。

## 本地调试

MCP 的密钥文件位于其目录下的 `.env`，模板为 `.env.example`。CLI 技能和旧来源技能仅用于人工调试或 MCP 尚未覆盖的接口，不作为交易体系默认数据入口。

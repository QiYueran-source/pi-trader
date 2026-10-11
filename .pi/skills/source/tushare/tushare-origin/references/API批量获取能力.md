# Tushare API 批量获取能力速查

按 `trade_date` 或单参数能批量拉全市场的接口：

| 接口 | 批量方式 | 返回量 | 备注 |
|------|---------|--------|------|
| `daily` | `trade_date=X` 不传 ts_code | 全市场~5000条 | 日行情，按天拉全量 |
| `daily_basic` | `trade_date=X` 不传 ts_code | 全市场~5000条 | 含总市值、PE、PB |
| `stock_basic` | 不传参数 | 全市场~5000条 | 基础信息 |
| `trade_cal` | `start_date/end_date` | 全部交易日 | 交易日历 |
| `index_member_all` | `index_code=X` | 全部成分股 | 指数历史成分股 |

**必须传 `ts_code` 逐个股票拉取的接口：**

| 接口 | 限制 | 最优方案 |
|------|------|---------|
| `income`（利润表） | 一次只能拉1只股票 | 并发池 + pickle缓存 |
| `balancesheet`（资产负债表） | 同上 | 并发池 + pickle缓存 |
| `fina_indicator`（财务指标） | 同上 | 如果只需要现成的 roic/ebit/ev，一个接口替代 income+bs |

**⚠️ fina_indicator 并发陷阱**

全市场 5000+ 只股票逐只拉取时，**高并发 + 短间隔会导致大量请求超时（~64%失败率）**。

**推荐两阶段法：**

1. **阶段1（快速扫）：** `ThreadPoolExecutor(max_workers=10)` + 每只 sleep(0.12s)，能拉到 30-40%
2. **阶段2（补拉）：** 记录所有失败股票，改单线程 + sleep(0.25s) + `socket.setdefaulttimeout(60)` 重拉
3. 每 200 只保存一次中间结果，支持断线续传

单线程全市场补拉大约 15-20 分钟。

**重要：** `fina_indicator` 对金融股（银行/保险/证券/房地产）返回的 `roic`、`ebit`、`invest_capital`、`networking_capital` 全部为 NaN。需按行业字段排除金融类股票。

**缓存策略：** 首次慢（单线程全市场约 25 分钟），缓存后秒出
**增量更新：** 只拉缺失的股票，已有缓存的跳过
**`fina_indicator` 含 `roic`、`ebit`、`invest_capital`、`networking_capital`，一个接口可替代 income + 部分 bs 计算

**积分限制说明：**
- 即使2000+积分，以上财报接口仍需传 ts_code
- `daily_basic` 按 `trade_date` 全量拉无此限制

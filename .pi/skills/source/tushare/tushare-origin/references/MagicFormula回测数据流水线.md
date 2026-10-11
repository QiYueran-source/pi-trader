# Magic Formula 回测数据流水线（A 股）

> 全市场5年回测的完整数据获取与计算流程。

## 数据依赖

| 数据 | 接口 | 批量方式 | 备注 |
|------|------|---------|------|
| 股票列表 | `stock_basic` | 一次性全拉 | 筛选活跃A股(非ST、非北交所、上市满1年) |
| 交易日历 | `trade_cal` | 一次性全拉 | 确定季度末调仓日 |
| 财务指标 | `fina_indicator` | **必须传 ts_code 逐只拉取** | 含 roic, ebit, invest_capital 等 |
| 估值数据 | `daily_basic` | 按 trade_date 全市场批量 | 仅需调仓日数据(含 total_mv) |
| 日线行情 | `daily` | 按 trade_date 全市场批量 | 全区间所有交易日(用于计算持仓收益) |

## ⚠️ 已知坑点

### total_mv 的单位是万元，不是元

`daily_basic.total_mv`（总市值）的数值单位是 **万元（CNY 10,000）**，不是元。

```python
# 错误：以为单位是元
merged = merged[merged["total_mv"] >= 1e9]       # ← 10亿，清洗后0只通过

# 正确：单位是万元
merged = merged[merged["total_mv"] >= 100000]     # ← 10亿=100,000万元 ✅
```

如果不做此转换，市值过滤条件会错误地排除所有股票。这是 tushare 官方文档中少数不标注单位的关键字段之一。

## 核心指标计算

### ROC（资本回报率）—— 公司质量
```
ROC = fina_indicator.roic  （直接使用 tushare 提供的指标）
```

### EY（盈利收益率）—— 价格便宜程度
```
EY = ebit / total_mv
```
- `ebit` 从 `fina_indicator` 获取
- `total_mv`（总市值）从调仓日的 `daily_basic` 获取

### 综合排名
```
综合排名 = rank(ROC 降序) + rank(EY 降序)
选综合排名最低的前 N 只（通常 30 只）
```

## 财务季度对齐（调仓日 → 最新可用财报）

回测中每个调仓日不能"看到未来"的数据，需按实际披露时间对齐：

| 调仓日 | 可用财报 |
|--------|---------|
| 3月底 | 上年三季报（`上年-09-30`）—— 年报截至4月底才出齐 |
| 6月底 | 一季报（`当年-03-31`）—— 年报+一季报4月底已出 |
| 9月底 | 中报（`当年-06-30`）—— 中报8月底已出 |
| 12月底 | 三季报（`当年-09-30`）—— 三季报10月底已出 |

```python
def get_quarter_for_reb(reb_date):
    y = int(reb_date[:4]); m = int(reb_date[4:6])
    if m <= 3:  return f"{y-1}0930"
    elif m <= 6: return f"{y}0331"
    elif m <= 9: return f"{y}0630"
    else:        return f"{y}0930"
```

## 数据清洗规则

1. **排除金融行业**：industry 包含"银行""保险""证券""多元金融""房地产" → 这些公司 roic/ebit 为 NaN
2. **ROIC > 0**：排除亏损/低效公司
3. **EBIT > 0**：排除亏损公司
4. **总市值 >= 10亿**：排除小盘股，保证流动性

## 回测参数

| 参数 | 值 |
|------|-----|
| 周期 | 5年（2021-07 ~ 2026-06） |
| 调仓频率 | 每季度末 |
| 选股数 | 30只 |
| 持仓方式 | 等权 |
| 基准 | 沪深300（000300.SH） |

## 完整脚本流

参考 `/opt/data/magic_backtest/` 目录下的脚本：

- `step1_fetch_data.py` — 全量数据拉取
- `step1b_retry_failed.py` — 两阶段补拉失败股票
- `step2_run_backtest.py` — 完整回测执行 + 结果输出

## fina_indicator 批量拉取注意

参见 `references/API批量获取能力.md` 的 fina_indicator 章节。

核心要点：
- 不要只用高并发（10线程+短间隔 → 64%失败率）
- 用两阶段法：先并发快拉，再单线程补拉失败的
- 设 `socket.setdefaulttimeout(60)` 防止卡死
- 每200只保存中间结果，支持断线续传

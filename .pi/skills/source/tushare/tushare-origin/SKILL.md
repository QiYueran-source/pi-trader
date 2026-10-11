---
name: tushare
description: 面向中文自然语言的 Tushare 数据研究技能。用于把“看看这只股票最近怎么样”“帮我查财报趋势”“最近哪个板块最强”“北向资金在买什么”“给我导出一份行情数据”这类请求，转成可执行的数据获取、清洗、对比、筛选、导出与简要分析流程。适用于 A 股、指数、ETF/基金、财务、估值、资金流、公告新闻、板块概念与宏观数据等研究场景。
author: tushare.pro
version: 1.1.12
credentials:
  - name: TUSHARE_TOKEN
    description: Tushare Token，用于认证和授权访问Tushare数据服务。
    how_to_get: "https://tushare.pro/register"
requirements:
  python: 3.7+
  packages:
    - name: tushare
  environment_variables:
    - name: TUSHARE_TOKEN
      required: false
      sensitive: true
  network_access: true
---

# tushare

把自然语言财经数据请求，转成可执行的 Tushare 数据工作流。

这是一个面向自然语言的金融数据研究 skill。


## What this skill is for

使用这个 skill 的典型场景：

- 看某只股票、指数、ETF 最近走势
- 查公司基本资料、估值、财务趋势
- 做多标的横向对比
- 看资金流、北向资金、龙虎榜、板块强弱
- 梳理公告、新闻、研报、政策线索
- 查看 CPI / PPI / PMI / 社融 / 利率等宏观数据
- 导出 CSV / parquet 供后续分析或回测使用
- 生成简洁研究摘要，而不是只吐原始字段表

先理解用户要解决什么问题，再去选接口、取数、整理、解释、交付。

***

## When to use

当用户表达以下意图时，优先使用本 skill：

### 行情 / 趋势

- 看下 XX 最近怎么样
- XX 这段时间涨得怎么样
- 今年以来表现如何
- 最近有没有放量
- 这票最近强不强

### 财务 / 估值 / 公司质量

- 看下 XX 财报
- 最近几个季度利润趋势
- 财务质量怎么样
- 现金流好不好
- 现在估值算高吗
- 帮我看 PE / PB / ROE / 毛利率

### 对比 / 排行 / 筛选

- XX 和 YY 谁更强
- 帮我横向比较一下
- 哪些公司利润增长更快
- 帮我筛一下高 ROE 低负债
- 给我排个前十

### 板块 / 指数 / 主题

- 最近哪个板块最强
- 半导体最近怎么样
- 机器人为什么涨
- 指数成分股有哪些
- 哪些主题最热

### 资金流 / 情绪

- 最近资金在买什么
- 北向资金最近流向哪里
- 哪个板块最吸金
- 主力资金流入最多的是谁
- 龙虎榜上有什么看点

### 公告 / 新闻 / 研报 / 政策

- 最近有什么公告
- 帮我梳理下 XX 公告
- 最近有没有什么催化
- 最近新闻面怎么样
- 最近有什么重要政策

### 宏观 / 跨市场

- 最近宏观环境怎么样
- CPI / PMI 最近怎么看
- 当前市场风格偏什么
- 大盘环境偏多还是偏空
- 港股 / 美股 / 美债最近怎么样

### 数据导出 / 研究准备

- 给我导出一份行情数据
- 把近两年日线拉成 CSV
- 生成可回测的数据表
- 拉一个研究表供后续分析

***

## What this skill is NOT for

这个 skill 不适合：

- 直接给买卖建议或替代投资顾问
- 自动下单或执行交易
- 需要毫秒级实时交易决策的场景
- 复杂回测引擎、组合优化系统本身的实现（那是另一个工程）
- 在没有 Tushare 权限/积分支持的情况下强行伪造数据

如果数据权限不够、接口不可用或时间范围不合理，要明确说出限制，不要硬编。

***

## Natural-language trigger guide

即使用户完全不说 `tushare`、`financials`、`macro` 这些术语，只要意图符合以下含义，也应该触发本 skill。

### 常见口语触发

- 看看这个股票最近怎么样
- 给我快速研究一下 XX
- 上次说的那只票现在什么情况
- 帮我看下财报
- 最近哪个板块最强
- 北向最近在买什么
- 有什么催化消息
- 这个公司值不值得重点看
- 给我拉份数据
- 导出成 CSV
- 帮我筛一批票
- 把这几个公司对比一下

### 中文自然语言优先原则

用户说人话时，先理解任务，不要先回到接口名和字段名。
优先把：

- "最近" 解释成合理时间窗
- "财报" 解释成最近 8 个季度 / 最近年度
- "强不强" 解释成走势 + 相对强弱 + 活跃度
- "资金关注" 解释成净流入、活跃成交、龙虎榜/北向等可用口径

如果任务有多个合理解释，再做最小澄清。

***

## Environment check

在真正请求数据之前，先做前置校验：

1. 检查 Python 是否可用， 版本要求 3.7+
2. 检查 `tushare` 包是否已安装
3. 检查 `TUSHARE_TOKEN` 是否存在.
4. 必要时做一次轻量接口冒烟测试（如交易日历 / 基础接口）
5. 如用户请求高权限接口，提前提示可能存在积分/权限限制

> **⚠️ 常见坑：tushare 安装在独立 venv 中**
> 
> 很多环境中 tushare 并不在系统 Python 里，而是在 Hermes 或其他项目的 venv 中（如 `/opt/hermes/.venv/`）。
> 系统 `python3 -c "import tushare"` 可能报 `ModuleNotFoundError`，但 `/opt/hermes/.venv/bin/python3 -c "import tushare"` 正常。
> 
> 验证方式：
> ```bash
> pip show tushare          # 看 Location 字段确认安装路径
> /opt/hermes/.venv/bin/python3 -c "import tushare as ts; print(ts.__version__)"
> ```
> 
> 如果 `pip install tushare` 安装到了 Hermes venv 但系统 python 找不到，使用 `/opt/hermes/.venv/bin/python3` 执行数据查询脚本。
> 也可以检查 `which python3` 和 `pip show tushare | grep Location` 的路径是否一致来确定问题。

若缺失 token，直接提示最短修复路径，例如：

```bash
export TUSHARE_TOKEN=your_token
```

不要等到主查询跑失败了才暴露环境问题。

***

## Intent taxonomy

先识别任务类型，再决定接口组合。

### 1. 行情 / 趋势

典型问题：

- 最近走势怎么样
- 今年涨了多少
- 最近波动大不大
- 最近有没有放量

常用接口：

- `daily`
- `pro_bar`
- `weekly`
- `monthly`
- `stk_mins`
- `rt_k` / `rt_min`（如确需实时口径且权限允许）
- `daily_basic`

#### ⚠️ ETF/基金行情用 `fund_daily`，不是 `daily`

**关键坑位：** ETF（如 588000 科创50ETF、510300 沪深300ETF）的日线行情**不能用** `pro.daily()`，即使带了正确的交易所后缀（`.SH`），也会**静默返回空 DataFrame**，不报错：

```python
# ❌ 错误：ETF 用 daily → 返回 0 行，静默失败
df = pro.daily(ts_code='588000.SH', start_date='20260728', end_date='20260728')
len(df)  # → 0

# ✅ 正确：ETF 用 fund_daily → 正常返回 OHLCV
df = pro.fund_daily(ts_code='588000.SH', start_date='20260728', end_date='20260728')
len(df)  # → 1
```

`fund_daily` 返回的字段与 `daily` 类似 — `ts_code, trade_date, pre_close, open, high, low, close, change, pct_chg, vol, amount`。

**适用对象：** 所有在交易所上市的 ETF（588000.SH、510300.SH、511990.SH、518880.SH 等）。LOF 基金也可能走 `fund_daily` 而非 `daily`。不确定时先跑 `fund_daily` 试探，如果返回空再回退到 `daily`。

**⚠️ `fund_daily` 的 ts_code 同样必须带交易所后缀：** 与 `daily` 一样，裸代码（如 `588000`）会**静默返回空 DataFrame**，不报错。盘后回放验证、定时任务里尤其容易踩——很多 cron prompt 示例代码写的是裸 `{标的代码}`：

```python
# ❌ 裸代码 → 空 DataFrame，静默失败（不报错，容易误判"无数据"）
df = pro.fund_daily(ts_code='588000', start_date='20260728', end_date='20260731')
len(df)  # → 0

# ✅ 带后缀 → 正常返回 OHLCV
df = pro.fund_daily(ts_code='588000.SH', start_date='20260728', end_date='20260731')
len(df)  # → 4
```

规则同 `daily`：`588000.SH`（科创板/沪市）、`510300.SH`、`159915.SZ`（深市 ETF 用 `.SZ`）。每次调用后检查 `len(df) > 0`。

#### ⚠️ 可转债行情用 `cb_daily`，支持按 trade_date 全市场拉取（2026-08-09 实测）

可转债（代码如 `128044.SZ`、`110092.SH`）日线行情**不能用** `pro.daily()`（那是股票接口），要用 `cb_daily`：

```python
# ✅ 按单日拉全市场所有转债（约 300-560 只/天）
df = pro.cb_daily(trade_date='20260807', fields='ts_code,trade_date,close,pre_close,change,pct_chg,vol,amount')
len(df)  # → ~310（随年份不同：2019 约124只，2021 约348，2024 约559）

# ✅ 也可以按 ts_code 拉单只转债区间（带 .SH/.SZ 后缀）
df = pro.cb_daily(ts_code='128044.SZ', start_date='20240101', end_date='20240801')
```

**关键点：**
- **按 `trade_date` 全市场拉取是全量模式**，不需要 ts_code、不需要后缀——和 `daily(trade_date=X)` 股票接口同款用法
- 历史覆盖 **2019 至今**，全市场约 1000 只转债（2019-2026 累积 977 只）
- 回测批量拉取模式：遍历 `trade_cal` 交易日 × 每天一次 `cb_daily(trade_date=d)`，`time.sleep(0.12)` 节流，~1859 个交易日约 5 分钟拉完 72 万行
- 退市转债会从"当前列表"消失，但历史交易日数据仍在——回测用 pivot 后列数变化即可覆盖存续期



用 `fund_daily` 计算 ETF **流动性/成交额**时，不能把 `amount` 当元直接除以 1e8：

```python
# ❌ 错误：把 amount 当元 → 得出日均 0.06亿，实际该 ETF 日均 62亿
avg_yi = df['amount'].mean() / 1e8   # 科创芯片ETF 588200 得出 0.06

# ✅ 正确：amount 单位是千元，1亿 = 100,000千元
avg_yi = df['amount'].mean() / 100000   # 588200 得出 ~62.4
```

- `amount`：**千元**（不是元），`amount / 100000` 才是亿元
- `vol`：**手**（1手=100份），`vol × 100 × close / 1e8` 才是亿元（交叉验证口径）
- 验证方法：`amount_raw / 1000` ≈ `vol × close`（即 千元×1000 ≈ 手×100×价格，二者应近似相等）；`amount` 与 `vol×close` 比值恒为 ~10 是单位搞错的标志
- 用 `amount/100000` 拉日均成交额做 ETF 流动性排序，是挑选"同板块最优 ETF"（流动性+费率）的第一步，完整方法见 `references/ETF流动性对比.md`

### 2. 基本资料 / 标的识别

典型问题：

- 这是什么公司 / 什么指数 / 什么基金
- 是创业板吗 / 是 ST 吗 / 什么时候上市

常用接口：

- `stock_basic`
- `fund_basic`
- `index_basic`
- `stock_company`
- `stock_st` / `st`

### 3. 财务 / 公司质量

典型问题：

- 最近几个季度利润趋势
- 最近几个季度营收和净利润趋势
- 财务质量怎么样
- ROE / 毛利率 / 现金流如何

常用接口：

- `income`（营收 / 净利润趋势优先）
- `fina_indicator`（ROE / 毛利率 / 净利率等质量指标补充）
- `balancesheet`
- `cashflow`
- `forecast`
- `express`
- `disclosure_date`

### 4. 估值 / 基本面指标

典型问题：

- 现在估值高不高
- 谁更便宜
- PE / PB / 股息率如何

常用接口：

- `daily_basic`
- `fina_indicator`

### 5. 资金流 / 市场行为

典型问题：

- 北向最近买什么
- 主力资金流向
- 龙虎榜情况

常用接口：

- `moneyflow`
- `moneyflow_hsgt`
- `hsgt_top10`
- `top_list`
- `top_inst`
- `moneyflow_ind_dc`
- `moneyflow_mkt_dc`

### 6. 板块 / 指数 / 主题

典型问题：

- 最近哪个板块最强
- 行业轮动如何
- 某板块有哪些成分股

常用接口：

- `index_basic`
- `index_daily`
- `index_classify`
- `index_member_all`
- `sw_daily`
- `ths_index`
- `ths_member`
- `dc_index`
- `dc_member`

### 7. 打板 / 情绪 / 活跃度

典型问题：

- 今天涨停梯队
- 连板结构
- 炸板率 / 情绪强弱

常用接口：

- `limit_list_d`
- `limit_step`
- `kpl_list`
- `dc_hot`
- `ths_hot`

### 8. 公告 / 新闻 / 研报 / 政策

典型问题：

- 最近有什么公告或催化
- 最近有什么研究报告
- 最近政策面发生了什么

常用接口：

- `anns_d`
- `news`
- `major_news`
- `research_report`
- `npr`
- `irm_qa_sh`
- `irm_qa_sz`

### 9. 宏观 / 跨市场

典型问题：

- CPI / PMI / 社融 / M2
- 利率与收益率曲线
- 港股 / 美股 / 美债数据

常用接口：

- `cn_cpi`
- `cn_ppi`
- `cn_pmi`
- `cn_gdp`
- `cn_m`
- `sf_month`
- `shibor`
- `shibor_lpr`
- `us_tycr`
- `us_daily`
- `hk_daily`
- `index_global`

### 10. 导出 / 研究准备

典型问题：

- 导出某标的一段时间行情
- 生成回测用数据表
- 输出 CSV / parquet

常用接口：

- 取决于上游任务，核心是统一输出规则与命名规范

***

## Entity resolution rules

### 标的解析

- 优先识别股票名、股票代码、指数名、ETF 名、基金名
- 对中文简称先尝试匹配标准对象
- 若重名或多解，列出候选并做最小澄清
- 证券代码内部统一为标准格式，如：`600519.SH`、`000001.SZ`

### 市场识别

- 默认先按 A 股理解，除非用户明确提到港股 / 美股 / 基金 / 债券 / 期货
- 指数、ETF、个股要分开判断，不要混用接口

### 时间默认值

若用户没有明确给时间范围，使用合理默认：

- "最近走势" → 默认近 20 个交易日
- "这段时间 / 最近一段时间" → 默认近 3 个月
- "财报 / 业绩" → 默认最近 8 个季度 + 最近年度
- "资金流最近如何" → 默认近 5～20 个交易日，按任务粒度调整
- "宏观最近如何" → 默认看最近 6～12 期

### 板块口径默认值

若用户只说"板块 / 行业 / 概念"但未指定分类体系：

- 行业优先用申万 / 中信等较稳定口径
- 概念优先同花顺 / 东方财富等主题口径
- 若结论依赖具体口径差异，要明确说明使用了哪种分类

***

## Input normalization rules

在请求数据前先做规范化：

- 日期统一为 `YYYYMMDD`
- 检查 `start_date <= end_date`
- 用户输入未来日期时，自动裁剪到最近可用日期并提示
- 裸代码如 `000001` 不要盲猜，能补全则说明补全规则，不能补全则澄清
- 对冲突参数（如 `trade_date` 与 `start_date/end_date` 同时给）要先裁决，不要直接乱传

***

## Data retrieval rules

### 文档先行

在写请求代码前，先确认：

- 接口名是否正确
- 必填参数
- 可选参数
- 返回字段
- 积分 / 频率限制

不要仅凭记忆硬写字段名。

### 字段确认

对 `fields` 参数，优先使用已知字段白名单或接口文档确认。
若用户要求字段不存在，应明确说明，而不是盲查。

### 默认分段拉取

长区间数据不要一次性全拉。
建议：

- 日线 / 周线 / 月线：按年或季度切片
- 财报：按年份 / 报告期切片
- 分钟数据：按月 / 周切片
- 大批量多标的：按标的分批 + 日期分段

### 重试与限流

- 仅对瞬时错误（网络抖动、超时、429）进行有限重试
- 参数错误、权限不足、字段错误不要盲重试
- 批量拉取时加入节流，避免高频撞限

### 已知接口速率限制（基础用户）

| 接口 | 限制 | 说明 |
|------|------|------|
| `limit_list_d` | **1次/分钟** | 非常严格的频率限制，批量扫多天数据不可行 |
| `stk_mins` | **1次/分钟（低积分实测直接 1次/小时，2026-08-15）** | 分钟数据接口。基础积分下实测**第一次调用后即限频 1次/小时**（不是文档说的 1次/分钟），22只×2月分钟数据批量拉取需 40+ 小时不可行。1min 全量历史需代理接口（见下） |
| `daily` | **500次/分钟** | 可批量调用，是涨停筛选的首选替代方案 |
| `stock_basic` | 较高 | 支持批量查 5000+ 条数据 |

**⚠️ 分钟数据（1min/5min）批量拉取的替代源（2026-08-15 实测）：**

| 源 | 频率 | 限制 | 备注 |
|----|------|------|------|
| baostock `query_history_k_data_plus` | 5/15/30/60min | 无限频 | 免费登录即用，**不支持 1min**；字段 date/time/.../volume（非 trade_time/vol） |
| akshare `stock_zh_a_minute`(新浪) | 1min | 无限频 | **仅最近~9天**，历史深度不够做统计 |
| **promax 代理**（`https://pcd.mobcvb.cn/tushare/pro`） | 1min 全量 | 4.2s/次 | 返回 tushare 同构（`{"code":0,"data":{"fields":[...],"items":[...]}}`），已封装为 **tushare-proxy 技能**（`/opt/data/skills/data/tushare-proxy/`）：`ts_proxy.py` 提供 `ts/rds/get/fetch_1min`，key 在技能自带 `.env`（load_dotenv 绝对路径，不进项目 env、不进 git）；1min 批量拉取用 `fetch_1min(ts_code, trade_dates, freq='1min', resume_file=...)`；调用：`requests.get(f"{U}/{api}", params=..., headers={"X-API-Key": K}, verify=False)` |

### ⚠️ `pro.daily()` 的 ts_code 必须带交易所后缀（关键坑位）

`pro.daily()` 的 `ts_code` 参数必须包含交易所后缀（`.SH` / `.SZ` / `.BJ`），**裸代码会静默返回空结果**，不报错：

```python
# ❌ 错误：裸代码 → 返回 0 行，不报错，静默失败
df = pro.daily(ts_code='600192', start_date='20260701', end_date='20260724')
len(df)  # → 0

# ✅ 正确：带交易所后缀 → 正常返回
df = pro.daily(ts_code='600192.SH', start_date='20260701', end_date='20260724')
len(df)  # → 18

# ✅ 批量查询也带后缀
df = pro.daily(ts_code='600192.SH,000037.SZ,002606.SZ', ...)
```

**后缀规则：**

| 代码范围 | 后缀 | 示例 |
|----------|------|------|
| 600xxx/601xxx/603xxx/605xxx | `.SH` | `600519.SH` |
| 000xxx/001xxx/002xxx/003xxx | `.SZ` | `000001.SZ` |
| 300xxx（创业板） | `.SZ` | `300750.SZ` |
| 688xxx（科创板） | `.SH` | `688981.SH` |
| 920xxx（北交所） | `.BJ` | `920002.BJ` |
| 30xxxx（部分新三板/北交所） | `.BJ` | 按实际 |

**指数（index）后缀按交易所，不套用股票代码段规则：** `index_daily(ts_code=...)` 同样必须带后缀。经典陷阱是 000688——科创50 指数是 `000688.SH`（上交所指数），按股票代码段规则会误判成 `.SZ`（且存在股票 000688.SZ 国城矿业）；8/10 复盘实测 `index_daily(ts_code='000688.SH')` 正常返回。不确定时 `.SH`/`.SZ` 各试一次并检查 `len(df) > 0`。

**为什么这很重要：** 裸代码返回 0 行是一个**静默失败**——tushare 不抛异常，只返回空 DataFrame。如果你不检查 `len(df)`，会以为数据不存在然后跳过处理，导致遗漏关键分析。

**检查方法：** 每次调用 `pro.daily(ts_code=...)` 后，确认 `len(df) > 0`。批量场景下尤其注意——如果一批代码中混有裸代码，该只股票的数据会静默缺失。

> 注意：`pro.daily(trade_date=X)` 不传 `ts_code` 时返回全市场数据，不受此限制影响（全市场模式不需要后缀）。

**分钟数据使用技巧：** `stk_mins`（1次/分钟）用于拉取盘后分钟线，持仓股数少时够用。每只股票拉开盘半小时5分钟线（共6根K线），串行调用即可。超频后会被惩罚到1次/小时——如果在几分钟内连续调用多次触发该限制，等待约1小时后自动恢复。

**关键技巧：** `daily(trade_date=X)` 不加 `ts_code` 参数时，返回**该日期全市场所有股票**的日线数据。利用这个特性可以替代 `limit_list_d` 做涨停筛选：

```python
df = pro.daily(trade_date="20260615")           # 全市场一网打尽
up_stocks = df[df["pct_chg"] >= 9.5]             # 涨停常用阈值
```

通过 `stock_basic` 补充名称和行业信息：

```python
df = pro.stock_basic(ts_code=",".join(codes), fields="ts_code,name,industry")
```

**批量拉取避限策略：** 对 `daily` 接口每只股票查日线时，`time.sleep(0.15)` 可将速率控制在 ~400次/分钟，留有余量。

### 财报接口的重要限制

`income`、`balancesheet`、`fina_indicator` **必须传 `ts_code`**，不支持按 `period` 拉全市场。即使 2000+ 积分也一样。

#### fina_indicator 全市场批量拉取 ⚠️ 并发陷阱

全市场5000+只股票逐只拉取 fina_indicator 时，**高并发 + 短间隔会导致大量请求超时**。实测数据：

| 策略 | 成功率 | 耗时 |
|------|--------|------|
| `ThreadPoolExecutor(max_workers=10)` + sleep(0.12s) | ~36%（2000/5526） | 较快但不可靠 |
| **先10线程快拉一批，失败的单线程补拉（两阶段法）** | **~99%** | 并发5分钟+补拉15分钟 |
| 纯单线程 + sleep(0.25s) + socket.setdefaulttimeout(60) | ~95%+ | ~25分钟 |

**推荐方案（两阶段法）：**

```python
import socket
socket.setdefaulttimeout(60)  # 全局超时保护，防止网络请求卡死

# 阶段1：ThreadPoolExecutor(max_workers=10) + sleep(0.12s) 快速拉第一轮
# 阶段2：记录所有失败股票，单线程 sleep(0.25s) 补拉
# 每200只保存一次中间结果，支持断线续传
```

**金融股特殊处理：** `fina_indicator` 对银行/保险/证券等金融行业的返回中，`roic`、`ebit`、`invest_capital`、`networking_capital` 字段全部为 `NaN`。这是正常的——ROIC 不适用于金融行业。在需要这些字段的筛选任务中，必须排除金融行业（industry 中包含"银行""保险""证券""多元金融""房地产"的股票）。

`daily_basic(trade_date=X)` 不传 `ts_code` 可拉全市场——这是少数支持批量模式的财务相关接口。

各接口的批量能力对比详见 `references/API批量获取能力.md`。

### 分段合并

分段拉取后：

- 合并
- 去重
- 按主键排序
- 记录失败分段
- 若部分成功，要明确告诉用户哪些段失败了

***

## Output contract

除非用户明确只要原始表，否则优先按这个结构输出：

1. **一句话结论**
2. **数据范围与口径**
3. **关键指标 / 关键表格**
4. **异常点 / 风险点 / 解释限制**
5. **如有本地输出，给出文件路径**

### 结果交付形态

按任务复杂度选择：

- 小结果：Markdown 摘要 + 简短表格
- 中等数据表：CSV
- 大规模 / 后续分析：Parquet
- 需要可复用流程：附 Python 脚本
- 需要可视化时：输出图表 PNG 或说明可绘制图表

### 元信息

生成数据文件时，尽量同时记录：

- 接口名
- 请求参数
- 拉取时间
- 数据行数
- 字段列表
- 是否存在失败分段 / 缺失

***

## Workflow templates

下面这些模板，是本 skill 的核心。
不要直接从接口想起，而要从任务模板想起。

### 1. 单标的行情分析

适用：

- 看下 XX 最近怎么样
- 这票最近强不强
- 今年以来表现如何

默认流程：

1. 解析标的
2. 确定时间范围
3. 取行情 + 必要基础指标
4. 总结区间涨跌、成交活跃度、高低点、波动
5. 输出一句结论 + 关键数字

### 2. 多标的横向对比

适用：

- XX 和 YY 谁更强
- 把这几家公司对比一下

默认流程：

1. 锁定对象
2. 统一时间口径
3. 选 3～5 个关键指标
4. 输出对比表
5. 给出"谁在哪方面更强"的总结

### 3. 财务质量快照

适用：

- 看下 XX 财报
- 最近几个季度利润趋势
- 财务质量怎么样

默认流程：

1. 拉最近 8 个季度 + 最近年度财务核心数据
2. 区分营收、利润、毛利率、ROE、现金流
3. 标出改善 / 恶化 / 波动点
4. 说明累计值、单季值、同比口径

### 4. 估值分析 / 筛选

适用：

- 现在估值高不高
- 谁更便宜
- 筛低估值高股息

默认流程：

1. 明确标的池
2. 拉 `daily_basic` 等估值指标
3. 必要时联动财务质量
4. 输出排序、极值、口径说明

### 5. 资金流追踪

适用：

- 最近资金在买什么
- 北向最近流向哪里
- 主力资金流入最多的是谁

默认流程：

1. 明确资金口径（北向 / 主力 / 龙虎榜 / 板块资金）
2. 确定时间窗
3. 拉净流入 / 活跃成交 / 持续性
4. 和价格表现联动解释
5. 避免把单日噪声说成趋势

### 6. 板块 / 题材轮动分析

适用：

- 最近哪个板块最强
- 机器人最近强在哪
- 某概念板块里有哪些成分股

默认流程：

1. 确定分类口径
2. 拉板块区间表现
3. 必要时联动成分股、资金流、涨停梯队
4. 输出强势板块排行与代表标的

### 7. 公告 / 新闻 / 事件梳理

适用：

- 最近有什么公告
- 有没有什么催化
- 最近新闻面怎么样

默认流程：

1. 明确对象和时间窗
2. 拉公告 / 新闻 / 研报 / 政策数据
3. 去噪，提炼 3～5 条主线
4. 区分事实、公告、媒体解读
5. 必要时结合股价异动做弱因果解释

### 8. 数据导出与研究准备

适用：

- 拉一份 CSV
- 做回测数据表
- 导出某段时间的行情/财务数据

默认流程：

1. 明确数据范围、频率、字段
2. 采用分段策略取数
3. 清洗、去重、统一字段类型
4. 输出 CSV / parquet
5. 给出文件路径和元信息

### 9. 综合研究简报

适用：

- 给我快速研究一下 XX
- 做个投资者视角简报
- 先给个全景判断

默认流程：

1. 一句话结论
2. 行情表现
3. 财务趋势
4. 估值水平
5. 资金流情况
6. 公告 / 新闻催化
7. 风险点
8. 值得继续深挖的问题

***

## Data quality rules

拉取完成后，至少做这些检查：

- schema 校验
- 关键字段存在性检查
- 主键去重
- 固定排序
- 日期标准化
- 数值字段类型规范化

### 空结果处理

空表不一定是失败，要区分：

- 非交易日
- 区间无数据
- 股票未上市
- 参数错误
- 接口权限不足

不要把所有空结果都说成"接口坏了"。

***

## Cache and reuse rules

为了让 skill 可长期复用，应优先支持：

- 基础表缓存（如 `stock_basic`、交易日历、指数基础信息）
- 增量更新，而不是每次全量重拉
- 大任务断点续跑
- 结果文件规范命名

推荐命名格式：

- `daily_600519.SH_20230101_20231231_20260322.csv`
- `fina_indicator_300750.SZ_20260322.parquet`

缓存命中时，最好说明哪些来自缓存，哪些是新拉取的数据。

***

## Error handling

优先用"人话 + 调试细节分层"的方式输出错误。

### 用户可见层

- token 未配置
- 当前接口可能需要更高积分/权限
- 时间范围过大，已自动改为分段拉取
- 股票名称不唯一，请确认是哪一个
- 当前结果为空，可能因为该日期非交易日 / 标的未上市 / 无权限

### 调试层

必要时补：

- 接口名
- 参数
- 失败分段
- 异常原文

### 部分成功原则

如果部分分段失败，不要说"成功完成"。
应明确说：

- 哪些部分成功
- 哪些部分失败
- 是否已生成不完整结果

***

## Recommended minimal interface set

主 skill 正文不要塞几百个接口。
优先记住 80% 常用任务的核心接口集：

- `stock_basic`
- `trade_cal`
- `daily`
- `pro_bar`
- `daily_basic`
- `fina_indicator`
- `income`
- `balancesheet`
- `cashflow`
- `forecast`
- `express`
- `moneyflow`
- `moneyflow_hsgt`
- `hsgt_top10`
- `top_list`
- `index_basic`
- `index_daily`
- `index_classify`
- `sw_daily`
- `ths_index`
- `ths_member`
- `limit_list_d`
- `limit_step`
- `news`
- `major_news`
- `research_report`
- `anns_d`
- `cn_cpi`
- `cn_pmi`
- `us_tycr`
- `fund_daily`  # ⚠️ ETF/基金日线行情：ETF 用 fund_daily 替代 daily，silent empty 陷阱
- `cb_daily`    # ⚠️ 可转债日线：按 trade_date 拉全市场（2019 起可用，返回 ts_code 带 .SH/.SZ 后缀），回测转债策略用此接口

全部数据接口，请参考 `references/数据接口.md`。
全市场涨停筛选与候选股生成模式，请参考 `references/全市场涨停筛选.md`。
概念板块/行业成分股查询（ths_index 无权限时的申万替代路径 + 腾讯盘中实时行情接口），请参考 `references/概念板块成分股查询.md`。
基于候选池的买入信号检测（MA5 突破 + 放量确认模式），请参考 `references/买入信号检测.md`。
板块/概念成分股查询（无 ths_index 权限时用 index_member_all 分页快照 + l3_name 过滤，含申万「计算机/AI应用」三块成分股清单），请参考 `references/板块成分股查询.md`。
板块/概念成分股查询（index_member_all 全市场快照按申万三级过滤）与盘中实时行情（tushare 无当日数据时用腾讯接口），请参考 `references/板块成分股查询.md`。
各接口批量能力速查（哪些支持全市场拉取、哪些必须逐股票），请参考 `references/API批量获取能力.md`。
季度调仓回测的日期对齐模式（用 `trade_cal` 代替硬编码 + 手动修正），请参考 `references/季度调仓日期对齐.md`。
全市场 Magic Formula 回测的完整数据流水线（财务季度对齐、fina_indicator 批量拉取方案、清洗规则），请参考 `references/MagicFormula回测数据流水线.md`。
个股结合近期市场分析做操作研判的标准流程（Tushare数据 + 财经分析笔记交叉研判），请参考 `references/个股结合市场分析研判.md`。

***

## Best practices

- 先理解任务，再选接口
- 能少取就少取，先核心数据，再扩展
- 先给结论，再给证据
- 默认说人话，不堆字段名
- 对"最近 / 财报 / 强不强 / 资金关注"这类模糊中文表达，要有合理默认口径
- 大任务先给执行计划，再开跑
- 导出任务尽量保留脚本、元信息、文件路径，方便复用

***

## Examples

### 单票行情

- 看下宁德时代最近三个月走势
- 茅台今年以来涨了多少
- 招行这两年最大回撤大概多少

### 财务 / 估值

- 看下比亚迪最近 8 个季度营收和净利润趋势
- 茅台现在估值算高吗
- 帮我找高 ROE 低负债的公司

### 对比

- 比一下茅台、五粮液、泸州老窖近一年的涨幅和估值
- 对比一下沪深300、中证500、创业板今年表现

### 资金流 / 板块

- 今天北向资金流入最多的股票有哪些
- 最近哪个板块最强
- 半导体板块最近一个月强不强

### 公告 / 事件

- 帮我梳理下寒武纪最近的重要公告
- 最近机器人板块有什么消息面催化

### 宏观

- 看一下最近 CPI、PPI、PMI 变化
- 当前市场风格偏成长还是价值

### 导出

- 把沪深300成分股近两年日线导成 CSV
- 下载宁德时代 2020 到现在的复权行情
- 把最近 3 年 ROE、PE、PB、营收增速拉成一个表

***

## Quick rule

当用户在说：

- 看走势
- 查财报
- 比较公司
- 看板块
- 看资金流
- 梳理公告新闻
- 看宏观
- 拉数据导出

就不要先想"有哪些接口"。
先想：
**这是什么任务？默认该走哪条数据工作流？结果应该怎样交付才真正有用？**

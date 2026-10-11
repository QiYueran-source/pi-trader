---
name: tushare-proxy
description: 第三方 tushare 代理通道统一封装（promax + RDS）。用于绕过官方限频批量拉取分钟级数据（stk_mins 1min）、需要快速/高并发拉取 tushare 同构数据的场景。与官方 tushare 技能互补：官方接口拉不动时用本技能。
author: workbuddy
version: 1.0.0
credentials:
  - name: TUSHARE_PROMAX_URL
    description: promax 代理基础地址
  - name: TUSHARE_PROMAX_KEY
    description: promax 代理 API Key
  - name: TUSHARE_RDS_URL
    description: RDS (datahubco) 代理基础地址
  - name: TUSHARE_RDS_KEY
    description: RDS (datahubco) API Key
requirements:
  python: 3.7+
  packages:
    - name: requests
    - name: python-dotenv
    - name: pandas
  environment_variables:
    - name: TUSHARE_PROMAX_URL
      required: false
      sensitive: true
    - name: TUSHARE_PROMAX_KEY
      required: false
      sensitive: true
    - name: TUSHARE_RDS_URL
      required: false
      sensitive: true
    - name: TUSHARE_RDS_KEY
      required: false
      sensitive: true
  network_access: true
---

# tushare-proxy

第三方 tushare 代理通道统一封装：**promax**（全接口聚合，支持 1min 分钟线）+ **RDS**（datahubco，速度快）。

> 本质：这两个都不是独立数据源，是 tushare 官方接口的第三方中转代理（卖家高权限账号对外转调）。返回结构与官方完全同构 `{code:0, data:{fields, items}}`。

## 什么时候用

- **官方 tushare 限频卡死**（`stk_mins` 官方 1次/小时，批量拉 1min 要 40+ 小时）→ 用 promax 拉 1min，实测 4.2s/次
- 需要快速/高并发拉取 tushare 同构数据（RDS 速度快）
- 回测数据准备：批量拉分钟线、全市场拉取

## 快速开始

```python
import sys
sys.path.insert(0, "/opt/data/skills/data/tushare-proxy/scripts")
from ts_proxy import ts, rds, get, fetch_1min

# 1. promax 通道（全 tushare pro 接口）
df = get("daily", ts_code="000001.SZ", start_date="20260701", end_date="20260814")
# df 是 pandas DataFrame

# 2. 指定通道
df = get("fund_daily", ts_code="515180.SH", start_date="20260701", channel="promax")

# 3. 1min 分钟线批量拉取（回测核心）
dates = ["20260803", "20260804", "20260805"]
df1 = fetch_1min("000533.SZ", dates, freq="1min", sleep=0.5, resume_file="/tmp/progress.txt")
```

## API

| 函数 | 说明 |
|:---|:---|
| `ts(a, **p)` | promax 通道，返回原始 dict `{code, data:{fields, items}}` |
| `rds(a, **p)` | RDS 通道，返回原始 dict |
| `get(a, channel="auto", retries=2, **p)` | 统一入口，**返回 DataFrame**；auto=promax 优先失败切 RDS |
| `get_dict(a, **p)` | 返回 list[dict] |
| `fetch_1min(ts_code, trade_dates, freq="1min", sleep=0.5, resume_file=None)` | 按交易日批量拉分钟线，支持断点续传 |

## 坑位（重要）

1. **promax 必须 `verify=False`**——证书校验会失败；脚本已内置 + 抑制警告
2. **RDS 必须设置 `NO_PROXY='*'`**——否则走代理请求失败；脚本已 `os.environ.setdefault("NO_PROXY", "*")`
3. **ts_code 必须带交易所后缀**（`.SH`/`.SZ`）——与官方一致，裸代码静默返回空
4. **ETF/基金用 `fund_daily`，不是 `daily`**——官方规则同样适用，`daily` 对 ETF 静默返回空
5. **key 在 `/opt/data/skills/data/tushare-proxy/.env`**——脚本自动 load_dotenv，不依赖调用方 cwd；不在项目 env、不进 git
6. **代理通道非官方**——可靠性依赖卖家，出问题无官方支持；仅用于拉数据，**绝不用于交易提交**
7. **load_dotenv 默认不覆盖**进程已有同名环境变量（override=False）

## 与官方 tushare 技能的取舍

| 场景 | 用哪个 |
|:---|:---|
| 少量日线/财报/宏观 | 官方 `tushare` 技能（稳定、文档全） |
| 1min 分钟线批量 | **本技能 promax**（官方限频不可行） |
| 全市场高频拉取、被官方限频 | **本技能**（RDS 快 / promax 绕限频） |
| 可转债、涨停筛选等官方特色接口 | 官方（若代理也支持则均可） |

---
name: tushare-cli
description: 通过命令行查询 Tushare 股票、基金和市场数据。适用于用户明确要求按证券代码、日期范围或市场分类取数，并以表格、JSON 或 CSV 输出；接口知识、字段解释和研究流程仍路由到 tushare 技能。
---

# Tushare CLI

本技能是可执行数据入口，不替代 `tushare` 知识技能。

## 路由规则

根据请求选择脚本，并按需读取对应参考文档：

| 用户意图 | 脚本 | 参考文档 |
|---|---|---|
| 股票列表、日线、财务指标 | `scripts/stock_cli.py` | `references/stock-cli.md` |
| 基金列表、ETF 日线、净值、基金经理 | `scripts/fund_cli.py` | `references/fund-cli.md` |
| 行业分类、行业成分、概念板块列表、北向资金 | `scripts/market_cli.py` | `references/market-cli.md` |

如果用户询问 Tushare 接口含义、积分要求、字段定义或研究方法，使用 `tushare` 技能，不要猜测接口字段。

## 执行约定

1. 脚本从本技能根目录 `.env` 读取 `TUSHARE_TOKEN`，不读取其他技能的密钥文件。
2. 日期参数接受 `YYYYMMDD` 或 `YYYY-MM-DD`，传给 Tushare 前统一转换为 `YYYYMMDD`。
3. 股票代码使用完整 Tushare 代码，例如 `000001.SZ`；ETF 使用 `588000.SH`；场外基金通常使用 `.OF` 后缀。
4. ETF 行情必须调用 `fund_cli.py daily`，不能调用股票日线接口。
5. 默认输出表格；自动化消费优先使用 `--format json`，落盘优先使用 `--format csv --output <path>`。
6. 查询失败时保留脚本的非零退出状态，不把错误伪装成空结果。

## 快速路由示例

股票日线：

```bash
python scripts/stock_cli.py daily --code 000001.SZ --start-date 2025-01-01 --end-date 2025-03-01
```

ETF 日线：

```bash
python scripts/fund_cli.py daily --code 588000.SH --start-date 2025-01-01 --end-date 2025-03-01
```

北向资金：

```bash
python scripts/market_cli.py northbound --start-date 2025-01-01 --end-date 2025-03-01
```

执行具体任务前读取对应 `references/*.md`，确认命令参数和数据语义。
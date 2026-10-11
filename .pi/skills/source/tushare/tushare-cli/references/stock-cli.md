# 股票 CLI

脚本：`scripts/stock_cli.py`

## 通用输出参数

所有命令支持：

- `--format table|json|csv`：输出格式，默认 `table`。
- `--output PATH`：写入文件；省略时输出到标准输出。
- `--limit INTEGER`：只保留返回结果的前 N 行。
- `--fields TEXT`：逗号分隔的 Tushare 字段列表；省略时使用接口默认字段。

## `list`：股票基础列表

```bash
python scripts/stock_cli.py list [OPTIONS]
```

参数：

- `--exchange TEXT`：交易所代码，常用 `SSE`、`SZSE`、`BSE`；默认全部。
- `--list-status L|D|P`：上市、退市或暂停上市，默认 `L`。

示例：

```bash
python scripts/stock_cli.py list --exchange SZSE --list-status L --limit 20
```

```bash
python scripts/stock_cli.py list --fields ts_code,name,industry,list_date --format csv --output /tmp/stocks.csv
```

## `daily`：股票日线行情

```bash
python scripts/stock_cli.py daily --code CODE [OPTIONS]
```

参数：

- `--code, -c TEXT`：完整股票代码，必填，例如 `000001.SZ`。
- `--start-date DATE`：开始日期；默认今天之前 30 个自然日。
- `--end-date DATE`：结束日期；默认今天。

示例：

```bash
python scripts/stock_cli.py daily --code 000001.SZ --start-date 2025-01-01 --end-date 2025-03-01
```

```bash
python scripts/stock_cli.py daily -c 600000.SH --fields trade_date,open,high,low,close,vol --format json
```

注意：ETF 日线必须使用 `fund_cli.py daily`。

## `financial`：财务指标

```bash
python scripts/stock_cli.py financial --code CODE [OPTIONS]
```

参数：

- `--code, -c TEXT`：完整股票代码，必填。
- `--period DATE`：报告期，例如 `20241231`；省略时由接口返回可用记录。

示例：

```bash
python scripts/stock_cli.py financial --code 000001.SZ --period 20241231 --fields ts_code,end_date,roe,roa
```
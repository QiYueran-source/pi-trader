# 市场 CLI

脚本：`scripts/market_cli.py`

## 通用输出参数

所有命令支持 `--format table|json|csv`、`--output PATH`、`--limit INTEGER` 和 `--fields TEXT`。

## `sectors`：申万行业分类

```bash
python scripts/market_cli.py sectors [OPTIONS]
```

参数：

- `--level L1|L2|L3`：行业层级，默认 `L1`。
- `--source SW2021`：分类来源，默认 `SW2021`。

示例：

```bash
python scripts/market_cli.py sectors --level L1
```

## `sector-members`：行业指数成分

```bash
python scripts/market_cli.py sector-members --code INDEX_CODE [OPTIONS]
```

示例：

```bash
python scripts/market_cli.py sector-members --code 801010.SI --format csv --output /tmp/sector-members.csv
```

## `concepts`：概念板块列表

```bash
python scripts/market_cli.py concepts --trade-date DATE [OPTIONS]
```

参数：

- `--trade-date DATE`：交易日期，必填，支持 `YYYYMMDD` 或 `YYYY-MM-DD`。

示例：

```bash
python scripts/market_cli.py concepts --trade-date 2025-01-10 --limit 30
```

## `northbound`：沪深港通资金流向

```bash
python scripts/market_cli.py northbound [OPTIONS]
```

参数：

- `--start-date DATE`：开始日期，默认今天之前 30 个自然日。
- `--end-date DATE`：结束日期，默认今天。

示例：

```bash
python scripts/market_cli.py northbound --start-date 2025-01-01 --end-date 2025-03-01
```
# 基金 CLI

脚本：`scripts/fund_cli.py`

## 通用输出参数

所有命令支持 `--format table|json|csv`、`--output PATH`、`--limit INTEGER` 和 `--fields TEXT`。

## `list`：基金基础列表

```bash
python scripts/fund_cli.py list [OPTIONS]
```

参数：

- `--market E|O`：`E` 表示场内基金，`O` 表示场外基金，默认 `E`。
- `--status L|D|I`：基金状态，默认 `L`。

示例：

```bash
python scripts/fund_cli.py list --market E --status L --limit 20
```

## `daily`：ETF/场内基金日线行情

```bash
python scripts/fund_cli.py daily --code CODE [OPTIONS]
```

参数：

- `--code, -c TEXT`：完整基金代码，必填，例如 `588000.SH`。
- `--start-date DATE`：开始日期，默认今天之前 30 个自然日。
- `--end-date DATE`：结束日期，默认今天。

示例：

```bash
python scripts/fund_cli.py daily --code 588000.SH --start-date 2025-01-01 --end-date 2025-03-01
```

ETF 不应使用 `stock_cli.py daily`，否则可能得到空数据。

## `nav`：基金净值

```bash
python scripts/fund_cli.py nav --code CODE [OPTIONS]
```

参数与 `daily` 相同，适用于支持净值接口的基金。

```bash
python scripts/fund_cli.py nav --code 110011.OF --start-date 2025-01-01 --end-date 2025-03-01 --format json
```

## `manager`：基金经理记录

```bash
python scripts/fund_cli.py manager [OPTIONS]
```

可选参数：

- `--code, -c TEXT`：按基金代码查询；省略时查询接口允许的记录。
- `--name TEXT`：按基金经理姓名查询。

示例：

```bash
python scripts/fund_cli.py manager --code 110011.OF --limit 20
```
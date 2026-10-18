#!/usr/bin/env python3
"""热门板块回调低吸体系（system-id: hot_sector_pullback_system）MCP 服务入口。

一个体系一个服务：`system.yml`、`params/` 与 `templates/` 都在本目录内，目录名即 `system-id`。
注册见 `.pi/mcp.json` 的 `hot-sector-pullback-system`。

口径（2026-10-17 用户裁定）：
- 涨停/跌停按**分板精确**判定（北交所 30%、创业板/科创板 20%、主板 10%、ST 5%），剔除 N/C 新股与上市首日；
  涨停同时记录「含 ST」与 `clean`（剔 ST）两数，跌停剔除 ST。
- 候选的回调过滤采用**逐日比较**（对窗口内每个交易日重算 MA 后逐日比较），不使用「简化口径」。
- 全市场板块环境由本体系自算（不读取其它体系产物）。
- 事实计算全部在本服务完成；不查询账户、不下单、不写计划。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

REPO_ROOT = Path(os.environ.get("PI_PROJECT_DIR", "/pi-trader")).expanduser()
if not REPO_ROOT.exists():
    REPO_ROOT = Path(__file__).resolve().parents[4]
SYSTEM_ROOT = Path(__file__).resolve().parent
PARAMS_ROOT = SYSTEM_ROOT / "params"
TEMPLATES_ROOT = SYSTEM_ROOT / "templates"
SYSTEM_ID = SYSTEM_ROOT.name
SYSTEM_NAME = "热门板块回调低吸体系"
SYSTEM_VERSION = "v1"
PARAMETER_FILES = ("entry", "risk", "runtime", "sector_heat", "selection")
OPERATIONS = ("select_candidates", "sector_heat", "entry_signal", "risk_signal")
CONTENT_ROOT_NAMES = ("knowledge", "archive")
BENCHMARK_INDEX = "399006.SZ"
DAILY_SLEEP_SECONDS = 0.3
RISK_SLEEP_SECONDS = 5
HIT_LIMIT_EPSILON = 0.01
TUSHARE_PROXY_SCRIPTS = Path(
    os.environ.get("TUSHARE_PROXY_SCRIPTS", str(REPO_ROOT / ".pi/skills/source/tushare/tushare-proxy/scripts"))
)
if not PARAMS_ROOT.is_dir():
    raise RuntimeError(f"体系参数目录缺失：{PARAMS_ROOT}")


def load_env() -> None:
    env_file = REPO_ROOT / ".pi/mcp-servers/tushare/.env"
    if env_file.is_file():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def normalize_date(value: str | None) -> tuple[str, str]:
    if value is None:
        parsed = date.today()
    elif isinstance(value, str):
        fmt = "%Y-%m-%d" if "-" in value else "%Y%m%d"
        try:
            parsed = datetime.strptime(value, fmt).date()
        except ValueError as exc:
            raise ValueError(f"date 必须为 YYYYMMDD 或 YYYY-MM-DD: {value}") from exc
    else:
        raise ValueError("date 必须为 YYYYMMDD 或 YYYY-MM-DD")
    return parsed.strftime("%Y%m%d"), parsed.strftime("%Y-%m-%d")


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"JSON 文件不存在：{path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 无效：{path}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON 必须是对象：{path}")
    return value


def write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)


def fail(field: str, message: str) -> None:
    raise ValueError(f"字段 {field}: {message}")


def require_fields(value: Any, expected: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(field, "必须是 JSON 对象")
    missing = sorted(item for item in expected if item not in value)
    if missing:
        fail(field, f"缺少字段：{', '.join(missing)}")
    return value


def require_exact_fields(value: Any, expected: set[str], field: str) -> dict[str, Any]:
    require_fields(value, expected, field)
    unexpected = sorted(set(value) - expected)
    if unexpected:
        fail(field, f"存在未知字段：{', '.join(unexpected)}")
    return value


def require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(field, "必须是非空字符串")
    return value


def require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        fail(field, "必须是布尔值")
    return value


def require_integer(value: Any, field: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        fail(field, f"必须是不小于 {minimum} 的整数")
    return value


def require_ratio(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < float(value) < 1:
        fail(field, "必须在 (0, 1) 内")
    return float(value)


def require_unit_ratio(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < float(value) <= 1:
        fail(field, "必须在 (0, 1] 内")
    return float(value)


def load_parameters() -> dict[str, dict[str, Any]]:
    parameters = {name: read_json(PARAMS_ROOT / f"{name}.json") for name in PARAMETER_FILES}
    validate_parameters(parameters)
    return parameters


def validate_parameters(parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if set(parameters) != set(PARAMETER_FILES):
        raise ValueError(f"参数文件必须为：{', '.join(PARAMETER_FILES)}")
    for name, value in parameters.items():
        version = value.get("schema_version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            fail(f"{name}.schema_version", "必须是不小于 1 的整数")

    selection = parameters["selection"]
    require_exact_fields(selection, {"schema_version", "limit_up_window_days", "min_limit_up_count", "max_limit_up_count", "pullback_ma_period", "rebound_window_days"}, "selection")
    for field in ("limit_up_window_days", "min_limit_up_count", "max_limit_up_count", "pullback_ma_period", "rebound_window_days"):
        require_integer(selection[field], f"selection.{field}")
    if selection["min_limit_up_count"] > selection["max_limit_up_count"]:
        fail("selection.min_limit_up_count", "不能大于 max_limit_up_count")

    sector_heat = parameters["sector_heat"]
    require_exact_fields(sector_heat, {"schema_version", "limit_up_window_days", "trend_ma_periods", "volume_ratio_window_days", "max_consecutive_limit_up_days"}, "sector_heat")
    require_integer(sector_heat["limit_up_window_days"], "sector_heat.limit_up_window_days")
    require_integer(sector_heat["volume_ratio_window_days"], "sector_heat.volume_ratio_window_days")
    require_integer(sector_heat["max_consecutive_limit_up_days"], "sector_heat.max_consecutive_limit_up_days")
    periods = sector_heat["trend_ma_periods"]
    if not isinstance(periods, list) or len(periods) != 2:
        fail("sector_heat.trend_ma_periods", "必须是恰含两个正整数的数组")
    short_period = require_integer(periods[0], "sector_heat.trend_ma_periods[0]")
    long_period = require_integer(periods[1], "sector_heat.trend_ma_periods[1]")
    if short_period >= long_period:
        fail("sector_heat.trend_ma_periods", "必须严格递增")

    entry = parameters["entry"]
    require_exact_fields(entry, {"schema_version", "volume_multiplier", "volume_average_period", "breakout_ma_period"}, "entry")
    multiplier = entry["volume_multiplier"]
    if isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)) or multiplier <= 0:
        fail("entry.volume_multiplier", "必须是大于 0 的数值")
    require_integer(entry["volume_average_period"], "entry.volume_average_period")
    require_integer(entry["breakout_ma_period"], "entry.breakout_ma_period")

    risk = parameters["risk"]
    require_exact_fields(risk, {"schema_version", "opening_signal", "prudent_tag", "position_state", "exit_rules"}, "risk")
    opening = require_exact_fields(
        risk["opening_signal"],
        {"bar_frequency", "start_time", "end_time", "reference_price", "rapid_drop_pct", "fallback_sources"},
        "risk.opening_signal",
    )
    if opening["bar_frequency"] != "5min":
        fail("risk.opening_signal.bar_frequency", "必须为 5min")
    if opening["reference_price"] != "session_open":
        fail("risk.opening_signal.reference_price", "必须为 session_open")
    require_string(opening["start_time"], "risk.opening_signal.start_time")
    require_string(opening["end_time"], "risk.opening_signal.end_time")
    require_ratio(opening["rapid_drop_pct"], "risk.opening_signal.rapid_drop_pct")
    sources = opening["fallback_sources"]
    if not isinstance(sources, list) or not sources:
        fail("risk.opening_signal.fallback_sources", "必须是非空数组")
    if any(item not in {"official", "promax"} for item in sources):
        fail("risk.opening_signal.fallback_sources", "仅支持 official / promax")
    if len(set(sources)) != len(sources):
        fail("risk.opening_signal.fallback_sources", "不得重复")

    tags = require_exact_fields(
        risk["prudent_tag"],
        {"state_file", "valid_trading_days", "snapshot_lookback_trading_days", "refresh_on_bearish_signal"},
        "risk.prudent_tag",
    )
    require_string(tags["state_file"], "risk.prudent_tag.state_file")
    require_integer(tags["valid_trading_days"], "risk.prudent_tag.valid_trading_days")
    require_integer(tags["snapshot_lookback_trading_days"], "risk.prudent_tag.snapshot_lookback_trading_days")
    require_bool(tags["refresh_on_bearish_signal"], "risk.prudent_tag.refresh_on_bearish_signal")
    require_exact_fields(risk["position_state"], {"state_file"}, "risk.position_state")
    require_string(risk["position_state"]["state_file"], "risk.position_state.state_file")

    exits = require_exact_fields(risk["exit_rules"], {"hard_stop_loss_pct", "ma5", "ma10"}, "risk.exit_rules")
    require_ratio(exits["hard_stop_loss_pct"], "risk.exit_rules.hard_stop_loss_pct")
    ma5 = require_exact_fields(
        exits["ma5"],
        {"period", "break_action", "normal_observation_days", "prudent_observation_days", "reduce_ratio"},
        "risk.exit_rules.ma5",
    )
    require_integer(ma5["period"], "risk.exit_rules.ma5.period")
    require_integer(ma5["normal_observation_days"], "risk.exit_rules.ma5.normal_observation_days", 0)
    require_integer(ma5["prudent_observation_days"], "risk.exit_rules.ma5.prudent_observation_days", 0)
    if ma5["break_action"] != "observe_or_reduce":
        fail("risk.exit_rules.ma5.break_action", "必须为 observe_or_reduce")
    require_unit_ratio(ma5["reduce_ratio"], "risk.exit_rules.ma5.reduce_ratio")
    ma10 = require_exact_fields(exits["ma10"], {"period", "break_action", "execution_timing"}, "risk.exit_rules.ma10")
    require_integer(ma10["period"], "risk.exit_rules.ma10.period")
    if ma10["break_action"] != "liquidate" or ma10["execution_timing"] != "next_open":
        fail("risk.exit_rules.ma10", "必须为 liquidate / next_open")

    runtime = parameters["runtime"]
    require_exact_fields(
        runtime,
        {"schema_version", "process_root", "plan_root", "review_root", "directory_date_format", "trading_day_only", "history_lookback_calendar_days"},
        "runtime",
    )
    require_string(runtime["process_root"], "runtime.process_root")
    for field in ("plan_root", "review_root"):
        require_string(runtime[field], f"runtime.{field}")
    if runtime["directory_date_format"] != "%Y-%m-%d":
        fail("runtime.directory_date_format", "必须为 %Y-%m-%d")
    require_bool(runtime["trading_day_only"], "runtime.trading_day_only")
    require_integer(runtime["history_lookback_calendar_days"], "runtime.history_lookback_calendar_days")
    return {"valid": True, "files": list(PARAMETER_FILES)}


def parameter_metadata(parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    encoded = json.dumps(parameters, ensure_ascii=False, sort_keys=True).encode()
    return {
        "parameter_version": SYSTEM_VERSION,
        "parameter_hash": hashlib.sha256(encoded).hexdigest(),
        "schema_versions": {name: parameters[name]["schema_version"] for name in PARAMETER_FILES},
    }


def logical_root(field: str) -> str:
    raw = str(read_json(PARAMS_ROOT / "runtime.json")[field])
    return raw.split("/", 1)[1] if raw.startswith("knowledge/") else raw


def process_roots() -> list[tuple[Path, str]]:
    relative = logical_root("process_root")
    return [(REPO_ROOT / name / relative, name) for name in CONTENT_ROOT_NAMES]


def process_dir(directory_date: str, create: bool = False) -> Path:
    path = process_roots()[0][0] / directory_date / SYSTEM_NAME
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_process_file(directory_date: str, filename: str) -> Path | None:
    for root, _ in process_roots():
        candidate = root / directory_date / SYSTEM_NAME / filename
        if candidate.is_file():
            return candidate
    return None


def logical_process_path(directory_date: str, filename: str) -> str:
    return f"{logical_root('process_root')}/{directory_date}/{SYSTEM_NAME}/{filename}"


def load_process_document(directory_date: str, filename: str) -> dict[str, Any]:
    path = resolve_process_file(directory_date, filename)
    if path is None:
        raise ValueError(f"上游过程资料缺失：{logical_process_path(directory_date, filename)}")
    return read_json(path)


def latest_snapshot(run_api_date: str, filename: str, trade_days: list[str], back_n: int) -> tuple[Path, str] | None:
    earlier = sorted({normalize_date(str(item))[0] for item in trade_days if normalize_date(str(item))[0] < run_api_date})
    for trade_date in reversed(earlier[-back_n:]):
        directory_date = normalize_date(trade_date)[1]
        path = resolve_process_file(directory_date, filename)
        if path is not None:
            return path, trade_date
    return None


def artifact(kind: str, directory_date: str, parameters: dict[str, dict[str, Any]], note: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": directory_date,
        "artifact": kind,
        "system_id": SYSTEM_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": note,
        **parameter_metadata(parameters),
        **payload,
    }


def get_client() -> Any:
    load_env()
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    import tushare as ts
    ts.set_token(token)
    return ts.pro_api()


def fetch_trade_days(client: Any, start_date: str, end_date: str) -> list[str]:
    calendar = client.trade_cal(exchange="SSE", start_date=start_date, end_date=end_date, fields="cal_date,is_open")
    if calendar is None or calendar.empty:
        return []
    return sorted(calendar.loc[calendar["is_open"] == 1, "cal_date"].astype(str).tolist())


def fetch_trade_calendar(client: Any, api_date: str) -> dict[str, Any]:
    """单日交易日历：是否开市与上一交易日（来源 tushare.trade_cal，SSE）。"""
    frame = client.trade_cal(exchange="SSE", start_date=api_date, end_date=api_date, fields="exchange,cal_date,is_open,pretrade_date")
    if frame is None or frame.empty:
        raise ValueError(f"未获取到交易日历：{api_date}")
    record = frame.to_dict("records")[0]
    previous = record.get("pretrade_date")
    return {"is_open": int(record["is_open"]) == 1, "pretrade_date": str(previous) if previous else None}


def fetch_daily_market(client: Any, trade_days: list[str], fields: str) -> Any:
    import pandas as pd
    frames = []
    for trade_date in trade_days:
        frame = client.daily(trade_date=trade_date, fields=fields)
        if frame is not None and not frame.empty:
            frames.append(frame)
        time.sleep(DAILY_SLEEP_SECONDS)
    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)
    result["trade_date"] = result["trade_date"].astype(str)
    for column in ("open", "high", "close", "vol", "amount", "pct_chg"):
        if column in result.columns:
            result[column] = result[column].astype(float)
    return result


def fetch_stock_info(client: Any) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    stocks = client.stock_basic(fields="ts_code,name,industry,list_date")
    if stocks is None or stocks.empty:
        return {}, {}, {}
    industry_by_code: dict[str, str] = {}
    name_by_code: dict[str, str] = {}
    list_date_by_code: dict[str, str] = {}
    for _, row in stocks.iterrows():
        code = str(row["ts_code"])
        industry_by_code[code] = str(row["industry"] or "")
        name_by_code[code] = str(row["name"])
        list_date_by_code[code] = str(row["list_date"] or "")
    return industry_by_code, name_by_code, list_date_by_code


def is_st(name: str) -> bool:
    return "ST" in name.upper().replace(" ", "")


def is_new_or_first_day(name: str, list_date: str, trade_date: str) -> bool:
    return list_date == trade_date or name.startswith(("N", "C"))


def limit_pct(code: str, name: str) -> float:
    """分板精确涨停阈值：北交所 30%、创业板/科创板 20%、ST 5%、其余主板 10%。"""
    if code.endswith(".BJ"):
        return 30.0
    if code.startswith(("30", "68")):
        return 20.0
    if is_st(name):
        return 5.0
    return 10.0


def hit_limit(pct_chg: Any, threshold: float) -> bool:
    try:
        return float(pct_chg) >= threshold - HIT_LIMIT_EPSILON
    except (TypeError, ValueError):
        return False


def moving_average(values: list[float], period: int) -> float | None:
    if len(values) < period or period < 1:
        return None
    return sum(values[-period:]) / period


def passes_pullback_filter(closes: list[float], period: int, rebound_window: int) -> tuple[bool, float | None, int | None]:
    """逐日比较：窗口内每个交易日重算 MA；要求当日收盘 ≥ 当日 MA，且最近一次跌破后的反弹不超过 rebound_window。"""
    if len(closes) < period:
        return False, None, None
    current_ma = moving_average(closes, period)
    if current_ma is None or closes[-1] < current_ma:
        return False, current_ma, None
    last_below_index = None
    for index in range(period - 1, len(closes)):
        average = moving_average(closes[: index + 1], period)
        if average is not None and closes[index] < average:
            last_below_index = index
    if last_below_index is None:
        return True, current_ma, None
    bounceback_days = len(closes) - 1 - last_below_index
    if bounceback_days > rebound_window:
        return False, current_ma, bounceback_days
    recovered = True
    for index in range(last_below_index + 1, len(closes)):
        average = moving_average(closes[: index + 1], period)
        if average is not None and closes[index] < average:
            recovered = False
            break
    return recovered, current_ma, bounceback_days


def build_candidates(
    daily: Any,
    window_days: set[str],
    target_date: str,
    industry_by_code: dict[str, str],
    name_by_code: dict[str, str],
    list_date_by_code: dict[str, str],
    selection: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    candidates: list[dict[str, Any]] = []
    limit_up_codes: set[str] = set()
    for code, records in daily.groupby("ts_code"):
        records = records.sort_values("trade_date")
        name = name_by_code.get(str(code), "")
        threshold = limit_pct(str(code), name)
        board_dates = sorted(
            str(item)
            for item in records.loc[
                records["trade_date"].isin(window_days) & (records["pct_chg"] >= threshold - HIT_LIMIT_EPSILON),
                "trade_date",
            ].tolist()
        )
        if not (selection["min_limit_up_count"] <= len(board_dates) <= selection["max_limit_up_count"]):
            continue
        if is_new_or_first_day(name, list_date_by_code.get(str(code), ""), target_date):
            continue
        limit_up_codes.add(str(code))
        closes = [float(value) for value in records["close"].tolist()]
        passed, average, bounceback_days = passes_pullback_filter(
            closes, selection["pullback_ma_period"], selection["rebound_window_days"]
        )
        if not passed or average is None:
            continue
        current_close = closes[-1]
        board_records = records.loc[records["trade_date"].isin(board_dates)]
        peak = float(board_records["high"].max()) if not board_records.empty else current_close
        candidates.append(
            {
                "code": str(code),
                "name": name,
                "industry": industry_by_code.get(str(code), ""),
                "board_count": len(board_dates),
                "board_dates": board_dates,
                "current_close": round(current_close, 3),
                "pullback_ma": round(average, 3),
                "pullback_pct": round((current_close - peak) / peak * 100, 2),
                "bounceback_days": bounceback_days,
            }
        )
    candidates.sort(key=lambda item: item["pullback_pct"])
    return candidates, len(limit_up_codes)


def build_signal(candidate: dict[str, Any], records: Any, entry: dict[str, Any]) -> dict[str, Any] | None:
    required_days = max(entry["volume_average_period"], entry["breakout_ma_period"])
    if len(records) < required_days:
        return None
    closes = [float(value) for value in records["close"].tolist()]
    volumes = [float(value) for value in records["vol"].tolist()]
    breakout_ma = moving_average(closes, entry["breakout_ma_period"])
    volume_ma = moving_average(volumes, entry["volume_average_period"])
    if breakout_ma is None or volume_ma is None or volume_ma <= 0:
        return None
    close = closes[-1]
    volume = volumes[-1]
    if close <= breakout_ma or volume <= entry["volume_multiplier"] * volume_ma:
        return None
    latest = records.iloc[-1]
    return {
        "code": candidate["code"],
        "name": candidate["name"],
        "industry": candidate["industry"],
        "board_count": candidate["board_count"],
        "board_dates": candidate["board_dates"],
        "pullback_pct": candidate["pullback_pct"],
        "signal_date": str(latest["trade_date"]),
        "close": round(close, 3),
        "breakout_ma": round(breakout_ma, 3),
        "breakout_above_pct": round((close - breakout_ma) / breakout_ma * 100, 2),
        "volume": int(volume),
        "volume_ma": int(volume_ma),
        "volume_ratio": round(volume / volume_ma, 2),
        "pass": True,
    }


def daily_window_start(target_api_date: str, calendar_days: int) -> str:
    return (datetime.strptime(target_api_date, "%Y%m%d") - timedelta(days=calendar_days)).strftime("%Y%m%d")


def market_daily_start(target_api_date: str, parameters: dict[str, dict[str, Any]]) -> str:
    selection = parameters["selection"]
    sector_heat = parameters["sector_heat"]
    calendar_days = (
        max(
            selection["limit_up_window_days"] + selection["pullback_ma_period"],
            sector_heat["limit_up_window_days"] + max(sector_heat["trend_ma_periods"]) + sector_heat["volume_ratio_window_days"],
        )
        * 3
    )
    return daily_window_start(target_api_date, calendar_days)


def op_select_candidates(
    target_api_date: str,
    directory_date: str,
    industries: list[str] | None,
    parameters: dict[str, dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    client = get_client()
    selection = parameters["selection"]
    trade_days = fetch_trade_days(client, market_daily_start(target_api_date, parameters), target_api_date)
    if target_api_date not in trade_days:
        raise ValueError(f"{directory_date} 不是交易日，无候选事实")
    window_days = set(trade_days[-selection["limit_up_window_days"]:])
    daily = fetch_daily_market(client, trade_days, fields="ts_code,trade_date,close,high,vol,pct_chg")
    if daily.empty:
        raise RuntimeError("未获取到日线数据")
    industry_by_code, name_by_code, list_date_by_code = fetch_stock_info(client)
    candidates, total_limit_up = build_candidates(
        daily, window_days, target_api_date, industry_by_code, name_by_code, list_date_by_code, selection
    )
    filtered = [
        item
        for item in candidates
        if not industries or item["industry"] in set(industries)
    ]
    kind = "hottest_industry_candidate" if industries else "full_market_candidate"
    filename = f"{kind}.json"
    sectors = sorted({item["industry"] for item in filtered if item["industry"]})
    note = (
        f"窗口＝最近 {selection['limit_up_window_days']} 个交易日；涨停＝分板精确（北交所 30%／双创 20%／主板 10%／ST 5%，"
        f"容差 {HIT_LIMIT_EPSILON}），剔除 N/C 新股与上市首日；回调过滤＝逐日重算 MA{selection['pullback_ma_period']} 后逐日比较，"
        f"反弹窗口 {selection['rebound_window_days']} 个交易日。"
    )
    payload = artifact(
        kind,
        directory_date,
        parameters,
        note,
        {
            "params": {key: value for key, value in selection.items() if key != "schema_version"},
            "stats": {
                "total_limit_up_stocks": total_limit_up,
                "total_candidates": len(filtered),
                "candidate_sectors": len(sectors),
            },
            "candidates": filtered,
        },
    )
    if industries:
        payload["industry"] = list(industries)
    if dry_run:
        return {"ok": True, "dry_run": True, "artifact": kind, "date": directory_date, "document": payload}
    path = write_json(process_dir(directory_date, create=True) / filename, payload)
    return {"ok": True, "artifact": kind, "date": directory_date, "path": path, "logical_path": logical_process_path(directory_date, filename), "stats": payload["stats"]}


def build_sector_environment(
    daily: Any,
    target_date: str,
    previous_trade_date: str | None,
    industry_by_code: dict[str, str],
    name_by_code: dict[str, str],
    list_date_by_code: dict[str, str],
    parameters: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    client = get_client()
    limit_up_by_industry: dict[str, int] = defaultdict(int)
    limit_up_sample: list[str] = []
    limit_up_total = 0
    limit_up_clean = 0
    limit_down_total = 0
    up = down = flat = 0
    amount_total = 0.0
    highest = {"count": 0, "code": "", "name": "", "industry": ""}

    grouped = {str(code): records.sort_values("trade_date") for code, records in daily.groupby("ts_code")}
    for code, records in grouped.items():
        today = records.loc[records["trade_date"] == target_date]
        if today.empty:
            continue
        row = today.iloc[-1]
        name = name_by_code.get(code, "")
        if is_new_or_first_day(name, list_date_by_code.get(code, ""), target_date):
            continue
        pct = float(row["pct_chg"])
        amount_total += float(row.get("amount", 0.0) or 0.0)
        if pct > 0:
            up += 1
        elif pct < 0:
            down += 1
        else:
            flat += 1
        threshold = limit_pct(code, name)
        if hit_limit(pct, threshold):
            limit_up_total += 1
            industry = industry_by_code.get(code, "")
            if not is_st(name):
                limit_up_clean += 1
                limit_up_by_industry[industry] += 1
                if len(limit_up_sample) < 20:
                    limit_up_sample.append(f"{code} {name}（{industry}）")
        elif is_st(name) is False and hit_limit(-pct, threshold):
            limit_down_total += 1

    for code, records in grouped.items():
        count = 0
        for _, row in records.sort_values("trade_date", ascending=False).iterrows():
            name = name_by_code.get(code, "")
            if not hit_limit(float(row["pct_chg"]), limit_pct(code, name)):
                break
            count += 1
        if count > highest["count"]:
            highest = {
                "count": count,
                "code": code,
                "name": name_by_code.get(code, ""),
                "industry": industry_by_code.get(code, ""),
            }

    previous_amount = 0.0
    if previous_trade_date:
        previous_rows = daily.loc[daily["trade_date"] == previous_trade_date]
        if not previous_rows.empty:
            previous_amount = float(previous_rows["amount"].sum())

    benchmark_pct = fetch_index_pct(client, BENCHMARK_INDEX, target_date)
    if benchmark_pct is None:
        benchmark_tier = "unavailable"
    elif benchmark_pct > 0:
        benchmark_tier = "企稳"
    elif benchmark_pct > -2:
        benchmark_tier = "非极端弱"
    else:
        benchmark_tier = "极端弱"

    ranking = sorted(
        ({"industry": key, "limit_up_clean": value} for key, value in limit_up_by_industry.items()),
        key=lambda item: item["limit_up_clean"],
        reverse=True,
    )
    return {
        "market": {
            "up": up,
            "down": down,
            "flat": flat,
            "limit_up": limit_up_total,
            "limit_up_clean": limit_up_clean,
            "limit_down_clean": limit_down_total,
            "total_amount_yi": round(amount_total / 100000.0, 4),
            "previous_amount_yi": round(previous_amount / 100000.0, 4),
            "amount_change_yi": round((amount_total - previous_amount) / 100000.0, 4),
        },
        "limit_up_by_industry": ranking,
        "limit_up_sample": limit_up_sample,
        "highest_board": highest,
        "benchmark": {"ts_code": BENCHMARK_INDEX, "pct_chg": benchmark_pct, "tier": benchmark_tier},
        "note": (
            f"涨停/跌停＝分板精确阈值（北交所 30%／双创 20%／主板 10%／ST 5%，容差 {HIT_LIMIT_EPSILON}）；"
            "剔除 N/C 新股与上市首日；涨停行业分布与 sample 只统计 clean（剔 ST），跌停剔 ST；"
            f"大盘三档＝{BENCHMARK_INDEX} 当日涨跌幅（企稳>0／非极端弱 −2%~0／极端弱 ≤−2%）。"
        ),
    }


def fetch_index_pct(client: Any, ts_code: str, target_api_date: str) -> float | None:
    try:
        frame = client.index_daily(ts_code=ts_code, trade_date=target_api_date)
    except Exception:  # noqa: BLE001
        return None
    if frame is None or frame.empty or "pct_chg" not in frame:
        return None
    return round(float(frame.iloc[0]["pct_chg"]), 4)


def sector_statistics(
    daily: Any,
    target_date: str,
    sectors: list[str],
    candidates: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    industry_by_code: dict[str, str],
    name_by_code: dict[str, str],
    parameters: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    sector_heat = parameters["sector_heat"]
    short_period, long_period = sector_heat["trend_ma_periods"]
    volume_window = sector_heat["volume_ratio_window_days"]
    daily_with_sector = daily.assign(sector=daily["ts_code"].map(industry_by_code))
    candidate_count: dict[str, int] = defaultdict(int)
    signal_count: dict[str, int] = defaultdict(int)
    for item in candidates:
        candidate_count[item["industry"]] += 1
    for item in signals:
        signal_count[item["industry"]] += 1

    limit_up_total: dict[str, int] = defaultdict(int)
    limit_up_clean: dict[str, int] = defaultdict(int)
    for code, records in daily.groupby("ts_code"):
        code = str(code)
        today = records.loc[records["trade_date"] == target_date]
        if today.empty:
            continue
        name = name_by_code.get(code, "")
        if is_new_or_first_day(name, "", target_date):
            continue
        if not hit_limit(float(today.iloc[-1]["pct_chg"]), limit_pct(code, name)):
            continue
        sector = industry_by_code.get(code, "")
        limit_up_total[sector] += 1
        if not is_st(name):
            limit_up_clean[sector] += 1

    rows: list[dict[str, Any]] = []
    for sector in sectors:
        sector_daily = daily_with_sector.loc[daily_with_sector["sector"] == sector]
        grouped = sector_daily.groupby("trade_date", sort=True)
        pct_series = [float(value) for value in grouped["pct_chg"].mean().tolist()]
        volumes = [float(value) for value in grouped["vol"].sum().tolist()]
        short_ma = moving_average(pct_series, short_period)
        long_ma = moving_average(pct_series, long_period)
        prior_volumes = volumes[-volume_window - 1 : -1]
        volume_ratio = None
        if len(prior_volumes) == volume_window and sum(prior_volumes) > 0:
            volume_ratio = volumes[-1] / (sum(prior_volumes) / len(prior_volumes))
        trend = "—"
        if short_ma is not None and long_ma is not None:
            trend = "多头排列" if short_ma > long_ma else "空头"
        rows.append(
            {
                "industry": sector,
                "candidates": candidate_count[sector],
                "signals": signal_count[sector],
                "short_ma_pct": round(short_ma, 2) if short_ma is not None else None,
                "long_ma_pct": round(long_ma, 2) if long_ma is not None else None,
                "trend": trend,
                "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
                "limit_up_count": limit_up_total[sector],
                "limit_up_clean": limit_up_clean[sector],
            }
        )
    return rows


def signalize(
    daily_by_code: dict[str, Any],
    candidates: list[dict[str, Any]],
    target_api_date: str,
    entry: dict[str, Any],
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for candidate in candidates:
        records = daily_by_code.get(candidate["code"])
        if records is None:
            continue
        records = records.loc[records["trade_date"] <= target_api_date]
        signal = build_signal(candidate, records, entry)
        if signal:
            signals.append(signal)
    signals.sort(key=lambda item: item["volume_ratio"], reverse=True)
    return signals


def op_sector_heat(
    target_api_date: str,
    directory_date: str,
    parameters: dict[str, dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    candidate_document = load_process_document(directory_date, "full_market_candidate.json")
    candidates = candidate_document.get("candidates", [])
    sectors = sorted({item["industry"] for item in candidates if item.get("industry")})
    client = get_client()
    trade_days = fetch_trade_days(client, market_daily_start(target_api_date, parameters), target_api_date)
    if target_api_date not in trade_days:
        raise ValueError(f"{directory_date} 不是交易日，无板块热度事实")
    previous_trade_date = trade_days[trade_days.index(target_api_date) - 1] if trade_days.index(target_api_date) > 0 else None
    daily = fetch_daily_market(client, trade_days, fields="ts_code,trade_date,close,high,vol,amount,pct_chg")
    if daily.empty:
        raise RuntimeError("未获取到板块热度所需日线数据")
    industry_by_code, name_by_code, list_date_by_code = fetch_stock_info(client)
    daily_by_code = {str(code): records.sort_values("trade_date") for code, records in daily.groupby("ts_code")}
    signals = signalize(daily_by_code, candidates, target_api_date, parameters["entry"])
    rows = sector_statistics(daily, target_api_date, sectors, candidates, signals, industry_by_code, name_by_code, parameters)
    environment = build_sector_environment(
        daily, target_api_date, previous_trade_date, industry_by_code, name_by_code, list_date_by_code, parameters
    )
    heat_payload = artifact(
        "sector_heat",
        directory_date,
        parameters,
        (
            "short/long_ma_pct＝板块成分股当日平均涨幅的 "
            f"{parameters['sector_heat']['trend_ma_periods'][0]}/{parameters['sector_heat']['trend_ma_periods'][1]} 日均值；"
            f"trend＝short>long 记「多头排列」否则「空头」；volume_ratio＝板块当日总成交量 ÷ 前 "
            f"{parameters['sector_heat']['volume_ratio_window_days']} 日均量；涨停为分板精确口径（clean 剔 ST）。"
        ),
        {
            "params": {key: value for key, value in parameters["sector_heat"].items() if key != "schema_version"},
            "stats": {
                "total_candidates": len(candidates),
                "candidate_sectors": len(sectors),
                "signals": len(signals),
                "max_board_count": environment["highest_board"]["count"],
            },
            "candidate_sectors": sectors,
            "sectors": rows,
        },
    )
    environment_payload = artifact(
        "sector_environment",
        directory_date,
        parameters,
        environment["note"],
        {
            "market": environment["market"],
            "limit_up_by_industry": environment["limit_up_by_industry"],
            "limit_up_sample": environment["limit_up_sample"],
            "highest_board": environment["highest_board"],
            "benchmark": environment["benchmark"],
        },
    )
    if dry_run:
        return {"ok": True, "dry_run": True, "artifact": "sector_heat", "date": directory_date, "document": heat_payload, "environment": environment_payload}
    heat_path = write_json(process_dir(directory_date, create=True) / "sector_heat.json", heat_payload)
    environment_path = write_json(process_dir(directory_date, create=True) / "sector_environment.json", environment_payload)
    return {
        "ok": True,
        "artifact": "sector_heat",
        "date": directory_date,
        "paths": [heat_path, environment_path],
        "logical_paths": [logical_process_path(directory_date, "sector_heat.json"), logical_process_path(directory_date, "sector_environment.json")],
        "stats": heat_payload["stats"],
    }


def op_entry_signal(
    target_api_date: str,
    directory_date: str,
    industries: list[str] | None,
    parameters: dict[str, dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    source_file = "hottest_industry_candidate.json" if industries else "full_market_candidate.json"
    candidate_document = load_process_document(directory_date, source_file)
    candidates = candidate_document.get("candidates", [])
    entry = parameters["entry"]
    client = get_client()
    required_days = max(entry["volume_average_period"], entry["breakout_ma_period"])
    trade_days = fetch_trade_days(client, daily_window_start(target_api_date, required_days * 3), target_api_date)
    daily = fetch_daily_market(client, trade_days, fields="ts_code,trade_date,close,vol")
    if daily.empty:
        raise RuntimeError("未获取到建仓信号所需日线数据")
    daily_by_code = {str(code): records.sort_values("trade_date") for code, records in daily.groupby("ts_code")}
    signals = signalize(daily_by_code, candidates, target_api_date, entry)
    payload = artifact(
        "entry_signal",
        directory_date,
        parameters,
        (
            f"条件＝收盘 > MA{entry['breakout_ma_period']} 且 量 ≥ {entry['volume_multiplier']}×{entry['volume_average_period']} 日均量（含当日）；"
            f"输入＝{source_file}（{len(candidates)} 只候选）。"
        ),
        {
            "source": logical_process_path(directory_date, source_file),
            "params": {key: value for key, value in entry.items() if key != "schema_version"},
            "stats": {
                "total_candidates": len(candidates),
                "with_daily_data": sum(1 for item in candidates if item["code"] in daily_by_code),
                "signals": len(signals),
            },
            "signals": signals,
        },
    )
    if dry_run:
        return {"ok": True, "dry_run": True, "artifact": "entry_signal", "date": directory_date, "document": payload}
    path = write_json(process_dir(directory_date, create=True) / "entry_signal.json", payload)
    return {"ok": True, "artifact": "entry_signal", "date": directory_date, "path": path, "logical_path": logical_process_path(directory_date, "entry_signal.json"), "stats": payload["stats"]}


BEARISH_OPENING_SIGNALS = {"weak_distribution", "weak_rebound", "rapid_drop"}


def fetch_official_bars(client: Any, code: str, opening: dict[str, Any], directory_date: str) -> Any:
    return client.stk_mins(
        ts_code=code,
        freq=opening["bar_frequency"],
        start_date=f"{directory_date} {opening['start_time']}:00",
        end_date=f"{directory_date} {opening['end_time']}:00",
    )


def fetch_proxy_bars(code: str, opening: dict[str, Any], directory_date: str) -> Any:
    if not TUSHARE_PROXY_SCRIPTS.is_dir():
        raise RuntimeError(f"tushare-proxy 技能目录不存在：{TUSHARE_PROXY_SCRIPTS}")
    if str(TUSHARE_PROXY_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(TUSHARE_PROXY_SCRIPTS))
    import ts_proxy
    frame = ts_proxy.get(
        "stk_mins",
        ts_code=code,
        freq=opening["bar_frequency"],
        start_date=f"{directory_date} {opening['start_time']}:00",
        end_date=f"{directory_date} {opening['end_time']}:00",
    )
    if frame is None or frame.empty:
        raise RuntimeError("promax 返回空数据")
    dates = {str(value)[:10] for value in frame["trade_time"]}
    if dates != {directory_date}:
        raise RuntimeError(f"promax 返回日期不符：{sorted(dates)} != {directory_date}")
    return frame


def classify_opening_signal(bars: Any, config: dict[str, Any], reference_open: float | None = None) -> dict[str, Any]:
    import pandas as pd
    if bars is None or (isinstance(bars, pd.DataFrame) and bars.empty) or "close" not in bars:
        return {"status": "unavailable", "signal": "unavailable"}
    time_column = "trade_time" if "trade_time" in bars else "trade_date"
    ordered = bars.sort_values(time_column)
    closes = [float(value) for value in ordered["close"].tolist()]
    first_open = float(ordered.iloc[0].get("open", closes[0]))
    if reference_open is not None and reference_open > 0:
        reference = float(reference_open)
    else:
        reference = first_open
    low = min(closes)
    high = max(closes)
    last_close = closes[-1]
    low_index = closes.index(low)
    high_index = closes.index(high)
    rapid_drop_pct = config["opening_signal"]["rapid_drop_pct"]
    if low <= reference * (1 - rapid_drop_pct):
        signal = "rapid_drop"
    elif high_index < low_index and high > reference and last_close < reference:
        signal = "weak_distribution"
    elif low_index < high_index and low < reference and last_close < reference:
        signal = "weak_rebound"
    elif high_index < low_index and low >= reference:
        signal = "strong_continuation"
    elif low_index < high_index and last_close >= reference:
        signal = "strong_recovery"
    else:
        signal = "neutral"
    return {
        "status": "ok",
        "signal": signal,
        "reference_price": round(reference, 3),
        "last_close": round(last_close, 3),
        "low": round(low, 3),
        "high": round(high, 3),
        "bars": len(closes),
    }


def fetch_opening_signal(client: Any, code: str, target_api_date: str, config: dict[str, Any], reference_open: float | None = None) -> dict[str, Any]:
    opening = config["opening_signal"]
    directory_date = normalize_date(target_api_date)[1]
    errors: list[str] = []
    for source in opening["fallback_sources"]:
        try:
            if source == "official":
                bars = fetch_official_bars(client, code, opening, directory_date)
            else:
                bars = fetch_proxy_bars(code, opening, directory_date)
            signal = classify_opening_signal(bars, config, reference_open)
            if signal.get("signal") == "unavailable":
                errors.append(f"{source}: 空数据")
                continue
            signal["source"] = source
            return signal
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source}: {type(exc).__name__}: {exc}")
    return {"status": "unavailable", "signal": "unavailable", "source": "unavailable", "errors": errors}


def tag_is_active(tag: dict[str, Any] | None, target_api_date: str) -> bool:
    return bool(tag and tag.get("expire_date", "") >= target_api_date)


def tag_expire_date(target_api_date: str, trade_days: list[str], valid_days: int) -> str:
    index = trade_days.index(target_api_date)
    return trade_days[min(index + valid_days - 1, len(trade_days) - 1)]


def transition_prudent_tag(
    current_tag: dict[str, Any] | None,
    opening_signal: dict[str, Any],
    target_api_date: str,
    trade_days: list[str],
    config: dict[str, Any],
) -> dict[str, Any] | None:
    active = current_tag if tag_is_active(current_tag, target_api_date) else None
    should_refresh = config["prudent_tag"]["refresh_on_bearish_signal"] and opening_signal["signal"] in BEARISH_OPENING_SIGNALS
    if not should_refresh:
        return active
    return {
        "created_date": target_api_date,
        "expire_date": tag_expire_date(target_api_date, trade_days, config["prudent_tag"]["valid_trading_days"]),
        "signal": opening_signal["signal"],
    }


def evaluate_risk(
    buy_price: float,
    records: list[dict[str, Any]],
    prudent_tag: dict[str, Any] | None,
    prior_state: dict[str, Any],
    target_api_date: str,
    trade_days: list[str],
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    exits = config["exit_rules"]
    ma5_rule = exits["ma5"]
    ma10_rule = exits["ma10"]
    closes = [float(item["close"]) for item in records]
    close = closes[-1]
    ma5 = moving_average(closes, ma5_rule["period"])
    ma10 = moving_average(closes, ma10_rule["period"])
    state = dict(prior_state)
    if ma10 is not None and close < ma10:
        return {"action": "liquidate", "reason": "below_ma10", "daily": {"ma5": round(ma5, 3) if ma5 is not None else None, "ma10": round(ma10, 3)}}, state
    if close <= buy_price * (1 - exits["hard_stop_loss_pct"]):
        return {"action": "liquidate", "reason": "hard_stop_loss", "daily": {"ma5": round(ma5, 3) if ma5 is not None else None, "ma10": round(ma10, 3) if ma10 is not None else None}}, state
    daily = {"ma5": round(ma5, 3) if ma5 is not None else None, "ma10": round(ma10, 3) if ma10 is not None else None}
    if ma5 is None or close >= ma5:
        state.pop("ma5_below_since", None)
        return {"action": "hold", "reason": "no_risk_trigger", "daily": daily}, state
    first_below_date = state.get("ma5_below_since", target_api_date)
    state["ma5_below_since"] = first_below_date
    observed_days = len([day for day in trade_days if first_below_date <= day <= target_api_date])
    observation_days = (
        ma5_rule["prudent_observation_days"] if tag_is_active(prudent_tag, target_api_date) else ma5_rule["normal_observation_days"]
    )
    action = "reduce" if observed_days > observation_days else "observe"
    reason = "below_ma5" if action == "reduce" else "ma5_observation"
    return {"action": action, "reason": reason, "daily": daily}, state


def load_snapshot_positions(target_api_date: str, filename: str, trade_days: list[str], lookback_days: int) -> dict[str, Any]:
    found = latest_snapshot(target_api_date, filename, trade_days, lookback_days)
    if not found:
        return {}
    path, _ = found
    snapshot = read_json(path)
    positions = snapshot.get("positions", {})
    if not isinstance(positions, dict):
        raise ValueError(f"状态快照 positions 必须是对象：{path}")
    return positions


def op_risk_signal(
    target_api_date: str,
    directory_date: str,
    positions: dict[str, Any] | None,
    parameters: dict[str, dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    config = parameters["risk"]
    if positions is None:
        path = resolve_process_file(directory_date, "positions.json")
        positions = read_json(path) if path is not None else {}
    cleaned: dict[str, float] = {}
    for code, buy_price in positions.items():
        require_string(code, "positions 代码")
        if isinstance(buy_price, bool) or not isinstance(buy_price, (int, float)) or buy_price <= 0:
            fail(f"positions.{code}", "必须为正数买入价")
        cleaned[str(code)] = float(buy_price)

    if not cleaned:
        payload = artifact(
            "risk_signal",
            directory_date,
            parameters,
            "空仓契约：无持仓时不继承旧快照，state/prudent_tags 置为空仓位结构。",
            {
                "params": {key: value for key, value in config.items() if key != "schema_version"},
                "data_sources": {},
                "stats": {"positions": 0, "evaluated": 0, "actions": 0, "hold": 0},
                "risk_actions": [],
                "holdings": [],
            },
        )
        if dry_run:
            return {"ok": True, "dry_run": True, "artifact": "risk_signal", "date": directory_date, "document": payload}
        directory = process_dir(directory_date, create=True)
        paths = [
            write_json(directory / "risk_signal.json", payload),
            write_json(directory / config["prudent_tag"]["state_file"], {"date": target_api_date, "positions": {}}),
            write_json(directory / config["position_state"]["state_file"], {"date": target_api_date, "positions": {}}),
            write_json(directory / "positions.json", {}),
        ]
        return {"ok": True, "artifact": "risk_signal", "date": directory_date, "paths": paths, "stats": payload["stats"]}

    client = get_client()
    start_date = (datetime.strptime(target_api_date, "%Y%m%d") - timedelta(days=70)).strftime("%Y%m%d")
    calendar_end = (datetime.strptime(target_api_date, "%Y%m%d") + timedelta(days=config["prudent_tag"]["valid_trading_days"] * 3)).strftime("%Y%m%d")
    trade_days = fetch_trade_days(client, start_date, calendar_end)
    daily_trade_days = [day for day in trade_days if day <= target_api_date]
    if target_api_date not in daily_trade_days:
        raise ValueError(f"{directory_date} 不是交易日，无风控事实")
    lookback = config["prudent_tag"]["snapshot_lookback_trading_days"]
    prior_tags = load_snapshot_positions(target_api_date, config["prudent_tag"]["state_file"], trade_days, lookback)
    prior_states = load_snapshot_positions(target_api_date, config["position_state"]["state_file"], trade_days, lookback)

    stocks = client.stock_basic(ts_code=",".join(cleaned), fields="ts_code,name")
    name_by_code: dict[str, str] = {}
    if stocks is not None and not stocks.empty:
        name_by_code = {str(row["ts_code"]): str(row["name"]) for _, row in stocks.iterrows()}

    daily = fetch_daily_market(client, daily_trade_days, fields="ts_code,trade_date,open,close")
    records_by_code: dict[str, list[dict[str, Any]]] = {}
    if not daily.empty:
        filtered = daily.loc[daily["ts_code"].isin(list(cleaned))]
        records_by_code = {
            str(code): group.sort_values("trade_date").to_dict("records")
            for code, group in filtered.groupby("ts_code")
        }

    rows: list[dict[str, Any]] = []
    next_tags: dict[str, Any] = {}
    next_states: dict[str, Any] = {}
    for code, buy_price in cleaned.items():
        records = records_by_code.get(code, [])
        if not records:
            continue
        try:
            raw_open = records[-1].get("open")
            reference_open = float(raw_open) if raw_open is not None else None
            opening_signal = fetch_opening_signal(client, code, target_api_date, config, reference_open)
        except Exception as exc:  # noqa: BLE001
            opening_signal = {
                "status": "unavailable",
                "signal": "unavailable",
                "source": "unavailable",
                "errors": [f"{type(exc).__name__}: {exc}"],
            }
        prudent_tag = transition_prudent_tag(prior_tags.get(code), opening_signal, target_api_date, trade_days, config)
        assessment, state = evaluate_risk(buy_price, records, prudent_tag, prior_states.get(code, {}), target_api_date, trade_days, config)
        closes = [float(item["close"]) for item in records]
        rows.append(
            {
                "code": code,
                "name": name_by_code.get(code, ""),
                "buy_price": buy_price,
                "close": round(closes[-1], 3),
                "pnl_pct": round((closes[-1] - buy_price) / buy_price * 100, 2),
                "signal_date": records[-1]["trade_date"],
                "opening": opening_signal,
                "prudent_tag": prudent_tag,
                **assessment,
            }
        )
        next_states[code] = state
        if prudent_tag:
            next_tags[code] = prudent_tag
        time.sleep(RISK_SLEEP_SECONDS)

    risk_actions = [row for row in rows if row["action"] != "hold"]
    holdings = [row for row in rows if row["action"] == "hold"]
    payload = artifact(
        "risk_signal",
        directory_date,
        parameters,
        "三层风控：开盘信号（5min 开盘段，参考价＝当日开盘）→ 审慎标签（3 交易日）→ 日线退出（MA5 跌破观察/减半、MA10 跌破清仓、硬止损 5%）。",
        {
            "params": {key: value for key, value in config.items() if key != "schema_version"},
            "data_sources": {row["code"]: row["opening"].get("source", "unknown") for row in rows},
            "stats": {
                "positions": len(cleaned),
                "evaluated": len(rows),
                "actions": len(risk_actions),
                "hold": len(holdings),
            },
            "risk_actions": risk_actions,
            "holdings": holdings,
        },
    )
    if dry_run:
        return {"ok": True, "dry_run": True, "artifact": "risk_signal", "date": directory_date, "document": payload}
    directory = process_dir(directory_date, create=True)
    paths = [
        write_json(directory / "risk_signal.json", payload),
        write_json(directory / config["prudent_tag"]["state_file"], {"date": target_api_date, "positions": next_tags}),
        write_json(directory / config["position_state"]["state_file"], {"date": target_api_date, "positions": next_states}),
        write_json(directory / "positions.json", cleaned),
    ]
    return {"ok": True, "artifact": "risk_signal", "date": directory_date, "paths": paths, "logical_paths": [logical_process_path(directory_date, "risk_signal.json")], "stats": payload["stats"]}


RENDER_TARGETS = {
    "candidates": ("full_market_candidate.json", "candidates.md.j2", "candidates.md"),
    "sector_heat": ("sector_heat.json", "sector_heat.md.j2", "sector_heat.md"),
    "entry_signal": ("entry_signal.json", "entry_signal.md.j2", "entry_signal.md"),
    "risk_signal": ("risk_signal.json", "risk_signal.md.j2", "risk_signal.md"),
}


def render_artifact(directory_date: str, kind: str, document: dict[str, Any] | None, dry_run: bool) -> dict[str, Any]:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    input_name, template_name, output_name = RENDER_TARGETS[kind]
    if document is None:
        document = load_process_document(directory_date, input_name)
    if not isinstance(document, dict):
        fail("document", "必须是 JSON 对象")
    if str(document.get("date")) != directory_date:
        fail("document.date", f"必须与 date 一致（{directory_date}）")
    environment = Environment(loader=FileSystemLoader(str(TEMPLATES_ROOT)), undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
    markdown = environment.get_template(template_name).render(
        data=document,
        source_path=logical_process_path(directory_date, input_name),
        report_uuid=uuid.uuid5(uuid.NAMESPACE_URL, f"pi-trader:{SYSTEM_ID}:{directory_date}:{kind}").hex,
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    logical_path = logical_process_path(directory_date, output_name)
    if dry_run:
        return {"ok": True, "dry_run": True, "artifact": kind, "date": directory_date, "logical_path": logical_path, "markdown": markdown}
    path = process_dir(directory_date, create=True) / output_name
    overwrote = path.is_file()
    path.write_text(markdown, encoding="utf-8")
    return {"ok": True, "artifact": kind, "date": directory_date, "logical_path": logical_path, "path": str(path), "overwrote": overwrote}


def tool_calculate(arguments: dict[str, Any]) -> dict[str, Any]:
    parameters = load_parameters()
    operation = arguments.get("operation")
    if operation not in OPERATIONS:
        raise ValueError(f"operation 必须是 {' / '.join(OPERATIONS)}")
    target_api_date, directory_date = normalize_date(arguments.get("date"))
    dry_run = bool(arguments.get("dry_run", False))
    raw_industries = arguments.get("industries")
    industries = None
    if raw_industries is not None:
        if not isinstance(raw_industries, list) or not all(isinstance(item, str) and item.strip() for item in raw_industries):
            fail("industries", "必须是字符串数组")
        industries = [item.strip() for item in raw_industries]
    if operation == "select_candidates":
        return op_select_candidates(target_api_date, directory_date, industries, parameters, dry_run)
    if operation == "sector_heat":
        return op_sector_heat(target_api_date, directory_date, parameters, dry_run)
    if operation == "entry_signal":
        return op_entry_signal(target_api_date, directory_date, industries, parameters, dry_run)
    positions = arguments.get("positions")
    if positions is not None and not isinstance(positions, dict):
        fail("positions", "必须是 JSON 对象（代码 → 买入价）")
    return op_risk_signal(target_api_date, directory_date, positions, parameters, dry_run)


TOOLS = [
    Tool(name="list_systems", description="列出本服务实现的交易体系。", inputSchema={"type": "object", "properties": {}}),
    Tool(
        name="get_manifest",
        description="查看热门板块回调低吸体系的运行定义、支持的操作与产物契约。",
        inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}}, "required": ["system_id"]},
    ),
    Tool(
        name="validate_parameters",
        description="校验本体系参数（selection / sector_heat / entry / risk / runtime）。",
        inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}}, "required": ["system_id"]},
    ),
    Tool(
        name="is_trading_day",
        description="判断指定日期（默认今天）是否为交易日；数据源 tushare.trade_cal（SSE），本服务自带判断，不依赖其它 MCP。",
        inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}, "date": {"type": "string"}}, "required": ["system_id"]},
    ),
    Tool(
        name="calculate",
        description="计算候选（select_candidates）、板块热度与全市场板块环境（sector_heat）、建仓信号（entry_signal）或持仓风控（risk_signal）；dry_run 只返回结果不落盘。",
        inputSchema={
            "type": "object",
            "properties": {
                "system_id": {"type": "string"},
                "operation": {"type": "string", "enum": list(OPERATIONS)},
                "date": {"type": "string"},
                "industries": {"type": "array", "items": {"type": "string"}},
                "positions": {"type": "object"},
                "dry_run": {"type": "boolean"},
            },
            "required": ["system_id", "operation", "date"],
        },
    ),
    Tool(
        name="render",
        description="把当日过程资料渲染为 Markdown（candidates / sector_heat / entry_signal / risk_signal）。",
        inputSchema={
            "type": "object",
            "properties": {
                "system_id": {"type": "string"},
                "artifact": {"type": "string", "enum": list(RENDER_TARGETS)},
                "date": {"type": "string"},
                "document": {"type": "object"},
                "dry_run": {"type": "boolean"},
            },
            "required": ["system_id", "artifact", "date"],
        },
    ),
]

server = Server("hot-sector-pullback-system")


def list_tools_result() -> list[Tool]:
    return TOOLS


def call_tool_result(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    args = arguments or {}
    try:
        if name == "list_systems":
            result = {"systems": [{"system_id": SYSTEM_ID, "name": SYSTEM_NAME, "operations": list(OPERATIONS)}]}
        elif name in {"get_manifest", "validate_parameters", "is_trading_day", "calculate", "render"} and args.get("system_id") != SYSTEM_ID:
            raise ValueError(f"当前 MCP 不支持体系：{args.get('system_id')}")
        elif name == "get_manifest":
            runtime = read_json(PARAMS_ROOT / "runtime.json")
            result = {
                "system_id": SYSTEM_ID,
                "name": SYSTEM_NAME,
                "version": SYSTEM_VERSION,
                "maturity": "观察体系",
                "system_root": str(SYSTEM_ROOT),
                "parameter_root": str(PARAMS_ROOT),
                "template_root": str(TEMPLATES_ROOT),
                "operations": list(OPERATIONS),
                "computes_facts": True,
                "process_output": {
                    "logical_root": f"{logical_root('process_root')}/{{date}}/{SYSTEM_NAME}",
                    "physical_root": "knowledge",
                    "artifacts": [
                        "full_market_candidate.json",
                        "hottest_industry_candidate.json",
                        "sector_environment.json",
                        "sector_heat.json",
                        "entry_signal.json",
                        "risk_signal.json",
                        "positions.json",
                        "state.json",
                        "prudent_tags.json",
                    ],
                },
                "plan_output": f"{logical_root('plan_root')}/{{date}}/{SYSTEM_NAME}_交易计划.md",
                "review_output": f"{logical_root('review_root')}/{{date}}/{SYSTEM_NAME}_复盘.md",
                "fact_sources": {
                    "daily": "tushare pro_api daily（全市场按 trade_date）",
                    "index": f"tushare index_daily（{BENCHMARK_INDEX}）",
                    "minutes": "tushare stk_mins（5min 开盘段）+ params/risk.json fallback_sources 降级",
                },
                "boundaries": {
                    "computes_facts": True,
                    "queries_account": False,
                    "real_order": "forbidden",
                    "modifies_parameters": False,
                    "writes_plan": False,
                    "cross_system_reads": "none",
                },
            }
        elif name == "validate_parameters":
            parameters = load_parameters()
            result = {"system_id": SYSTEM_ID, **validate_parameters(parameters), **parameter_metadata(parameters)}
        elif name == "is_trading_day":
            api_date, directory_date = normalize_date(args.get("date"))
            calendar = fetch_trade_calendar(get_client(), api_date)
            result = {
                "ok": True,
                "system_id": SYSTEM_ID,
                "date": directory_date,
                "is_open": calendar["is_open"],
                "pretrade_date": calendar["pretrade_date"],
                "source": "tushare.trade_cal/SSE",
            }
        elif name == "calculate":
            result = tool_calculate(args)
        elif name == "render":
            artifact = args.get("artifact")
            if artifact not in RENDER_TARGETS:
                raise ValueError(f"不支持的渲染目标：{artifact}")
            _, directory_date = normalize_date(args.get("date"))
            document = args.get("document")
            if document is not None and not isinstance(document, dict):
                fail("document", "必须是 JSON 对象")
            result = render_artifact(directory_date, artifact, document, bool(args.get("dry_run", False)))
        else:
            raise ValueError(f"未知工具：{name}")
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": str(exc)}
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]


async def list_tools_legacy() -> list[Tool]:
    return list_tools_result()


async def call_tool_legacy(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    return call_tool_result(name, arguments)


if hasattr(server, "list_tools") and hasattr(server, "call_tool"):
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return list_tools_result()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        return call_tool_result(name, arguments)
else:
    async def list_tools(_context: Any, _params: Any) -> Any:
        from mcp.types import ListToolsResult
        return ListToolsResult(tools=TOOLS)

    async def call_tool(_context: Any, params: Any) -> Any:
        from mcp.types import CallToolResult
        content = call_tool_result(params.name, params.arguments or {})
        return CallToolResult(content=content)

    server = Server("hot-sector-pullback-system", on_list_tools=list_tools, on_call_tool=call_tool)


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

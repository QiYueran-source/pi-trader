"""热门板块回调低吸体系的共享配置与过程资料路径。"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(os.environ.get("HERMES_REPO_ROOT", "/hermes-trader")).expanduser()
if not REPO_ROOT.exists():
    REPO_ROOT = Path(__file__).resolve().parents[5]

SYSTEM_DIR = REPO_ROOT / "knowledge/交易/交易体系/热门板块回调低吸体系"
PARAMS_DIR = SYSTEM_DIR / "params"

TOP_LEVEL_FIELDS = {
    "selection": {
        "limit_up_window_days",
        "min_limit_up_count",
        "max_limit_up_count",
        "pullback_ma_period",
        "rebound_window_days",
    },
    "sector_heat": {
        "limit_up_window_days",
        "trend_ma_periods",
        "volume_ratio_window_days",
        "max_consecutive_limit_up_days",
    },
    "entry": {
        "volume_multiplier",
        "volume_average_period",
        "breakout_ma_period",
    },
    "risk": {"opening_signal", "prudent_tag", "position_state", "exit_rules"},
    "runtime": {"process_root", "directory_date_format", "trading_day_only"},
}


def fail(field: str, message: str) -> None:
    raise ValueError(f"配置字段 {field}: {message}")


def require_exact_fields(value: dict, fields: set[str], section: str) -> None:
    missing = fields - value.keys()
    unexpected = value.keys() - fields
    if missing:
        fail(section, f"缺少字段 {', '.join(sorted(missing))}")
    if unexpected:
        fail(section, f"存在未知字段 {', '.join(sorted(unexpected))}")


def require_int(value: object, field: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        fail(field, f"必须是不小于 {minimum} 的整数")
    return value


def require_ratio(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < 1:
        fail(field, "必须在 (0, 1) 内")
    return float(value)


def require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(field, "必须是非空字符串")
    return value


def load_config(name: str) -> dict:
    if name not in TOP_LEVEL_FIELDS:
        raise ValueError(f"不允许加载的配置: {name}")

    path = PARAMS_DIR / f"{name}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"配置文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"配置文件 JSON 无效 {path}: {exc.msg}") from exc

    if not isinstance(value, dict):
        fail(name, "必须是 JSON 对象")
    require_exact_fields(value, TOP_LEVEL_FIELDS[name], name)
    return value


def load_selection_config() -> dict:
    config = load_config("selection")
    for field in config:
        require_int(config[field], f"selection.{field}")
    if config["min_limit_up_count"] > config["max_limit_up_count"]:
        fail("selection.min_limit_up_count", "不能大于 max_limit_up_count")
    return config


def load_sector_heat_config() -> dict:
    config = load_config("sector_heat")
    require_int(config["limit_up_window_days"], "sector_heat.limit_up_window_days")
    require_int(config["volume_ratio_window_days"], "sector_heat.volume_ratio_window_days")
    require_int(config["max_consecutive_limit_up_days"], "sector_heat.max_consecutive_limit_up_days")

    periods = config["trend_ma_periods"]
    if not isinstance(periods, list) or len(periods) != 2:
        fail("sector_heat.trend_ma_periods", "必须是恰含两个正整数的数组")
    short_period, long_period = (
        require_int(periods[0], "sector_heat.trend_ma_periods[0]"),
        require_int(periods[1], "sector_heat.trend_ma_periods[1]"),
    )
    if short_period >= long_period:
        fail("sector_heat.trend_ma_periods", "必须严格递增")
    return config


def load_entry_config() -> dict:
    config = load_config("entry")
    multiplier = config["volume_multiplier"]
    if isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)) or multiplier <= 0:
        fail("entry.volume_multiplier", "必须是大于 0 的数值")
    require_int(config["volume_average_period"], "entry.volume_average_period")
    require_int(config["breakout_ma_period"], "entry.breakout_ma_period")
    return config


def load_risk_config() -> dict:
    config = load_config("risk")
    opening = config["opening_signal"]
    tags = config["prudent_tag"]
    state = config["position_state"]
    exits = config["exit_rules"]

    require_exact_fields(opening, {"bar_frequency", "start_time", "end_time", "reference_price", "rapid_drop_pct", "fallback_sources"}, "risk.opening_signal")
    require_exact_fields(tags, {"state_file", "valid_trading_days", "snapshot_lookback_trading_days", "refresh_on_bearish_signal"}, "risk.prudent_tag")
    require_exact_fields(state, {"state_file"}, "risk.position_state")
    require_exact_fields(exits, {"hard_stop_loss_pct", "ma5", "ma10"}, "risk.exit_rules")

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
    if any(not isinstance(item, str) or item not in {"official", "promax"} for item in sources):
        fail("risk.opening_signal.fallback_sources", "仅支持 official / promax")
    if len(set(sources)) != len(sources):
        fail("risk.opening_signal.fallback_sources", "不得重复")
    require_string(tags["state_file"], "risk.prudent_tag.state_file")
    require_int(tags["valid_trading_days"], "risk.prudent_tag.valid_trading_days")
    require_int(tags["snapshot_lookback_trading_days"], "risk.prudent_tag.snapshot_lookback_trading_days")
    if not isinstance(tags["refresh_on_bearish_signal"], bool):
        fail("risk.prudent_tag.refresh_on_bearish_signal", "必须为布尔值")
    require_string(state["state_file"], "risk.position_state.state_file")
    require_ratio(exits["hard_stop_loss_pct"], "risk.exit_rules.hard_stop_loss_pct")

    ma5 = exits["ma5"]
    require_exact_fields(ma5, {"period", "break_action", "normal_observation_days", "prudent_observation_days", "reduce_ratio"}, "risk.exit_rules.ma5")
    require_int(ma5["period"], "risk.exit_rules.ma5.period")
    require_int(ma5["normal_observation_days"], "risk.exit_rules.ma5.normal_observation_days", 0)
    require_int(ma5["prudent_observation_days"], "risk.exit_rules.ma5.prudent_observation_days", 0)
    require_ratio(ma5["reduce_ratio"], "risk.exit_rules.ma5.reduce_ratio")
    if ma5["break_action"] != "observe_or_reduce":
        fail("risk.exit_rules.ma5.break_action", "必须为 observe_or_reduce")

    ma10 = exits["ma10"]
    require_exact_fields(ma10, {"period", "break_action", "execution_timing"}, "risk.exit_rules.ma10")
    require_int(ma10["period"], "risk.exit_rules.ma10.period")
    if ma10["break_action"] != "liquidate":
        fail("risk.exit_rules.ma10.break_action", "必须为 liquidate")
    if ma10["execution_timing"] != "next_open":
        fail("risk.exit_rules.ma10.execution_timing", "必须为 next_open")
    return config


def load_runtime_config() -> dict:
    config = load_config("runtime")
    require_string(config["process_root"], "runtime.process_root")
    if config["directory_date_format"] != "%Y-%m-%d":
        fail("runtime.directory_date_format", "必须为 %Y-%m-%d")
    if not isinstance(config["trading_day_only"], bool):
        fail("runtime.trading_day_only", "必须为布尔值")
    return config


def normalize_date(value: str | None) -> tuple[str, str]:
    if value is None:
        parsed = date.today()
    elif isinstance(value, str):
        format_string = "%Y-%m-%d" if "-" in value else "%Y%m%d"
        try:
            parsed = datetime.strptime(value, format_string).date()
        except ValueError as exc:
            raise ValueError(f"date 必须为 YYYYMMDD 或 YYYY-MM-DD: {value}") from exc
    else:
        raise ValueError("date 必须为 YYYYMMDD 或 YYYY-MM-DD")

    return parsed.strftime("%Y%m%d"), parsed.strftime(load_runtime_config()["directory_date_format"])


def process_dir(target_date: str | None) -> Path:
    _, directory_date = normalize_date(target_date)
    return REPO_ROOT / load_runtime_config()["process_root"] / directory_date / SYSTEM_DIR.name


def previous_trade_dates(run_date: str, trade_dates: list[str], back_n: int) -> list[str]:
    if back_n < 0:
        raise ValueError("back_n 必须不小于 0")

    run_api_date, _ = normalize_date(run_date)
    normalized_dates = {normalize_date(str(item))[0] for item in trade_dates}
    earlier_dates = sorted(day for day in normalized_dates if day < run_api_date)
    return list(reversed(earlier_dates[-back_n:]))


def latest_snapshot(run_date: str, filename: str, trade_dates: list[str], back_n: int) -> tuple[Path, str] | None:
    for trade_date in previous_trade_dates(run_date, trade_dates, back_n):
        candidate = process_dir(trade_date) / filename
        if candidate.is_file():
            return candidate, trade_date
    return None
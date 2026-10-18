"""参数读取、校验与元数据。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from functions.paths import PARAMETER_FILES, PARAMS_ROOT, SYSTEM_VERSION, read_json

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
    require_exact_fields(entry, {"schema_version", "volume_multiplier", "volume_average_period", "breakout_ma_period", "benchmark_tiers"}, "entry")
    tiers = require_exact_fields(entry["benchmark_tiers"], {"stabilize_above_pct", "extreme_weak_at_or_below_pct", "note"}, "entry.benchmark_tiers")
    stabilize = tiers["stabilize_above_pct"]
    extreme_weak = tiers["extreme_weak_at_or_below_pct"]
    for key, value in (("stabilize_above_pct", stabilize), ("extreme_weak_at_or_below_pct", extreme_weak)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            fail(f"entry.benchmark_tiers.{key}", "必须是数值（百分比）")
    if not float(stabilize) > float(extreme_weak):
        fail("entry.benchmark_tiers", "stabilize_above_pct 必须大于 extreme_weak_at_or_below_pct")
    require_string(tiers["note"], "entry.benchmark_tiers.note")
    multiplier = entry["volume_multiplier"]
    if isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)) or multiplier <= 0:
        fail("entry.volume_multiplier", "必须是大于 0 的数值")
    require_integer(entry["volume_average_period"], "entry.volume_average_period")
    require_integer(entry["breakout_ma_period"], "entry.breakout_ma_period")

    risk = parameters["risk"]
    require_exact_fields(risk, {"schema_version", "opening_signal", "prudent_tag", "position_state", "exit_rules"}, "risk")
    opening = require_exact_fields(
        risk["opening_signal"],
        {"bar_frequency", "start_time", "end_time", "reference_price", "rapid_drop_pct", "note"},
        "risk.opening_signal",
    )
    if opening["bar_frequency"] != "5min":
        fail("risk.opening_signal.bar_frequency", "必须为 5min")
    if opening["reference_price"] != "session_open":
        fail("risk.opening_signal.reference_price", "必须为 session_open")
    require_string(opening["start_time"], "risk.opening_signal.start_time")
    require_string(opening["end_time"], "risk.opening_signal.end_time")
    require_ratio(opening["rapid_drop_pct"], "risk.opening_signal.rapid_drop_pct")

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
        {
            "schema_version",
            "process_root",
            "plan_root",
            "review_root",
            "directory_date_format",
            "history_lookback_calendar_days",
            "note",
        },
        "runtime",
    )
    require_string(runtime["process_root"], "runtime.process_root")
    for field in ("plan_root", "review_root"):
        require_string(runtime[field], f"runtime.{field}")
    if runtime["directory_date_format"] != "%Y-%m-%d":
        fail("runtime.directory_date_format", "必须为 %Y-%m-%d")
    require_integer(runtime["history_lookback_calendar_days"], "runtime.history_lookback_calendar_days")
    return {"valid": True, "files": list(PARAMETER_FILES)}

def parameter_metadata(parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    encoded = json.dumps(parameters, ensure_ascii=False, sort_keys=True).encode()
    return {
        "parameter_version": SYSTEM_VERSION,
        "parameter_hash": hashlib.sha256(encoded).hexdigest(),
        "schema_versions": {name: parameters[name]["schema_version"] for name in PARAMETER_FILES},
    }

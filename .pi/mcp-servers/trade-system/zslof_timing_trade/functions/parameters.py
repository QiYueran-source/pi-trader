"""参数读取、校验与元数据。"""

from __future__ import annotations

import json
import hashlib
from typing import Any

from functions.paths import PARAMETER_FILES, PARAMS_ROOT, SYSTEM_VERSION, read_json

def fail(field: str, message: str) -> None:
    raise ValueError(f"配置字段 {field}: {message}")

def require_fields(value: Any, expected: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(field, "必须是 JSON 对象")
    missing = sorted(item for item in expected if item not in value)
    if missing:
        fail(field, f"缺少字段：{', '.join(missing)}")
    return value

def require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(field, "必须是非空字符串")
    return value

def require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        fail(field, "必须是布尔值")
    return value

def require_integer(value: Any, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        fail(field, f"必须是不小于 {minimum} 的整数")
    return value

def require_ratio(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        fail(field, "必须是非负数值")
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
            raise ValueError(f"{name}.schema_version 必须是不小于 1 的整数")

    instrument = parameters["instrument"]
    require_fields(instrument, {"schema_version", "instrument", "account", "commission"}, "instrument")
    require_fields(instrument["instrument"], {"instrument_id", "ts_code", "name"}, "instrument.instrument")
    require_fields(instrument["account"], {"account_id", "broker_name"}, "instrument.account")
    require_fields(instrument["commission"], {"commission_ratio", "minimum_commission_exempt", "description"}, "instrument.commission")
    require_string(instrument["instrument"]["instrument_id"], "instrument.instrument.instrument_id")
    require_string(instrument["instrument"]["ts_code"], "instrument.instrument.ts_code")
    require_string(instrument["instrument"]["name"], "instrument.instrument.name")
    require_string(instrument["account"]["account_id"], "instrument.account.account_id")
    require_string(instrument["account"]["broker_name"], "instrument.account.broker_name")
    require_ratio(instrument["commission"]["commission_ratio"], "instrument.commission.commission_ratio")
    require_bool(instrument["commission"]["minimum_commission_exempt"], "instrument.commission.minimum_commission_exempt")
    require_string(instrument["commission"]["description"], "instrument.commission.description")

    timing = parameters["timing"]
    require_fields(timing, {"schema_version", "confirmation_days", "stop_loss_enabled", "chase_enabled", "order_amount", "signal_timing", "execution_timing"}, "timing")
    require_integer(timing["confirmation_days"], "timing.confirmation_days", 1)
    require_bool(timing["stop_loss_enabled"], "timing.stop_loss_enabled")
    require_bool(timing["chase_enabled"], "timing.chase_enabled")
    require_integer(timing["order_amount"], "timing.order_amount", 1)
    if timing["signal_timing"] != "close_confirmed" or timing["execution_timing"] != "next_open":
        fail("timing", "必须使用收盘确认、次日开盘执行")

    runtime = parameters["runtime"]
    require_fields(runtime, {"schema_version", "process_root", "directory_date_format", "history_lookback_calendar_days", "strategy_state_file", "signal_facts_file", "report_file", "state_lookup", "allow_future_state", "state_anchor_date"}, "runtime")
    require_string(runtime["process_root"], "runtime.process_root")
    if runtime["directory_date_format"] != "%Y-%m-%d":
        fail("runtime.directory_date_format", "必须为 %Y-%m-%d")
    require_integer(runtime["history_lookback_calendar_days"], "runtime.history_lookback_calendar_days", 1)
    for field in ("strategy_state_file", "signal_facts_file", "report_file"):
        require_string(runtime[field], f"runtime.{field}")
    if runtime["state_lookup"] != "latest_prior_process_date":
        fail("runtime.state_lookup", "必须为 latest_prior_process_date")
    if require_bool(runtime["allow_future_state"], "runtime.allow_future_state"):
        fail("runtime.allow_future_state", "必须为 false")
    require_string(runtime["state_anchor_date"], "runtime.state_anchor_date")
    return {"valid": True, "files": list(PARAMETER_FILES)}

def parameter_metadata(parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    encoded = json.dumps(parameters, ensure_ascii=False, sort_keys=True).encode()
    return {
        "parameter_version": SYSTEM_VERSION,
        "parameter_hash": hashlib.sha256(encoded).hexdigest(),
        "schema_versions": {name: parameters[name]["schema_version"] for name in PARAMETER_FILES},
    }

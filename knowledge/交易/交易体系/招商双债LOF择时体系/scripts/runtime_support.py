"""招商双债 LOF 择时体系的静态参数与过程资料支持。"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("HERMES_REPO_ROOT", "/hermes-trader")).expanduser()
if not REPO_ROOT.exists():
    REPO_ROOT = Path(__file__).resolve().parents[5]

SYSTEM_DIR = REPO_ROOT / "knowledge/交易/交易体系/招商双债LOF择时体系"
PARAMS_DIR = SYSTEM_DIR / "params"
SYSTEM_ID = "zslof_timing_trade"
SYSTEM_NAME = "招商双债LOF择时体系"


def fail(field: str, message: str) -> None:
    raise ValueError(f"配置字段 {field}: {message}")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 无效 {path}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON 必须是对象: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as temporary_file:
        temporary_file.write(content)
        temporary_path = Path(temporary_file.name)
    os.replace(temporary_path, path)


def require_fields(value: dict[str, Any], expected: set[str], field: str) -> None:
    missing = expected - value.keys()
    unexpected = value.keys() - expected
    if missing:
        fail(field, f"缺少字段 {', '.join(sorted(missing))}")
    if unexpected:
        fail(field, f"存在未知字段 {', '.join(sorted(unexpected))}")


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
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
        fail(field, "必须在 [0, 1] 内")
    return float(value)


def load_parameters() -> dict[str, dict[str, Any]]:
    values = {
        name: read_json(PARAMS_DIR / f"{name}.json")
        for name in ("instrument", "timing", "runtime")
    }
    for name, value in values.items():
        if value.get("schema_version") != 1:
            fail(f"{name}.schema_version", "当前仅支持版本 1")
    validate_parameters(values)
    return values


def validate_parameters(values: dict[str, dict[str, Any]]) -> None:
    instrument = values["instrument"]
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

    timing = values["timing"]
    require_fields(timing, {"schema_version", "confirmation_days", "stop_loss_enabled", "chase_enabled", "order_amount", "signal_timing", "execution_timing", "counter_semantics"}, "timing")
    require_integer(timing["confirmation_days"], "timing.confirmation_days", 1)
    require_bool(timing["stop_loss_enabled"], "timing.stop_loss_enabled")
    require_bool(timing["chase_enabled"], "timing.chase_enabled")
    require_integer(timing["order_amount"], "timing.order_amount", 1)
    if timing["signal_timing"] != "close_confirmed" or timing["execution_timing"] != "next_open":
        fail("timing", "必须使用收盘确认、次日开盘执行")
    require_fields(timing["counter_semantics"], {"no_high", "no_low", "stop_loss_priority"}, "timing.counter_semantics")
    require_bool(timing["counter_semantics"]["stop_loss_priority"], "timing.counter_semantics.stop_loss_priority")

    runtime = values["runtime"]
    require_fields(runtime, {"schema_version", "process_root", "directory_date_format", "trading_day_only", "history_lookback_calendar_days", "strategy_state_file", "signal_facts_file", "report_file", "state_lookup", "allow_future_state"}, "runtime")
    require_string(runtime["process_root"], "runtime.process_root")
    if runtime["directory_date_format"] != "%Y-%m-%d":
        fail("runtime.directory_date_format", "必须为 %Y-%m-%d")
    require_bool(runtime["trading_day_only"], "runtime.trading_day_only")
    require_integer(runtime["history_lookback_calendar_days"], "runtime.history_lookback_calendar_days", 1)
    for field in ("strategy_state_file", "signal_facts_file", "report_file"):
        require_string(runtime[field], f"runtime.{field}")
    if runtime["state_lookup"] != "latest_prior_process_date":
        fail("runtime.state_lookup", "必须为 latest_prior_process_date")
    if require_bool(runtime["allow_future_state"], "runtime.allow_future_state"):
        fail("runtime.allow_future_state", "必须为 false")


def normalize_date(value: str | None) -> tuple[str, str]:
    if value is None:
        parsed = date.today()
    elif isinstance(value, str):
        pattern = "%Y-%m-%d" if "-" in value else "%Y%m%d"
        try:
            parsed = datetime.strptime(value, pattern).date()
        except ValueError as exc:
            raise ValueError(f"date 必须为 YYYY-MM-DD 或 YYYYMMDD: {value}") from exc
    else:
        raise ValueError("date 必须为 YYYY-MM-DD 或 YYYYMMDD")
    return parsed.strftime("%Y%m%d"), parsed.strftime("%Y-%m-%d")


def process_dir(value: str | None) -> Path:
    _, directory_date = normalize_date(value)
    runtime = load_parameters()["runtime"]
    return REPO_ROOT / runtime["process_root"] / directory_date / SYSTEM_NAME


def latest_prior_strategy_state(value: str) -> Path | None:
    _, target_date = normalize_date(value)
    runtime = load_parameters()["runtime"]
    root = REPO_ROOT / runtime["process_root"]
    if not root.is_dir():
        return None
    for directory in sorted((item for item in root.iterdir() if item.is_dir() and item.name < target_date), key=lambda item: item.name, reverse=True):
        candidate = directory / SYSTEM_NAME / runtime["strategy_state_file"]
        if candidate.is_file():
            return candidate
    return None
"""红利科创 ETF 双网格体系的参数校验与日期化过程资料支持。"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("PI_PROJECT_DIR", "/pi-trader")).expanduser()
if not REPO_ROOT.exists():
    REPO_ROOT = Path(__file__).resolve().parents[5]

SYSTEM_DIR = REPO_ROOT / "knowledge/交易/交易体系/红利科创ETF双网格体系"
PARAMS_DIR = SYSTEM_DIR / "params"
SYSTEM_ID = "div_etf_grid_trade"
SYSTEM_NAME = "红利科创ETF双网格体系"
LEGACY_SYSTEM_NAMES = ("红利ETF网格",)

PARAMETER_FILES = {
    "instruments",
    "grid",
    "risk",
    "runtime",
    "sector_classification",
    "state_machine",
}


def fail(field: str, message: str) -> None:
    raise ValueError(f"配置字段 {field}: {message}")


def require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(field, "必须是 JSON 对象")
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


def require_ratio(value: Any, field: str, minimum: float = 0.0, maximum: float = 1.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail(field, "必须是数值")
    ratio = float(value)
    if not minimum <= ratio <= maximum:
        fail(field, f"必须在 [{minimum}, {maximum}] 内")
    return ratio


def require_fields(value: dict[str, Any], expected: set[str], field: str) -> None:
    missing = expected - value.keys()
    unexpected = value.keys() - expected
    if missing:
        fail(field, f"缺少字段 {', '.join(sorted(missing))}")
    if unexpected:
        fail(field, f"存在未知字段 {', '.join(sorted(unexpected))}")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 无效 {path}: {exc.msg}") from exc
    return require_object(value, str(path))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as temporary_file:
        temporary_file.write(content)
        temporary_path = Path(temporary_file.name)
    os.replace(temporary_path, path)


def load_parameter(name: str) -> dict[str, Any]:
    if name not in PARAMETER_FILES:
        raise ValueError(f"不允许加载的参数文件: {name}")
    value = read_json(PARAMS_DIR / f"{name}.json")
    if value.get("schema_version") != 1:
        fail(f"{name}.schema_version", "当前仅支持版本 1")
    return value


def load_parameters() -> dict[str, dict[str, Any]]:
    parameters = {name: load_parameter(name) for name in sorted(PARAMETER_FILES)}
    validate_parameters(parameters)
    return parameters


def validate_parameters(parameters: dict[str, dict[str, Any]]) -> None:
    instruments = parameters["instruments"]
    require_fields(
        instruments,
        {"schema_version", "account", "commission", "instruments", "data_sources"},
        "instruments",
    )
    account = require_object(instruments["account"], "instruments.account")
    require_fields(account, {"account_id", "broker_name", "total_capital_amount", "currency"}, "instruments.account")
    require_string(account["account_id"], "instruments.account.account_id")
    require_string(account["broker_name"], "instruments.account.broker_name")
    require_integer(account["total_capital_amount"], "instruments.account.total_capital_amount", 1)
    require_string(account["currency"], "instruments.account.currency")

    commission = require_object(instruments["commission"], "instruments.commission")
    require_fields(commission, {"etf_commission_ratio", "etf_no_minimum_commission", "stamp_duty_sell_ratio", "transfer_fee_ratio"}, "instruments.commission")
    for field in ("etf_commission_ratio", "stamp_duty_sell_ratio", "transfer_fee_ratio"):
        require_ratio(commission[field], f"instruments.commission.{field}")
    require_bool(commission["etf_no_minimum_commission"], "instruments.commission.etf_no_minimum_commission")

    configured_instruments = require_object(instruments["instruments"], "instruments.instruments")
    if set(configured_instruments) != {"dividend", "growth"}:
        fail("instruments.instruments", "必须且只能包含 dividend 与 growth")
    for instrument_id, instrument in configured_instruments.items():
        require_fields(require_object(instrument, f"instruments.instruments.{instrument_id}"), {"ts_code", "name", "lot_size_shares"}, f"instruments.instruments.{instrument_id}")
        require_string(instrument["ts_code"], f"instruments.instruments.{instrument_id}.ts_code")
        require_string(instrument["name"], f"instruments.instruments.{instrument_id}.name")
        require_integer(instrument["lot_size_shares"], f"instruments.instruments.{instrument_id}.lot_size_shares", 1)

    grid = parameters["grid"]
    require_fields(grid, {"schema_version", "calibration", "step_formula", "portfolio", "grids"}, "grid")
    calibration = require_object(grid["calibration"], "grid.calibration")
    require_fields(calibration, {"schedule", "fetch_lookback_calendar_days", "step_window_trading_days", "minimum_step_ratio"}, "grid.calibration")
    require_string(calibration["schedule"], "grid.calibration.schedule")
    require_integer(calibration["fetch_lookback_calendar_days"], "grid.calibration.fetch_lookback_calendar_days", 1)
    require_integer(calibration["step_window_trading_days"], "grid.calibration.step_window_trading_days", 1)
    require_ratio(calibration["minimum_step_ratio"], "grid.calibration.minimum_step_ratio")
    if calibration["step_window_trading_days"] > calibration["fetch_lookback_calendar_days"]:
        fail("grid.calibration.step_window_trading_days", "不能大于 fetch_lookback_calendar_days")

    grids = require_object(grid["grids"], "grid.grids")
    if set(grids) != set(configured_instruments):
        fail("grid.grids", "必须与 instruments.instruments 完全对应")
    for instrument_id, spec in grids.items():
        require_fields(require_object(spec, f"grid.grids.{instrument_id}"), {"drawdown_coefficient", "buy_shares", "sell_shares", "buy_confirmation_rebound_ratio", "sell_confirmation_pullback_ratio", "step_window_trading_days"}, f"grid.grids.{instrument_id}")
        require_ratio(spec["drawdown_coefficient"], f"grid.grids.{instrument_id}.drawdown_coefficient")
        require_integer(spec["buy_shares"], f"grid.grids.{instrument_id}.buy_shares", 1)
        require_integer(spec["sell_shares"], f"grid.grids.{instrument_id}.sell_shares", 1)
        require_ratio(spec["buy_confirmation_rebound_ratio"], f"grid.grids.{instrument_id}.buy_confirmation_rebound_ratio")
        require_ratio(spec["sell_confirmation_pullback_ratio"], f"grid.grids.{instrument_id}.sell_confirmation_pullback_ratio")
        if "step_window_trading_days" in spec:
            require_integer(spec["step_window_trading_days"], f"grid.grids.{instrument_id}.step_window_trading_days", 1)
            if spec["step_window_trading_days"] > calibration["fetch_lookback_calendar_days"]:
                fail(f"grid.grids.{instrument_id}.step_window_trading_days", "不能大于 fetch_lookback_calendar_days")

    runtime = parameters["runtime"]
    require_fields(runtime, {"schema_version", "process_root", "directory_date_format", "trading_day_only", "state_snapshot"}, "runtime")
    require_string(runtime["process_root"], "runtime.process_root")
    if runtime["directory_date_format"] != "%Y-%m-%d":
        fail("runtime.directory_date_format", "必须为 %Y-%m-%d")
    require_bool(runtime["trading_day_only"], "runtime.trading_day_only")
    snapshot = require_object(runtime["state_snapshot"], "runtime.state_snapshot")
    require_fields(snapshot, {"file_name", "lookup", "allow_same_day_read", "allow_future_read"}, "runtime.state_snapshot")
    if snapshot["file_name"] != "state_after.json" or snapshot["lookup"] != "latest_prior_trading_day":
        fail("runtime.state_snapshot", "必须使用前序交易日 state_after.json")
    require_bool(snapshot["allow_same_day_read"], "runtime.state_snapshot.allow_same_day_read")
    if require_bool(snapshot["allow_future_read"], "runtime.state_snapshot.allow_future_read"):
        fail("runtime.state_snapshot.allow_future_read", "必须为 false")

    sector_classification = parameters["sector_classification"]
    require_fields(sector_classification, {"schema_version", "technology_industry_keywords"}, "sector_classification")
    keywords = sector_classification["technology_industry_keywords"]
    if not isinstance(keywords, list) or not keywords or any(not isinstance(keyword, str) or not keyword.strip() for keyword in keywords):
        fail("sector_classification.technology_industry_keywords", "必须是非空字符串数组")

    state_machine = parameters["state_machine"]
    require_fields(state_machine, {"schema_version", "initial_state", "states", "allowed_transitions", "transition_policy"}, "state_machine")
    states = require_object(state_machine["states"], "state_machine.states")
    if set(states) != {"normal", "bull", "bear"}:
        fail("state_machine.states", "必须且只能包含 normal、bull、bear")
    if state_machine["initial_state"] not in states:
        fail("state_machine.initial_state", "必须是有效状态")
    transitions = require_object(state_machine["allowed_transitions"], "state_machine.allowed_transitions")
    if set(transitions) != set(states):
        fail("state_machine.allowed_transitions", "必须覆盖所有状态")
    for source, targets in transitions.items():
        if not isinstance(targets, list) or any(target not in states for target in targets):
            fail(f"state_machine.allowed_transitions.{source}", "必须是有效状态列表")


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
    runtime = load_parameter("runtime")
    return REPO_ROOT / runtime["process_root"] / directory_date / SYSTEM_NAME


def artifact_path(value: str | None, filename: str) -> Path:
    return process_dir(value) / filename


def latest_prior_artifact(value: str, filename: str) -> Path | None:
    _, target_date = normalize_date(value)
    runtime = load_parameter("runtime")
    root = REPO_ROOT / runtime["process_root"]
    if not root.is_dir():
        return None
    candidates = sorted(
        (directory for directory in root.iterdir() if directory.is_dir() and directory.name < target_date),
        key=lambda directory: directory.name,
        reverse=True,
    )
    for directory in candidates:
        candidate_names = (SYSTEM_NAME, *LEGACY_SYSTEM_NAMES)
        for system_name in candidate_names:
            candidate = directory / system_name / filename
            if candidate.is_file():
                return candidate
    return None


def load_prior_state(value: str) -> dict[str, Any]:
    state_machine = load_parameter("state_machine")
    path = latest_prior_artifact(value, "state_after.json")
    if path is None:
        return {
            "date": None,
            "state": state_machine["initial_state"],
            "transition": None,
            "source": "initial_state",
        }
    state = read_json(path)
    if state.get("state") not in state_machine["states"]:
        raise ValueError(f"前序状态无效: {path}")
    return state
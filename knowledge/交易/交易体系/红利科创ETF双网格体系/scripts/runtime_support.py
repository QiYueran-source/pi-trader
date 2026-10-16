"""红利科创 ETF 双网格体系的参数校验与日期化过程资料支持。

依赖引导：/opt/venv 由 root 持有，脚本依赖如需额外安装，落在用户级 site-packages
（`~/.local/lib/python3.12/site-packages`），此处显式加入 sys.path。
"""

from __future__ import annotations

import json
import os
import site
import sys
import tempfile

site.addsitedir(site.getusersitepackages())
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
    "regulator",
}

# Tushare 密钥与本项目 MCP 服务共用同一个 .env，不在脚本内复制密钥
TUSHARE_ENV_FILE = REPO_ROOT / ".pi/mcp-servers/tushare/.env"


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
    version = value.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        fail(f"{name}.schema_version", "必须为不小于 1 的整数")
    return value


def tushare_client() -> Any:
    """按项目 MCP 服务的同一 .env 取得 Tushare 客户端。"""
    if TUSHARE_ENV_FILE.is_file():
        for line in TUSHARE_ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置（检查 .pi/mcp-servers/tushare/.env）")
    import tushare as ts_mod
    ts_mod.set_token(token)
    return ts_mod.pro_api()


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
    require_fields(grid, {"schema_version", "effective_from", "version", "note", "portfolio", "confirmation", "ladder", "calibration"}, "grid")
    portfolio = require_object(grid["portfolio"], "grid.portfolio")
    require_fields(portfolio, {"shared_capital_pool", "nominal_pool_amount"}, "grid.portfolio")
    require_bool(portfolio["shared_capital_pool"], "grid.portfolio.shared_capital_pool")
    require_integer(portfolio["nominal_pool_amount"], "grid.portfolio.nominal_pool_amount", 1)
    confirmation = require_object(grid["confirmation"], "grid.confirmation")
    require_fields(confirmation, {"buy_confirmation_rebound_ratio", "sell_confirmation_pullback_ratio"}, "grid.confirmation")
    for field in ("buy_confirmation_rebound_ratio", "sell_confirmation_pullback_ratio"):
        require_ratio(confirmation[field], f"grid.confirmation.{field}")
    ladder = require_object(grid["ladder"], "grid.ladder")
    require_fields(ladder, {"owner", "anchor", "note"}, "grid.ladder")
    if ladder["owner"] != "broker_software":
        fail("grid.ladder.owner", "v4 起档位价格由券商软件计算")
    calibration = require_object(grid["calibration"], "grid.calibration")
    require_fields(calibration, {"schedule", "note"}, "grid.calibration")
    require_string(calibration["schedule"], "grid.calibration.schedule")

    runtime = parameters["runtime"]
    require_fields(runtime, {"schema_version", "process_root", "directory_date_format", "trading_day_only", "state_snapshot"}, "runtime")
    require_string(runtime["process_root"], "runtime.process_root")
    if runtime["directory_date_format"] != "%Y-%m-%d":
        fail("runtime.directory_date_format", "必须为 %Y-%m-%d")
    require_bool(runtime["trading_day_only"], "runtime.trading_day_only")
    if runtime.get("state_snapshot") is not None:
        snapshot = require_object(runtime["state_snapshot"], "runtime.state_snapshot")
        require_bool(snapshot["allow_future_read"], "runtime.state_snapshot.allow_future_read")
        if snapshot["allow_future_read"]:
            fail("runtime.state_snapshot.allow_future_read", "必须为 false")

    sector_classification = parameters["sector_classification"]
    require_fields(sector_classification, {"schema_version", "technology_industry_keywords"}, "sector_classification")
    keywords = sector_classification["technology_industry_keywords"]
    if not isinstance(keywords, list) or not keywords or any(not isinstance(keyword, str) or not keyword.strip() for keyword in keywords):
        fail("sector_classification.technology_industry_keywords", "必须是非空字符串数组")

    regulator = parameters["regulator"]
    require_fields(
        regulator,
        {"schema_version", "version", "effective_from", "mode", "positioning", "normal_state", "execution", "capital_guard", "defense_levels", "signals", "approval", "reserve_shares", "policy"},
        "regulator",
    )
    normal_state = require_object(regulator["normal_state"], "regulator.normal_state")
    for instrument_id in configured_instruments:
        spec = require_object(normal_state.get(instrument_id), f"regulator.normal_state.{instrument_id}")
        require_fields(
            spec,
            {"name", "code", "buy_step_ratio", "sell_step_ratio", "buy_shares", "sell_shares", "buy_enabled", "sell_enabled"},
            f"regulator.normal_state.{instrument_id}",
        )
        require_ratio(spec["buy_step_ratio"], f"regulator.normal_state.{instrument_id}.buy_step_ratio", 0.0, 0.5)
        require_ratio(spec["sell_step_ratio"], f"regulator.normal_state.{instrument_id}.sell_step_ratio", 0.0, 0.5)
        require_integer(spec["buy_shares"], f"regulator.normal_state.{instrument_id}.buy_shares", 1)
        require_integer(spec["sell_shares"], f"regulator.normal_state.{instrument_id}.sell_shares", 1)
        require_bool(spec["buy_enabled"], f"regulator.normal_state.{instrument_id}.buy_enabled")
        require_bool(spec["sell_enabled"], f"regulator.normal_state.{instrument_id}.sell_enabled")

    guard = require_object(regulator["capital_guard"], "regulator.capital_guard")
    require_fields(guard, {"weight_base", "weight_base_note", "tiers", "stop_buy_u", "resume_u", "leg_max_weight", "stacking", "step_cap"}, "regulator.capital_guard")
    if not isinstance(guard["tiers"], list) or not guard["tiers"]:
        fail("regulator.capital_guard.tiers", "必须是非空数组")
    previous_u = 0.0
    for index, tier in enumerate(guard["tiers"]):
        tier = require_object(tier, f"regulator.capital_guard.tiers[{index}]")
        require_fields(tier, {"u", "step_multiplier"}, f"regulator.capital_guard.tiers[{index}]")
        current_u = require_ratio(tier["u"], f"regulator.capital_guard.tiers[{index}].u")
        if current_u <= previous_u:
            fail("regulator.capital_guard.tiers", "u 必须严格递增")
        previous_u = current_u
        if float(tier["step_multiplier"]) < 1:
            fail(f"regulator.capital_guard.tiers[{index}].step_multiplier", "必须不小于 1")
    stop_u = require_ratio(guard["stop_buy_u"], "regulator.capital_guard.stop_buy_u")
    resume_u = require_ratio(guard["resume_u"], "regulator.capital_guard.resume_u")
    if resume_u >= stop_u:
        fail("regulator.capital_guard.resume_u", "恢复线必须低于停买线")
    if stop_u <= previous_u:
        fail("regulator.capital_guard.stop_buy_u", "必须高于最高分档 u")
    require_ratio(guard["leg_max_weight"], "regulator.capital_guard.leg_max_weight")
    if guard["stacking"] != "multiply_then_cap":
        fail("regulator.capital_guard.stacking", "v4 仅支持 multiply_then_cap")
    step_cap = require_object(guard["step_cap"], "regulator.capital_guard.step_cap")
    if set(step_cap) != set(configured_instruments):
        fail("regulator.capital_guard.step_cap", "必须与标的完全对应")
    for instrument_id, cap in step_cap.items():
        require_ratio(cap, f"regulator.capital_guard.step_cap.{instrument_id}", 0.0, 0.5)

    levels = require_object(regulator["defense_levels"], "regulator.defense_levels")
    for level in ("A0", "A1", "A2", "A3"):
        spec = require_object(levels.get(level), f"regulator.defense_levels.{level}")
        require_fields(spec, {"step_multiplier", "shares_multiplier", "label"} if level != "A0" else {"step_multiplier", "shares_multiplier", "label"}, f"regulator.defense_levels.{level}")
        if float(spec["step_multiplier"]) < 1 or float(spec["shares_multiplier"]) <= 0:
            fail(f"regulator.defense_levels.{level}", "倍数不合法")

    approval = require_object(regulator["approval"], "regulator.approval")
    require_fields(approval, {"required_for", "default_effect", "channels", "plan_after_approval", "record_fields", "record_location"}, "regulator.approval")
    if sorted(approval["required_for"]) != ["level_down", "level_up"]:
        fail("regulator.approval.required_for", "升档与降档都必须人工审批")
    require_bool(approval["plan_after_approval"], "regulator.approval.plan_after_approval")

    policy = require_object(regulator["policy"], "regulator.policy")
    for forbidden in ("liquidation", "reduce_position"):
        if policy.get(forbidden) != "forbidden":
            fail(f"regulator.policy.{forbidden}", "v4 必须为 forbidden")


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


def logical_path(path: Path | str) -> str:
    """转为逻辑路径：去掉仓库根与 knowledge/ 前缀（动态文档引用规范）。"""
    text = str(path)
    for prefix in (f"{REPO_ROOT}/knowledge/", f"{REPO_ROOT}/", "knowledge/",):
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


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



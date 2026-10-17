#!/usr/bin/env python3
"""招商双债LOF择时体系（system-id: zslof_timing_trade）MCP 服务入口。

一个体系一个服务：实现、`system.yml`、`params/` 与 `templates/` 都在本目录内，
目录名即 `system-id`。注册见 `.pi/mcp.json` 的 `zslof-timing-trade`。

口径：收盘确认的机械波段择时；状态从过程资料「最近先前过程日」读取
（`knowledge/` 优先、`archive/` 兜底），推进与判定按体系 `择时参数.md` 的协议。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
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
SERVER_ROOT = SYSTEM_ROOT.parent
PARAMS_ROOT = SYSTEM_ROOT / "params"
TEMPLATES_ROOT = SYSTEM_ROOT / "templates"
SYSTEM_ID = SYSTEM_ROOT.name
SYSTEM_NAME = "招商双债LOF择时体系"
SYSTEM_VERSION = "v1"
PARAMETER_FILES = ("instrument", "runtime", "timing")
CONTENT_ROOT_NAMES = ("knowledge", "archive")
if not (SYSTEM_ROOT / "system.yml").is_file():
    raise RuntimeError(f"体系运行定义缺失：{SYSTEM_ROOT / 'system.yml'}")


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
    else:
        fmt = "%Y-%m-%d" if "-" in value else "%Y%m%d"
        try:
            parsed = datetime.strptime(value, fmt).date()
        except ValueError as exc:
            raise ValueError(f"date 必须为 YYYY-MM-DD 或 YYYYMMDD：{value}") from exc
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


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    require_fields(timing, {"schema_version", "confirmation_days", "stop_loss_enabled", "chase_enabled", "order_amount", "signal_timing", "execution_timing", "counter_semantics"}, "timing")
    require_integer(timing["confirmation_days"], "timing.confirmation_days", 1)
    require_bool(timing["stop_loss_enabled"], "timing.stop_loss_enabled")
    require_bool(timing["chase_enabled"], "timing.chase_enabled")
    require_integer(timing["order_amount"], "timing.order_amount", 1)
    if timing["signal_timing"] != "close_confirmed" or timing["execution_timing"] != "next_open":
        fail("timing", "必须使用收盘确认、次日开盘执行")
    require_fields(timing["counter_semantics"], {"no_high", "no_low", "stop_loss_priority"}, "timing.counter_semantics")
    require_bool(timing["counter_semantics"]["stop_loss_priority"], "timing.counter_semantics.stop_loss_priority")

    runtime = parameters["runtime"]
    require_fields(runtime, {"schema_version", "process_root", "directory_date_format", "trading_day_only", "history_lookback_calendar_days", "strategy_state_file", "signal_facts_file", "report_file", "state_lookup", "allow_future_state", "state_anchor_date"}, "runtime")
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
    require_string(runtime["state_anchor_date"], "runtime.state_anchor_date")
    return {"valid": True, "files": list(PARAMETER_FILES)}


def parameter_metadata(parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    encoded = json.dumps(parameters, ensure_ascii=False, sort_keys=True).encode()
    return {
        "parameter_version": SYSTEM_VERSION,
        "parameter_hash": hashlib.sha256(encoded).hexdigest(),
        "schema_versions": {name: parameters[name]["schema_version"] for name in PARAMETER_FILES},
    }


def get_client() -> Any:
    load_env()
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    import tushare as ts
    ts.set_token(token)
    return ts.pro_api()


def logical_process_root() -> str:
    raw = str(read_json(PARAMS_ROOT / "runtime.json")["process_root"])
    return raw.split("/", 1)[1] if raw.startswith("knowledge/") else raw


def process_roots() -> list[tuple[Path, str]]:
    relative = logical_process_root()
    return [(REPO_ROOT / name / relative, name) for name in CONTENT_ROOT_NAMES]


def process_dir(directory_date: str) -> Path:
    return process_roots()[0][0] / directory_date / SYSTEM_NAME


def initial_state() -> dict[str, Any]:
    return {
        "strategy_position": "flat",
        "peak": 0.0,
        "trough": None,
        "no_high_days": 0,
        "no_low_days": 0,
        "buy_trough": None,
        "last_sell_peak": None,
        "last_processed_trade_date": None,
        "last_signal": None,
        "last_signal_trade_date": None,
    }


def state_lookup(target_directory_date: str) -> tuple[dict[str, Any], str | None, dict[str, Any]]:
    """读取最近先前过程日的理论状态：knowledge 优先、archive 兜底。"""
    state_file = str(read_json(PARAMS_ROOT / "runtime.json")["strategy_state_file"])
    root_relative = logical_process_root()
    for root, location in process_roots():
        if not root.is_dir():
            continue
        dates = sorted(
            (item.name for item in root.iterdir() if item.is_dir() and item.name < target_directory_date),
            reverse=True,
        )
        for directory_date in dates:
            candidate = root / directory_date / SYSTEM_NAME / state_file
            if not candidate.is_file():
                continue
            document = read_json(candidate)
            state = document.get("state")
            if not isinstance(state, dict):
                raise ValueError(f"策略状态缺少 state 对象：{candidate}")
            logical = f"{root_relative}/{directory_date}/{SYSTEM_NAME}/{state_file}"
            info = {"location": location, "directory_date": directory_date, "physical_path": str(candidate)}
            return {**initial_state(), **state}, logical, info
    return initial_state(), None, {"location": None, "directory_date": None, "physical_path": None}


def fetch_daily(pro: Any, ts_code: str, start_api_date: str, target_api_date: str) -> list[dict[str, Any]]:
    frame = pro.fund_daily(
        ts_code=ts_code,
        start_date=start_api_date,
        end_date=target_api_date,
        fields="ts_code,trade_date,close,pre_close,vol,amount",
    )
    if frame is None or frame.empty:
        raise ValueError(f"未获取到 {ts_code} 的行情：{start_api_date}~{target_api_date}")
    rows = []
    for record in sorted(frame.to_dict("records"), key=lambda item: str(item["trade_date"])):
        rows.append({
            "trade_date": str(record["trade_date"]),
            "close": float(record["close"]),
            "pre_close": float(record["pre_close"]) if record.get("pre_close") is not None else None,
            "vol": float(record["vol"]) if record.get("vol") is not None else None,
        })
    if rows[-1]["trade_date"] != target_api_date:
        raise ValueError(f"目标日期没有行情数据：{target_api_date}")
    return rows


def advance_state(state: dict[str, Any], trade_date: str, close: float, timing: dict[str, Any]) -> str | None:
    position = state["strategy_position"]
    confirmation_days = int(timing["confirmation_days"])
    signal: str | None = None

    if position == "flat" and timing["chase_enabled"] and state["last_sell_peak"] is not None and close > float(state["last_sell_peak"]):
        state.update({
            "strategy_position": "hold",
            "peak": close,
            "no_high_days": 0,
            "no_low_days": 0,
            "buy_trough": state["trough"] if state["trough"] is not None else close,
            "last_sell_peak": None,
        })
        signal = "chase_buy"
    elif position == "hold":
        if close > float(state["peak"]):
            state["peak"] = close
            state["no_high_days"] = 0
        else:
            state["no_high_days"] += 1

        if timing["stop_loss_enabled"] and state["buy_trough"] is not None and close < float(state["buy_trough"]):
            state.update({
                "strategy_position": "flat",
                "trough": close,
                "no_low_days": 0,
                "no_high_days": 0,
                "last_sell_peak": state["peak"],
                "buy_trough": None,
            })
            signal = "stop_loss_sell"
        elif state["no_high_days"] >= confirmation_days and close < float(state["peak"]):
            state.update({
                "strategy_position": "flat",
                "trough": close,
                "no_low_days": 0,
                "no_high_days": 0,
                "last_sell_peak": state["peak"],
                "buy_trough": None,
            })
            signal = "sell"
    else:
        trough = state["trough"]
        if trough is None or close < float(trough):
            state["trough"] = close
            state["no_low_days"] = 0
        else:
            state["no_low_days"] += 1

        if state["no_low_days"] >= confirmation_days and close > float(state["trough"]):
            state.update({
                "strategy_position": "hold",
                "peak": close,
                "no_high_days": 0,
                "no_low_days": 0,
                "buy_trough": state["trough"],
                "last_sell_peak": None,
            })
            signal = "buy"

    state["last_processed_trade_date"] = trade_date
    if signal is not None:
        state["last_signal"] = signal
        state["last_signal_trade_date"] = trade_date
    return signal


def action_tomorrow(signal: str | None, strategy_position: str) -> str:
    actions = {"buy": "buy", "sell": "sell_all", "stop_loss_sell": "sell_all", "chase_buy": "buy"}
    return actions.get(signal, "hold" if strategy_position == "hold" else "no_action")


def build_checks(before: dict[str, Any], after: dict[str, Any], close: float, timing: dict[str, Any]) -> list[dict[str, Any]]:
    """把当日判定拆成结构化判据，供报告渲染与复核。"""
    confirmation_days = int(timing["confirmation_days"])
    checks: list[dict[str, Any]] = []

    if before["strategy_position"] == "flat":
        trough = before["trough"]
        if after["trough"] == trough:
            checks.append({"label": "非创新低", "met": False, "detail": f"收盘 {close} 未严格低于空仓期谷值 {trough}；谷值不变，no_low_days 累计至 {after['no_low_days']}"})
        else:
            checks.append({"label": "创新低", "met": True, "detail": f"收盘 {close} 低于原谷值 {trough} → 谷值更新为 {after['trough']}，no_low_days 归零"})
        count_leg = after["no_low_days"] >= confirmation_days
        price_leg = after["trough"] is not None and close > float(after["trough"])
        checks.append({
            "label": "普通买入条件",
            "met": bool(count_leg and price_leg),
            "detail": f"计数腿 {after['no_low_days']} ≥ {confirmation_days}：{'成立' if count_leg else '不成立'}；价格腿 收盘 {close} 严格高于谷值 {after['trough']}：{'成立' if price_leg else '不成立'}",
        })
        anchor = before["last_sell_peak"]
        if anchor is None:
            checks.append({"label": "追回买入条件", "met": None, "detail": "无追回锚（last_sell_peak 为空）"})
        else:
            checks.append({
                "label": "追回买入条件",
                "met": close > float(anchor),
                "detail": f"追回锚 {anchor}；收盘 {close} {'严格高于' if close > float(anchor) else '未突破'}（差 {round(float(anchor) - close, 6)}）",
            })
        checks.append({"label": "止损", "met": None, "detail": "空仓期不检查止损（止损仅作用于持仓期跌破买入前谷值）"})
    else:
        peak = before["peak"]
        if after["peak"] != peak:
            checks.append({"label": "创出新高", "met": True, "detail": f"收盘 {close} 高于原峰值 {peak} → 峰值更新为 {after['peak']}，no_high_days 归零"})
        else:
            checks.append({"label": "未创出新高", "met": False, "detail": f"收盘 {close} 未高于峰值 {peak}；no_high_days 累计至 {after['no_high_days']}"})
        buy_trough = before["buy_trough"]
        if not timing["stop_loss_enabled"]:
            checks.append({"label": "止损条件", "met": None, "detail": "未启用止损"})
        elif buy_trough is None:
            checks.append({"label": "止损条件", "met": None, "detail": "无买入前谷值（buy_trough 为空）"})
        else:
            checks.append({"label": "止损条件", "met": close < float(buy_trough), "detail": f"买入前谷值 {buy_trough}；收盘 {close} {'低于' if close < float(buy_trough) else '未低于'}"})
        count_leg = after["no_high_days"] >= confirmation_days
        price_leg = close < float(after["peak"])
        checks.append({
            "label": "普通卖出条件",
            "met": bool(count_leg and price_leg),
            "detail": f"计数腿 {after['no_high_days']} ≥ {confirmation_days}：{'成立' if count_leg else '不成立'}；价格腿 收盘 {close} 低于峰值 {after['peak']}：{'成立' if price_leg else '不成立'}",
        })
    return checks


def compose_note(checks: list[dict[str, Any]], signal: str | None) -> str:
    def state_text(met: Any) -> str:
        return "成立" if met is True else ("不成立" if met is False else "不适用")
    parts = [f"{check['label']}{state_text(check['met'])}（{check['detail']}）" for check in checks]
    return "；".join(parts) + f"；signal = {signal if signal is not None else 'null'}。"


def calculate_signal(target_date: str, parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    api_date, directory_date = normalize_date(target_date)
    instrument = parameters["instrument"]["instrument"]
    timing = parameters["timing"]
    runtime = parameters["runtime"]

    prior_state, prior_logical, prior_info = state_lookup(directory_date)
    pro = get_client()
    lookback_days = int(runtime["history_lookback_calendar_days"])
    start_date = (datetime.strptime(api_date, "%Y%m%d").date() - timedelta(days=lookback_days)).strftime("%Y%m%d")
    rows = fetch_daily(pro, instrument["ts_code"], start_date, api_date)

    state = dict(prior_state)
    before_target = dict(state)
    emitted_signal: str | None = None
    for row in rows:
        trade_date = row["trade_date"]
        if state["last_processed_trade_date"] and trade_date <= state["last_processed_trade_date"]:
            continue
        if trade_date == api_date:
            before_target = dict(state)
        signal = advance_state(state, trade_date, row["close"], timing)
        if signal is not None and trade_date == api_date:
            emitted_signal = signal

    if state["last_processed_trade_date"] != api_date:
        raise ValueError("目标日期没有推进理论策略状态")
    if emitted_signal is None and state["last_signal_trade_date"] == api_date:
        emitted_signal = state["last_signal"]

    target_row = rows[-1]
    previous_row = rows[-2] if len(rows) > 1 else None
    close = float(target_row["close"])
    pre_close = target_row["pre_close"]
    volume = target_row["vol"]
    previous_volume = previous_row["vol"] if previous_row else None
    daily_change = (close / pre_close - 1) if pre_close else None
    volume_change = (volume / previous_volume - 1) if volume and previous_volume else None
    checks = build_checks(before_target, state, close, timing)

    strategy_state = {
        "date": directory_date,
        "system_id": SYSTEM_ID,
        "artifact": "strategy_state",
        "source_state": prior_logical,
        "source_state_detail": prior_info,
        "state": state,
    }
    signal_facts = {
        "instrument": instrument,
        "market": {
            "trade_date": api_date,
            "close": close,
            "pre_close": pre_close,
            "daily_change_ratio": round(daily_change, 8) if daily_change is not None else None,
            "volume": volume,
            "volume_change_ratio": round(volume_change, 8) if volume_change is not None else None,
            "source_data_start_date": rows[0]["trade_date"],
        },
        "strategy_position": state["strategy_position"],
        "position_before": before_target["strategy_position"],
        "signal": emitted_signal,
        "next_trading_action": action_tomorrow(emitted_signal, state["strategy_position"]),
        "state_anchors": {
            "peak": state["peak"] if state["peak"] else None,
            "trough": state["trough"],
            "buy_trough": state["buy_trough"],
            "last_sell_peak": state["last_sell_peak"],
        },
        "checks": checks,
        "parameters": {
            "confirmation_days": timing["confirmation_days"],
            "stop_loss_enabled": timing["stop_loss_enabled"],
            "chase_enabled": timing["chase_enabled"],
            "order_amount": timing["order_amount"],
            "execution_timing": timing["execution_timing"],
        },
        "state_source_path": prior_logical,
        "note": compose_note(checks, emitted_signal),
    }
    return {
        "strategy_state": artifact("strategy_state", directory_date, parameters, strategy_state),
        "signal_facts": artifact("signal_facts", directory_date, parameters, signal_facts),
    }


def replay_check(target_date: str, parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """从锚日重放收盘价序列并与存储状态比对（只读，不写产物）。"""
    api_date, directory_date = normalize_date(target_date)
    instrument = parameters["instrument"]["instrument"]
    timing = parameters["timing"]
    runtime = parameters["runtime"]
    anchor_api, _ = normalize_date(str(runtime["state_anchor_date"]))
    if anchor_api > api_date:
        raise ValueError(f"锚日 {anchor_api} 晚于目标日期 {api_date}")

    pro = get_client()
    rows = fetch_daily(pro, instrument["ts_code"], anchor_api, api_date)
    replayed = initial_state()
    signals: list[dict[str, Any]] = []
    for row in rows:
        signal = advance_state(replayed, row["trade_date"], row["close"], timing)
        if signal is not None:
            signals.append({"trade_date": row["trade_date"], "signal": signal, "close": row["close"]})

    stored_path = process_dir(directory_date) / str(runtime["strategy_state_file"])
    if stored_path.is_file():
        reference = read_json(stored_path)["state"]
        reference_source = str(stored_path)
    else:
        prior_state, prior_logical, _ = state_lookup(directory_date)
        reference = dict(prior_state)
        for row in rows:
            if reference["last_processed_trade_date"] and row["trade_date"] <= reference["last_processed_trade_date"]:
                continue
            advance_state(reference, row["trade_date"], row["close"], timing)
        reference_source = f"由最近先前状态（{prior_logical}）推进至 {api_date}"

    diff = [key for key in sorted(set(replayed) | set(reference)) if replayed.get(key) != reference.get(key)]
    return {
        "ok": True,
        "artifact": "replay_check",
        "system_id": SYSTEM_ID,
        "date": directory_date,
        "anchor_date": anchor_api,
        "bars": len(rows),
        "signals_replayed": signals,
        "state_replayed": replayed,
        "state_reference": reference,
        "reference_source": reference_source,
        "matched": not diff,
        "diff_fields": diff,
    }


def artifact(kind: str, directory_date: str, parameters: dict[str, dict[str, Any]], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": directory_date,
        "system_id": SYSTEM_ID,
        "artifact": kind,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": SYSTEM_VERSION,
        **parameter_metadata(parameters),
        **payload,
    }


def write_artifact(document: dict[str, Any], filename: str) -> str:
    path = process_dir(document["date"]) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)


def render_artifact(document: dict[str, Any], state_document: dict[str, Any] | None = None) -> dict[str, Any]:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    runtime = read_json(PARAMS_ROOT / "runtime.json")
    if str(document.get("artifact")) != "signal_facts":
        raise ValueError(f"不支持的渲染目标：{document.get('artifact')}")
    output_name = str(runtime["report_file"])
    if state_document is None:
        candidate = process_dir(document["date"]) / str(runtime["strategy_state_file"])
        if not candidate.is_file():
            raise ValueError(f"缺少同日策略状态，无法渲染报告：{candidate}")
        state_document = read_json(candidate)
    source_path = f"{logical_process_root()}/{document['date']}/{SYSTEM_NAME}/{runtime['signal_facts_file']}"
    environment = Environment(loader=FileSystemLoader(str(TEMPLATES_ROOT)), undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
    markdown = environment.get_template(f"{output_name}.j2").render(
        signal=document,
        state=state_document,
        source_path=source_path,
        report_uuid=uuid.uuid5(uuid.NAMESPACE_URL, f"pi-trader:{SYSTEM_ID}:{document['date']}:{output_name}").hex,
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    path = process_dir(document["date"]) / output_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return {"path": str(path), "artifact": "signal_report", "system_id": SYSTEM_ID, "date": document["date"]}


def tool_calculate(arguments: dict[str, Any]) -> dict[str, Any]:
    parameters = load_parameters()
    operation = arguments.get("operation")
    if operation == "signal":
        document = calculate_signal(arguments["date"], parameters)
    elif operation == "replay_check":
        return replay_check(arguments["date"], parameters)
    else:
        raise ValueError("operation 必须是 signal 或 replay_check")
    if bool(arguments.get("dry_run", False)):
        return document
    paths = {
        "strategy_state": write_artifact(document["strategy_state"], str(parameters["runtime"]["strategy_state_file"])),
        "signal_facts": write_artifact(document["signal_facts"], str(parameters["runtime"]["signal_facts_file"])),
    }
    return {**document, "output_paths": paths}


TOOLS = [
    Tool(name="list_systems", description="列出本服务实现的交易体系。", inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_manifest", description="查看招商双债LOF择时体系运行定义和支持的操作。", inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}}, "required": ["system_id"]}),
    Tool(name="validate_parameters", description="校验本体系当前参数。", inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}}, "required": ["system_id"]}),
    Tool(name="calculate", description="计算当日收盘信号与理论状态（signal），或从锚日重放校验（replay_check）；signal 默认写入过程资料。", inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}, "operation": {"type": "string", "enum": ["signal", "replay_check"]}, "date": {"type": "string"}, "dry_run": {"type": "boolean"}}, "required": ["system_id", "operation", "date"]}),
    Tool(name="render", description="把当日信号事实渲染为可读信号报告。", inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}, "artifact": {"type": "string", "enum": ["signal_report"]}, "date": {"type": "string"}, "document": {"type": "object"}, "state": {"type": "object"}}, "required": ["system_id", "artifact", "date"]}),
]

server = Server("zslof-timing-trade")


def list_tools_result() -> list[Tool]:
    return TOOLS


def call_tool_result(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    args = arguments or {}
    try:
        if name == "list_systems":
            result = {"systems": [{"system_id": SYSTEM_ID, "name": SYSTEM_NAME, "operations": ["signal", "replay_check"]}]}
        elif name == "get_manifest":
            if args.get("system_id") != SYSTEM_ID:
                raise ValueError(f"当前 MCP 不支持体系：{args.get('system_id')}")
            result = {
                "system_id": SYSTEM_ID,
                "name": SYSTEM_NAME,
                "version": SYSTEM_VERSION,
                "system_root": str(SYSTEM_ROOT),
                "parameter_root": str(PARAMS_ROOT),
                "template_root": str(TEMPLATES_ROOT),
                "operations": ["signal", "replay_check"],
                "writes_to": f"knowledge/{logical_process_root()}/{{date}}/{SYSTEM_NAME}",
                "boundaries": {"queries_account": False, "real_order": "forbidden", "writes_plan": False},
            }
        elif name == "validate_parameters":
            if args.get("system_id") != SYSTEM_ID:
                raise ValueError(f"当前 MCP 不支持体系：{args.get('system_id')}")
            parameters = load_parameters()
            result = {"system_id": SYSTEM_ID, **validate_parameters(parameters), **parameter_metadata(parameters)}
        elif name == "calculate":
            if args.get("system_id") != SYSTEM_ID:
                raise ValueError(f"当前 MCP 不支持体系：{args.get('system_id')}")
            result = tool_calculate(args)
        elif name == "render":
            if args.get("system_id") != SYSTEM_ID:
                raise ValueError(f"当前 MCP 不支持体系：{args.get('system_id')}")
            _, directory_date = normalize_date(args["date"])
            if args.get("artifact") != "signal_report":
                raise ValueError(f"不支持的渲染目标：{args.get('artifact')}")
            document = args.get("document")
            if document is None:
                runtime = read_json(PARAMS_ROOT / "runtime.json")
                document = read_json(process_dir(directory_date) / str(runtime["signal_facts_file"]))
            if not isinstance(document, dict):
                raise ValueError("document 必须是 JSON 对象")
            if document.get("date") != directory_date:
                raise ValueError("document.date 与 date 不一致")
            result = render_artifact(document, args.get("state"))
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

    server = Server("zslof-timing-trade", on_list_tools=list_tools, on_call_tool=call_tool)


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

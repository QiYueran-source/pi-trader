"""参数读取、校验（运行契约与候选池）与元数据。"""

from __future__ import annotations

import json
import hashlib
import re
from typing import Any

from functions.paths import PARAMETER_FILES, PARAMS_ROOT, REVIEW_ARTIFACTS, SYSTEM_VERSION, read_json

CODE_PATTERN = re.compile(r"^\d{6}\.(SH|SZ)$")
UNIVERSE_FIELDS = {"code", "name", "asset_class", "fee_pct_per_year", "note"}

def fail(field: str, message: str) -> None:
    raise ValueError(f"字段 {field}: {message}")

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

def require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        fail(field, "必须是数组")
    return value

def require_string_list(value: Any, field: str) -> list[str]:
    for index, item in enumerate(require_list(value, field)):
        if not isinstance(item, str) or not item.strip():
            fail(f"{field}[{index}]", "必须是非空字符串")
    return list(value)

def load_parameters() -> dict[str, dict[str, Any]]:
    parameters = {name: read_json(PARAMS_ROOT / f"{name}.json") for name in PARAMETER_FILES}
    validate_parameters(parameters)
    return parameters

def validate_parameters(parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if set(parameters) != set(PARAMETER_FILES):
        raise ValueError(f"参数文件必须为：{', '.join(PARAMETER_FILES)}")
    runtime = parameters["runtime"]
    require_fields(
        runtime,
        {
            "schema_version",
            "process_root",
            "plan_root",
            "review_root",
            "directory_date_format",
            "process_file",
            "review_file",
            "render_artifacts",
            "trading_calendar_lookback_days",
        },
        "runtime",
    )
    version = runtime["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        fail("runtime.schema_version", "必须是不小于 1 的整数")
    for field in ("process_root", "plan_root", "review_root", "process_file", "review_file"):
        require_string(runtime[field], f"runtime.{field}")
    if runtime["process_root"] not in {"knowledge", "knowledge/交易/过程资料"} and not str(runtime["process_root"]).startswith("knowledge/"):
        fail("runtime.process_root", "必须以 knowledge 开头（物理落盘根）")
    if runtime["directory_date_format"] != "%Y-%m-%d":
        fail("runtime.directory_date_format", "必须为 %Y-%m-%d")
    require_integer(runtime["trading_calendar_lookback_days"], "runtime.trading_calendar_lookback_days", 1)
    artifacts = require_string_list(runtime["render_artifacts"], "runtime.render_artifacts")
    if tuple(artifacts) != REVIEW_ARTIFACTS:
        fail("runtime.render_artifacts", f"必须为 {list(REVIEW_ARTIFACTS)}")
    validate_universe(parameters["universe"])
    return {"valid": True, "files": list(PARAMETER_FILES)}

def validate_universe(universe: dict[str, Any]) -> None:
    require_fields(universe, {"schema_version", "as_of", "cash_substitute", "instruments", "notes"}, "universe")
    version = universe["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        fail("universe.schema_version", "必须是不小于 1 的整数")
    require_string(universe["as_of"], "universe.as_of")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", universe["as_of"]):
        fail("universe.as_of", "必须为 YYYY-MM-DD")
    require_string(universe["notes"], "universe.notes")
    instruments = universe["instruments"]
    if not isinstance(instruments, list) or not instruments:
        fail("universe.instruments", "必须是非空数组")
    codes: list[str] = []
    for index, item in enumerate(instruments):
        if not isinstance(item, dict):
            fail(f"universe.instruments[{index}]", "必须是对象")
        require_fields(item, UNIVERSE_FIELDS, f"universe.instruments[{index}]")
        code = require_string(item["code"], f"universe.instruments[{index}].code")
        if not CODE_PATTERN.match(code):
            fail(f"universe.instruments[{index}].code", "必须形如 510300.SH")
        require_string(item["name"], f"universe.instruments[{index}].name")
        require_string(item["asset_class"], f"universe.instruments[{index}].asset_class")
        require_string(item["note"], f"universe.instruments[{index}].note")
        fee = item["fee_pct_per_year"]
        if isinstance(fee, bool) or not isinstance(fee, (int, float)) or fee <= 0 or fee > 5:
            fail(f"universe.instruments[{index}].fee_pct_per_year", "必须是 0-5 之间的数值")
        codes.append(code)
    if len(set(codes)) != len(codes):
        fail("universe.instruments", "代码不得重复")
    cash = require_string(universe["cash_substitute"], "universe.cash_substitute")
    if cash not in codes:
        fail("universe.cash_substitute", "必须在 instruments 代码列表内")
    return None

def parameter_metadata(parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    encoded = json.dumps(parameters, ensure_ascii=False, sort_keys=True).encode()
    return {
        "parameter_version": SYSTEM_VERSION,
        "parameter_hash": hashlib.sha256(encoded).hexdigest(),
        "schema_versions": {name: parameters[name]["schema_version"] for name in PARAMETER_FILES},
    }

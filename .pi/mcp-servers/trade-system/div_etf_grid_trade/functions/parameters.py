"""参数加载与校验（`params/*.json`）。

数值唯一来源仍是 `params/`，本模块只读取与校验。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from functions.paths import PARAMETER_FILES, PARAMS_ROOT, read_json

EXPANSION_KEYS = {"buy_step_ratio", "sell_step_ratio", "buy_shares", "sell_shares"}


def load_parameters() -> dict[str, dict[str, Any]]:
    parameters = {name: read_json(PARAMS_ROOT / f"{name}.json") for name in PARAMETER_FILES}
    validate_parameters(parameters)
    return parameters


def validate_parameters(parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if set(parameters) != set(PARAMETER_FILES):
        raise ValueError(f"参数文件必须为：{', '.join(PARAMETER_FILES)}")
    for name, value in parameters.items():
        version = value.get("schema_version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError(f"{name}.schema_version 必须是不小于 1 的整数")
    instruments = parameters["instruments"].get("instruments")
    if not isinstance(instruments, dict) or set(instruments) != {"dividend", "growth"}:
        raise ValueError("instruments.instruments 必须且只能包含 dividend 与 growth")
    regulator = parameters["regulator"]
    normal = {key: value for key, value in regulator.get("normal_state", {}).items() if not key.startswith("note")}
    if not isinstance(normal, dict) or set(normal) != {"dividend", "growth"}:
        raise ValueError("regulator.normal_state 必须包含 dividend 与 growth")
    guard = regulator.get("capital_guard", {})
    if float(guard.get("resume_u", 1)) >= float(guard.get("stop_buy_u", 0)):
        raise ValueError("capital_guard.resume_u 必须低于 stop_buy_u")
    scaling = regulator.get("scaling")
    declared = {name: value for name, value in scaling.items() if not name.startswith("note")} if isinstance(scaling, dict) else {}
    if set(declared) != EXPANSION_KEYS:
        raise ValueError(f"regulator.scaling 必须且只能包含：{', '.join(sorted(EXPANSION_KEYS))}")
    scaling = declared
    for name in sorted(EXPANSION_KEYS):
        item = scaling[name]
        if not isinstance(item, dict):
            raise ValueError(f"scaling.{name} 必须是对象")
        factors = item.get("factors")
        if not isinstance(factors, list) or not factors or any(factor not in {"defense", "capital"} for factor in factors):
            raise ValueError(f"scaling.{name}.factors 必须是非空数组且只含 defense / capital")
        if item.get("cap") not in {None, "step_cap"}:
            raise ValueError(f"scaling.{name}.cap 只能是 null 或 step_cap")
        if item.get("rounding") not in {None, "floor100"}:
            raise ValueError(f"scaling.{name}.rounding 只能是 null 或 floor100")
    for name in ("buy_shares", "sell_shares"):
        item = scaling[name]
        if item.get("cap") is not None:
            raise ValueError(f"scaling.{name} 不支持 cap（档距上限只用于档距）")
    for name in ("buy_step_ratio", "sell_step_ratio"):
        if scaling[name].get("rounding") is not None:
            raise ValueError(f"scaling.{name} 不支持 rounding（取整只用于份数）")
    for key in normal:
        for field in ("buy_shares", "sell_shares"):
            shares = normal[key].get(field)
            if not isinstance(shares, int) or isinstance(shares, bool) or shares <= 0 or shares % 100:
                raise ValueError(f"regulator.normal_state.{key}.{field} 必须是 100 的正整数倍")
    reserve = regulator.get("reserve_shares", {})
    if reserve.get("enabled"):
        if reserve.get("mode") != "shares":
            raise ValueError("reserve_shares.mode 目前只支持 shares")
        per_leg = reserve.get("per_leg")
        if not isinstance(per_leg, dict) or set(per_leg) != {"dividend", "growth"}:
            raise ValueError("reserve_shares.per_leg 必须包含 dividend 与 growth")
        for key in sorted(per_leg):
            floor_shares = per_leg[key]
            if not isinstance(floor_shares, int) or isinstance(floor_shares, bool) or floor_shares < 0 or floor_shares % 100:
                raise ValueError(f"reserve_shares.per_leg.{key} 必须是 100 的非负整数倍")
    if regulator.get("policy", {}).get("liquidation") != "forbidden":
        raise ValueError("v4 禁止清仓")
    if regulator.get("policy", {}).get("reduce_position") != "forbidden":
        raise ValueError("v4 禁止减仓")
    return {"valid": True, "files": list(PARAMETER_FILES)}


def parameter_metadata(parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    encoded = json.dumps(parameters, ensure_ascii=False, sort_keys=True).encode()
    return {
        "parameter_version": parameters["regulator"].get("version", "unknown"),
        "parameter_hash": hashlib.sha256(encoded).hexdigest(),
        "schema_versions": {name: parameters[name]["schema_version"] for name in PARAMETER_FILES},
    }

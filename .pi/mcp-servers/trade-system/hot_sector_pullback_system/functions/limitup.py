"""涨跌停口径：分板阈值、新股与首日排除。"""

from __future__ import annotations

from typing import Any

from functions.paths import HIT_LIMIT_EPSILON

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

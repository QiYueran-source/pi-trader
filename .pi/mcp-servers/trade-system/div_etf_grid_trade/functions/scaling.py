"""倍数叠加与份数取整（口径见 `params/regulator.json#scaling`）。"""
from __future__ import annotations

from typing import Any


def floor100(value: float) -> int:
    """申报份数取整：向下取到 100 的整数倍，最小 100 份（ETF 最小交易单位）。"""
    return max(100, int(value // 100) * 100)


def apply_factors(value: float, factors: Any, *, defense_multiplier: float, capital_multiplier: float) -> float:
    """按 params/regulator.json#scaling 声明的因子列表缩放一个量。"""
    result = float(value)
    if not isinstance(factors, list):
        raise ValueError("scaling 的 factors 必须是数组")
    for factor in factors:
        if factor == "defense":
            result *= float(defense_multiplier)
        elif factor == "capital":
            result *= float(capital_multiplier)
        else:
            raise ValueError(f"未知缩放因子：{factor}")
    return result

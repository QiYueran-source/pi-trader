"""候选筛选：均线、回调过滤、建仓条件与候选产物。"""

from __future__ import annotations

from datetime import date
from typing import Any

from functions.artifacts import artifact
from functions.limitup import is_new_or_first_day, limit_pct
from functions.market import fetch_daily_market, fetch_stock_info, fetch_trade_days, get_client, market_daily_start
from functions.paths import HIT_LIMIT_EPSILON, logical_process_path, process_dir, write_json

def moving_average(values: list[float], period: int) -> float | None:
    if len(values) < period or period < 1:
        return None
    return sum(values[-period:]) / period

def passes_pullback_filter(closes: list[float], period: int, rebound_window: int) -> tuple[bool, float | None, int | None]:
    """逐日比较：窗口内每个交易日重算 MA；要求当日收盘 ≥ 当日 MA，且最近一次跌破后的反弹不超过 rebound_window。"""
    if len(closes) < period:
        return False, None, None
    current_ma = moving_average(closes, period)
    if current_ma is None or closes[-1] < current_ma:
        return False, current_ma, None
    last_below_index = None
    for index in range(period - 1, len(closes)):
        average = moving_average(closes[: index + 1], period)
        if average is not None and closes[index] < average:
            last_below_index = index
    if last_below_index is None:
        return True, current_ma, None
    bounceback_days = len(closes) - 1 - last_below_index
    if bounceback_days > rebound_window:
        return False, current_ma, bounceback_days
    recovered = True
    for index in range(last_below_index + 1, len(closes)):
        average = moving_average(closes[: index + 1], period)
        if average is not None and closes[index] < average:
            recovered = False
            break
    return recovered, current_ma, bounceback_days

def build_candidates(
    daily: Any,
    window_days: set[str],
    target_date: str,
    industry_by_code: dict[str, str],
    name_by_code: dict[str, str],
    list_date_by_code: dict[str, str],
    selection: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    candidates: list[dict[str, Any]] = []
    limit_up_codes: set[str] = set()
    for code, records in daily.groupby("ts_code"):
        records = records.sort_values("trade_date")
        name = name_by_code.get(str(code), "")
        threshold = limit_pct(str(code), name)
        board_dates = sorted(
            str(item)
            for item in records.loc[
                records["trade_date"].isin(window_days) & (records["pct_chg"] >= threshold - HIT_LIMIT_EPSILON),
                "trade_date",
            ].tolist()
        )
        if not (selection["min_limit_up_count"] <= len(board_dates) <= selection["max_limit_up_count"]):
            continue
        if is_new_or_first_day(name, list_date_by_code.get(str(code), ""), target_date):
            continue
        limit_up_codes.add(str(code))
        closes = [float(value) for value in records["close"].tolist()]
        passed, average, bounceback_days = passes_pullback_filter(
            closes, selection["pullback_ma_period"], selection["rebound_window_days"]
        )
        if not passed or average is None:
            continue
        current_close = closes[-1]
        board_records = records.loc[records["trade_date"].isin(board_dates)]
        peak = float(board_records["high"].max()) if not board_records.empty else current_close
        candidates.append(
            {
                "code": str(code),
                "name": name,
                "industry": industry_by_code.get(str(code), ""),
                "board_count": len(board_dates),
                "board_dates": board_dates,
                "current_close": round(current_close, 3),
                "pullback_ma": round(average, 3),
                "pullback_pct": round((current_close - peak) / peak * 100, 2),
                "bounceback_days": bounceback_days,
            }
        )
    candidates.sort(key=lambda item: item["pullback_pct"])
    return candidates, len(limit_up_codes)

def build_signal(candidate: dict[str, Any], records: Any, entry: dict[str, Any]) -> dict[str, Any] | None:
    required_days = max(entry["volume_average_period"], entry["breakout_ma_period"])
    if len(records) < required_days:
        return None
    closes = [float(value) for value in records["close"].tolist()]
    volumes = [float(value) for value in records["vol"].tolist()]
    breakout_ma = moving_average(closes, entry["breakout_ma_period"])
    volume_ma = moving_average(volumes, entry["volume_average_period"])
    if breakout_ma is None or volume_ma is None or volume_ma <= 0:
        return None
    close = closes[-1]
    volume = volumes[-1]
    if close <= breakout_ma or volume <= entry["volume_multiplier"] * volume_ma:
        return None
    latest = records.iloc[-1]
    return {
        "code": candidate["code"],
        "name": candidate["name"],
        "industry": candidate["industry"],
        "board_count": candidate["board_count"],
        "board_dates": candidate["board_dates"],
        "pullback_pct": candidate["pullback_pct"],
        "signal_date": str(latest["trade_date"]),
        "close": round(close, 3),
        "breakout_ma": round(breakout_ma, 3),
        "breakout_above_pct": round((close - breakout_ma) / breakout_ma * 100, 2),
        "volume": int(volume),
        "volume_ma": int(volume_ma),
        "volume_ratio": round(volume / volume_ma, 2),
        "pass": True,
    }

def op_select_candidates(
    target_api_date: str,
    directory_date: str,
    industries: list[str] | None,
    parameters: dict[str, dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    client = get_client()
    selection = parameters["selection"]
    trade_days = fetch_trade_days(client, market_daily_start(target_api_date, parameters), target_api_date)
    if target_api_date not in trade_days:
        raise ValueError(f"{directory_date} 不是交易日，无候选事实")
    window_days = set(trade_days[-selection["limit_up_window_days"]:])
    daily = fetch_daily_market(client, trade_days, fields="ts_code,trade_date,close,high,vol,pct_chg")
    if daily.empty:
        raise RuntimeError("未获取到日线数据")
    industry_by_code, name_by_code, list_date_by_code = fetch_stock_info(client)
    candidates, total_limit_up = build_candidates(
        daily, window_days, target_api_date, industry_by_code, name_by_code, list_date_by_code, selection
    )
    filtered = [
        item
        for item in candidates
        if not industries or item["industry"] in set(industries)
    ]
    kind = "hottest_industry_candidate" if industries else "full_market_candidate"
    filename = f"{kind}.json"
    sectors = sorted({item["industry"] for item in filtered if item["industry"]})
    note = (
        f"窗口＝最近 {selection['limit_up_window_days']} 个交易日；涨停＝分板精确（北交所 30%／双创 20%／主板 10%／ST 5%，"
        f"容差 {HIT_LIMIT_EPSILON}），剔除 N/C 新股与上市首日；回调过滤＝逐日重算 MA{selection['pullback_ma_period']} 后逐日比较，"
        f"反弹窗口 {selection['rebound_window_days']} 个交易日。"
    )
    payload = artifact(
        kind,
        directory_date,
        parameters,
        note,
        {
            "params": {key: value for key, value in selection.items() if key != "schema_version"},
            "stats": {
                "total_limit_up_stocks": total_limit_up,
                "total_candidates": len(filtered),
                "candidate_sectors": len(sectors),
            },
            "candidates": filtered,
        },
    )
    if industries:
        payload["industry"] = list(industries)
    if dry_run:
        return {"ok": True, "dry_run": True, "artifact": kind, "date": directory_date, "document": payload}
    path = write_json(process_dir(directory_date, create=True) / filename, payload)
    return {"ok": True, "artifact": kind, "date": directory_date, "path": path, "logical_path": logical_process_path(directory_date, filename), "stats": payload["stats"]}

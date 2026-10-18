"""板块热度与全市场板块环境。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from functions.artifacts import artifact
from functions.limitup import hit_limit, is_new_or_first_day, is_st, limit_pct
from functions.market import fetch_daily_market, fetch_index_pct, fetch_stock_info, fetch_trade_days, get_client, market_daily_start
from functions.paths import BENCHMARK_INDEX, HIT_LIMIT_EPSILON, load_process_document, logical_process_path, process_dir, write_json
from functions.selection import moving_average
from functions.signals import signalize

def build_sector_environment(
    daily: Any,
    target_date: str,
    previous_trade_date: str | None,
    industry_by_code: dict[str, str],
    name_by_code: dict[str, str],
    list_date_by_code: dict[str, str],
    parameters: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    client = get_client()
    limit_up_by_industry: dict[str, int] = defaultdict(int)
    limit_up_sample: list[str] = []
    limit_up_total = 0
    limit_up_clean = 0
    limit_down_total = 0
    up = down = flat = 0
    amount_total = 0.0
    highest = {"count": 0, "code": "", "name": "", "industry": ""}

    grouped = {str(code): records.sort_values("trade_date") for code, records in daily.groupby("ts_code")}
    for code, records in grouped.items():
        today = records.loc[records["trade_date"] == target_date]
        if today.empty:
            continue
        row = today.iloc[-1]
        name = name_by_code.get(code, "")
        if is_new_or_first_day(name, list_date_by_code.get(code, ""), target_date):
            continue
        pct = float(row["pct_chg"])
        amount_total += float(row.get("amount", 0.0) or 0.0)
        if pct > 0:
            up += 1
        elif pct < 0:
            down += 1
        else:
            flat += 1
        threshold = limit_pct(code, name)
        if hit_limit(pct, threshold):
            limit_up_total += 1
            industry = industry_by_code.get(code, "")
            if not is_st(name):
                limit_up_clean += 1
                limit_up_by_industry[industry] += 1
                if len(limit_up_sample) < 20:
                    limit_up_sample.append(f"{code} {name}（{industry}）")
        elif is_st(name) is False and hit_limit(-pct, threshold):
            limit_down_total += 1

    for code, records in grouped.items():
        count = 0
        for _, row in records.sort_values("trade_date", ascending=False).iterrows():
            name = name_by_code.get(code, "")
            if not hit_limit(float(row["pct_chg"]), limit_pct(code, name)):
                break
            count += 1
        if count > highest["count"]:
            highest = {
                "count": count,
                "code": code,
                "name": name_by_code.get(code, ""),
                "industry": industry_by_code.get(code, ""),
            }

    previous_amount = 0.0
    if previous_trade_date:
        previous_rows = daily.loc[daily["trade_date"] == previous_trade_date]
        if not previous_rows.empty:
            previous_amount = float(previous_rows["amount"].sum())

    tiers = parameters["entry"]["benchmark_tiers"]
    stabilize_above = float(tiers["stabilize_above_pct"])
    extreme_weak_at_or_below = float(tiers["extreme_weak_at_or_below_pct"])
    benchmark_pct = fetch_index_pct(client, BENCHMARK_INDEX, target_date)
    if benchmark_pct is None:
        benchmark_tier = "unavailable"
    elif benchmark_pct > stabilize_above:
        benchmark_tier = "企稳"
    elif benchmark_pct > extreme_weak_at_or_below:
        benchmark_tier = "非极端弱"
    else:
        benchmark_tier = "极端弱"

    ranking = sorted(
        ({"industry": key, "limit_up_clean": value} for key, value in limit_up_by_industry.items()),
        key=lambda item: item["limit_up_clean"],
        reverse=True,
    )
    return {
        "market": {
            "up": up,
            "down": down,
            "flat": flat,
            "limit_up": limit_up_total,
            "limit_up_clean": limit_up_clean,
            "limit_down_clean": limit_down_total,
            "total_amount_yi": round(amount_total / 100000.0, 4),
            "previous_amount_yi": round(previous_amount / 100000.0, 4),
            "amount_change_yi": round((amount_total - previous_amount) / 100000.0, 4),
        },
        "limit_up_by_industry": ranking,
        "limit_up_sample": limit_up_sample,
        "highest_board": highest,
        "benchmark": {"ts_code": BENCHMARK_INDEX, "pct_chg": benchmark_pct, "tier": benchmark_tier},
        "note": (
            f"涨停/跌停＝分板精确阈值（北交所 30%／双创 20%／主板 10%／ST 5%，容差 {HIT_LIMIT_EPSILON}）；"
            "剔除 N/C 新股与上市首日；涨停行业分布与 sample 只统计 clean（剔 ST），跌停剔 ST；"
            f"大盘三档＝{BENCHMARK_INDEX} 当日涨跌幅（企稳>{stabilize_above:g}／非极端弱 {extreme_weak_at_or_below:g}%~0／极端弱 ≤{extreme_weak_at_or_below:g}%，边界见 params/entry.json#benchmark_tiers）。"
        ),
    }

def sector_statistics(
    daily: Any,
    target_date: str,
    sectors: list[str],
    candidates: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    industry_by_code: dict[str, str],
    name_by_code: dict[str, str],
    parameters: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    sector_heat = parameters["sector_heat"]
    short_period, long_period = sector_heat["trend_ma_periods"]
    volume_window = sector_heat["volume_ratio_window_days"]
    daily_with_sector = daily.assign(sector=daily["ts_code"].map(industry_by_code))
    candidate_count: dict[str, int] = defaultdict(int)
    signal_count: dict[str, int] = defaultdict(int)
    for item in candidates:
        candidate_count[item["industry"]] += 1
    for item in signals:
        signal_count[item["industry"]] += 1

    limit_up_total: dict[str, int] = defaultdict(int)
    limit_up_clean: dict[str, int] = defaultdict(int)
    for code, records in daily.groupby("ts_code"):
        code = str(code)
        today = records.loc[records["trade_date"] == target_date]
        if today.empty:
            continue
        name = name_by_code.get(code, "")
        if is_new_or_first_day(name, "", target_date):
            continue
        if not hit_limit(float(today.iloc[-1]["pct_chg"]), limit_pct(code, name)):
            continue
        sector = industry_by_code.get(code, "")
        limit_up_total[sector] += 1
        if not is_st(name):
            limit_up_clean[sector] += 1

    rows: list[dict[str, Any]] = []
    for sector in sectors:
        sector_daily = daily_with_sector.loc[daily_with_sector["sector"] == sector]
        grouped = sector_daily.groupby("trade_date", sort=True)
        pct_series = [float(value) for value in grouped["pct_chg"].mean().tolist()]
        volumes = [float(value) for value in grouped["vol"].sum().tolist()]
        short_ma = moving_average(pct_series, short_period)
        long_ma = moving_average(pct_series, long_period)
        prior_volumes = volumes[-volume_window - 1 : -1]
        volume_ratio = None
        if len(prior_volumes) == volume_window and sum(prior_volumes) > 0:
            volume_ratio = volumes[-1] / (sum(prior_volumes) / len(prior_volumes))
        trend = "—"
        if short_ma is not None and long_ma is not None:
            trend = "多头排列" if short_ma > long_ma else "空头"
        rows.append(
            {
                "industry": sector,
                "candidates": candidate_count[sector],
                "signals": signal_count[sector],
                "short_ma_pct": round(short_ma, 2) if short_ma is not None else None,
                "long_ma_pct": round(long_ma, 2) if long_ma is not None else None,
                "trend": trend,
                "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
                "limit_up_count": limit_up_total[sector],
                "limit_up_clean": limit_up_clean[sector],
            }
        )
    return rows

def op_sector_heat(
    target_api_date: str,
    directory_date: str,
    parameters: dict[str, dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    candidate_document = load_process_document(directory_date, "full_market_candidate.json")
    candidates = candidate_document.get("candidates", [])
    sectors = sorted({item["industry"] for item in candidates if item.get("industry")})
    client = get_client()
    trade_days = fetch_trade_days(client, market_daily_start(target_api_date, parameters), target_api_date)
    if target_api_date not in trade_days:
        raise ValueError(f"{directory_date} 不是交易日，无板块热度事实")
    previous_trade_date = trade_days[trade_days.index(target_api_date) - 1] if trade_days.index(target_api_date) > 0 else None
    daily = fetch_daily_market(client, trade_days, fields="ts_code,trade_date,close,high,vol,amount,pct_chg")
    if daily.empty:
        raise RuntimeError("未获取到板块热度所需日线数据")
    industry_by_code, name_by_code, list_date_by_code = fetch_stock_info(client)
    daily_by_code = {str(code): records.sort_values("trade_date") for code, records in daily.groupby("ts_code")}
    signals = signalize(daily_by_code, candidates, target_api_date, parameters["entry"])
    rows = sector_statistics(daily, target_api_date, sectors, candidates, signals, industry_by_code, name_by_code, parameters)
    environment = build_sector_environment(
        daily, target_api_date, previous_trade_date, industry_by_code, name_by_code, list_date_by_code, parameters
    )
    heat_payload = artifact(
        "sector_heat",
        directory_date,
        parameters,
        (
            "short/long_ma_pct＝板块成分股当日平均涨幅的 "
            f"{parameters['sector_heat']['trend_ma_periods'][0]}/{parameters['sector_heat']['trend_ma_periods'][1]} 日均值；"
            f"trend＝short>long 记「多头排列」否则「空头」；volume_ratio＝板块当日总成交量 ÷ 前 "
            f"{parameters['sector_heat']['volume_ratio_window_days']} 日均量；涨停为分板精确口径（clean 剔 ST）。"
        ),
        {
            "params": {key: value for key, value in parameters["sector_heat"].items() if key != "schema_version"},
            "stats": {
                "total_candidates": len(candidates),
                "candidate_sectors": len(sectors),
                "signals": len(signals),
                "max_board_count": environment["highest_board"]["count"],
            },
            "candidate_sectors": sectors,
            "sectors": rows,
        },
    )
    environment_payload = artifact(
        "sector_environment",
        directory_date,
        parameters,
        environment["note"],
        {
            "market": environment["market"],
            "limit_up_by_industry": environment["limit_up_by_industry"],
            "limit_up_sample": environment["limit_up_sample"],
            "highest_board": environment["highest_board"],
            "benchmark": environment["benchmark"],
        },
    )
    if dry_run:
        return {"ok": True, "dry_run": True, "artifact": "sector_heat", "date": directory_date, "document": heat_payload, "environment": environment_payload}
    heat_path = write_json(process_dir(directory_date, create=True) / "sector_heat.json", heat_payload)
    environment_path = write_json(process_dir(directory_date, create=True) / "sector_environment.json", environment_payload)
    return {
        "ok": True,
        "artifact": "sector_heat",
        "date": directory_date,
        "paths": [heat_path, environment_path],
        "logical_paths": [logical_process_path(directory_date, "sector_heat.json"), logical_process_path(directory_date, "sector_environment.json")],
        "stats": heat_payload["stats"],
    }

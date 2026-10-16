#!/usr/bin/env python3
"""采集当日涨停行业分布事实（v4：供信号与情绪面使用，不用于状态机）。"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any

import tushare as ts

from runtime_support import SYSTEM_ID, artifact_path, load_parameters, normalize_date, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="红利科创 ETF 双网格板块事实采集")
    parser.add_argument("--date", required=True, help="运行日期，YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true", help="只输出结果，不写过程资料")
    return parser.parse_args()


def tushare_client() -> Any:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    ts.set_token(token)
    return ts.pro_api()


def is_limit_up(ts_code: str, pct_change: float) -> bool:
    """涨停判定：北交所 .BJ 30%、双创 20%、主板 10%（阈值沿用本脚本 0.298/0.198/0.098 惯例）。

    ⚠️ 北交所必须用 .BJ 后缀判定：现行号段为 920xxx，前缀匹配（8/4）会漏判，
    把 +10%~+29.5% 的北交所票误计为涨停（2026-09-27 修正）。
    """
    if ts_code.endswith(".BJ"):
        threshold = 0.298
    elif ts_code.split(".", 1)[0].startswith(("30", "68")):
        threshold = 0.198
    else:
        threshold = 0.098
    return pct_change >= threshold * 100


def main() -> None:
    args = parse_args()
    api_date, directory_date = normalize_date(args.date)
    parameters = load_parameters()
    keywords = parameters["sector_classification"]["technology_industry_keywords"]
    pro = tushare_client()
    daily = pro.daily(trade_date=api_date, fields="ts_code,pct_chg")
    basic = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name,industry")
    if daily is None or daily.empty:
        raise ValueError(f"无 {api_date} 全市场日线数据")
    industry_by_code = {
        str(row["ts_code"]): {"name": str(row["name"]), "industry": str(row["industry"] or "未知")}
        for row in basic.to_dict("records")
    } if basic is not None else {}

    sectors: dict[str, dict[str, Any]] = {}
    limit_up_count = 0
    for row in daily.to_dict("records"):
        pct_change = float(row.get("pct_chg") or 0.0)
        ts_code = str(row["ts_code"])
        if not is_limit_up(ts_code, pct_change):
            continue
        limit_up_count += 1
        profile = industry_by_code.get(ts_code, {"name": ts_code, "industry": "未知"})
        industry = profile["industry"]
        sector = sectors.setdefault(industry, {"industry": industry, "limit_up_count": 0, "sample_stocks": []})
        sector["limit_up_count"] += 1
        if len(sector["sample_stocks"]) < 3:
            sector["sample_stocks"].append({"ts_code": ts_code, "name": profile["name"], "pct_change_ratio": round(pct_change / 100, 6)})

    ranked = sorted(sectors.values(), key=lambda sector: sector["limit_up_count"], reverse=True)
    for sector in ranked:
        sector["is_technology"] = any(keyword in sector["industry"] for keyword in keywords)
    technology_limit_up_count = sum(sector["limit_up_count"] for sector in ranked if sector["is_technology"])
    output = {
        "date": directory_date,
        "system_id": SYSTEM_ID,
        "artifact": "sector_facts",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_trade_date": api_date,
        "classification_parameter_version": parameters["sector_classification"]["schema_version"],
        "limit_up": {
            "stock_count": limit_up_count,
            "sector_count": len(ranked),
            "technology_stock_count": technology_limit_up_count,
            "technology_stock_ratio": round(technology_limit_up_count / limit_up_count, 8) if limit_up_count else 0.0,
        },
        "top_sectors": ranked[:10],
    }
    if args.dry_run:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    path = artifact_path(directory_date, "sector_facts.json")
    write_json(path, output)
    print(path)


if __name__ == "__main__":
    main()
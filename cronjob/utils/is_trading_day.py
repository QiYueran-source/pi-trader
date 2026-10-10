#!/opt/hermes/.venv/bin/python3
"""
交易日判断工具。

用法：
  is_trading_day.py                                 # 查今天
  is_trading_day.py --date 2026-06-15               # 查指定日期
  is_trading_day.py --date 2026-06-15 --next        # 查指定日期后的下个交易日

输出格式（一行 pipe 分隔）：
  TRADING_DAY|2026-06-12|2026-06-12
  NON_TRADING_DAY|2026-06-13(周六)|2026-06-15(周一)

第一字段：TRADING_DAY 或 NON_TRADING_DAY
第二字段：当前日期（含星期备注）
第三字段：最近的下一个交易日（含星期备注）

异常：TUSHARE_TOKEN 未配 / 网络不通 / trade_cal 返回空
      → 直接抛异常退出，不静默处理
"""

import argparse
import os
import sys
from datetime import date, datetime, timedelta

import tushare as ts
from dotenv import load_dotenv

# ── 初始化 ─────────────────────────────────────────────
TRADE_ENV_FILE = "/hermes-trader/.env"
if os.path.exists(TRADE_ENV_FILE):
    load_dotenv(TRADE_ENV_FILE)

token = os.environ.get("TUSHARE_TOKEN", "").strip()
if not token:
    sys.exit("FATAL: TUSHARE_TOKEN 未配置（已尝试加载 /hermes-trader/.env）")

ts.set_token(token)
pro = ts.pro_api(token)

WEEKDAY = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ── 工具函数 ───────────────────────────────────────────
def date_with_weekday(d: date) -> str:
    """返回 '2026-06-13(周六)' 格式"""
    return f"{d.strftime('%Y-%m-%d')}({WEEKDAY[d.weekday()]})"


def fetch_calendar(start: str, end: str):
    """调用 Tushare trade_cal，返回 is_open=1 的日期列表"""
    df = pro.trade_cal(
        exchange="SSE",
        start_date=start,
        end_date=end,
        fields="cal_date,is_open",
    )
    if df is None or len(df) == 0:
        raise RuntimeError(f"trade_cal 返回空，范围 {start} ~ {end}")
    return sorted(df[df["is_open"] == 1]["cal_date"].tolist())


def find_next_trading_day(d: date) -> str:
    """从 d 之后开始往后找第一个交易日（不含当天），返回带星期备注的字符串"""
    start = (d + timedelta(days=1)).strftime("%Y%m%d")
    end = (d + timedelta(days=14)).strftime("%Y%m%d")  # 14天窗口足够覆盖长假
    trading_days = fetch_calendar(start, end)
    if not trading_days:
        raise RuntimeError(f"{start} 之后 14 天内无交易日")
    next_day = datetime.strptime(trading_days[0], "%Y%m%d").date()
    return date_with_weekday(next_day)


# ── 主逻辑 ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="交易日判断工具")
    parser.add_argument("--date", type=str, default=None,
                        help="指定日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--next", action="store_true",
                        help="同时输出下一个交易日")
    args = parser.parse_args()

    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        d = date.today()

    date_str = d.strftime("%Y%m%d")
    trading_days = fetch_calendar(date_str, date_str)

    is_trading = len(trading_days) > 0
    today_label = date_with_weekday(d)

    if is_trading:
        if args.next:
            next_label = find_next_trading_day(d)
        else:
            next_label = date_with_weekday(d)
        print(f"TRADING_DAY|{today_label}|{next_label}")
    else:
        next_label = find_next_trading_day(d)
        print(f"NON_TRADING_DAY|{today_label}|{next_label}")


if __name__ == "__main__":
    main()

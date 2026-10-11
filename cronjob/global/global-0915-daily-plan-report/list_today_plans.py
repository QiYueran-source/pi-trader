#!/usr/bin/env python3
"""
扫描指定日期下的交易计划文件。

用法：
  list_today_plans.py                           # 扫今天
  list_today_plans.py --date 2026-06-15         # 扫指定日期

输出：每行一个计划文件的 knowledge 相对路径
  有计划 → 列出路径
  无计划 / 目录不存在 → 无输出，exit 0
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

TRADE_PLAN_DIR = Path("/pi-trader/knowledge/交易/交易计划")


def main():
    parser = argparse.ArgumentParser(description="扫描当日交易计划文件")
    parser.add_argument("--date", type=str, default=None,
                        help="指定日期 YYYY-MM-DD，默认今天")
    args = parser.parse_args()

    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        d = date.today()

    plan_dir = TRADE_PLAN_DIR / d.strftime("%Y-%m-%d")
    if not plan_dir.exists():
        return  # 无声退出

    files = sorted(plan_dir.glob("*.md"))
    for f in files:
        # 输出 knowledge 相对路径
        print(f.relative_to(Path("/pi-trader/knowledge")))


if __name__ == "__main__":
    main()

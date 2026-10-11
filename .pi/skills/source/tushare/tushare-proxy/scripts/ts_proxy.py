#!/opt/hermes/.venv/bin/python3
# -*- coding: utf-8 -*-
"""
tushare-proxy 核心封装：promax + RDS 两个第三方 tushare 代理通道的统一入口。

- ts(a, **p)     : promax 通道（全 tushare pro 接口，含 stk_mins 1min，绕过官方限频）
- rds(a, **p)    : RDS 通道（datahubco 中转，速度快）
- get(a, **p)    : 统一入口，默认 auto 优先 promax，失败自动切 RDS
- fetch_1min     : 按交易日批量拉取 1min 分钟线（断点续传 + 节流）

key 从本技能目录下的 .env 读取（不进项目 env、不进 git）。
"""
import os
import time
import warnings
from pathlib import Path

from dotenv import load_dotenv

# 定位本技能目录下的 .env（不依赖调用方 cwd）
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_FILE)

# RDS 走公网 HTTP，必须绕过代理
os.environ.setdefault("NO_PROXY", "*")

# 证书警告（promax 需 verify=False）
warnings.filterwarnings("ignore")

import requests  # noqa: E402

PROMAX_URL = os.environ.get("TUSHARE_PROMAX_URL", "https://pcd.mobcvb.cn/tushare/pro")
PROMAX_KEY = os.environ.get("TUSHARE_PROMAX_KEY", "")
RDS_URL = os.environ.get("TUSHARE_RDS_URL", "http://datahubco.com/app-api/openapi/v1/tushare")
RDS_KEY = os.environ.get("TUSHARE_RDS_KEY", "")


# ---------------------------------------------------------------------------
# 底层通道
# ---------------------------------------------------------------------------
def ts(a, **p):
    """promax 通道：GET {PROMAX_URL}/{a}?params，返回 tushare 同构 dict。"""
    if not PROMAX_KEY:
        raise RuntimeError("TUSHARE_PROMAX_KEY 未配置（检查 skills/data/tushare-proxy/.env）")
    r = requests.get(
        f"{PROMAX_URL}/{a}",
        params=p,
        headers={"X-API-Key": PROMAX_KEY},
        verify=False,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def rds(a, **p):
    """RDS 通道：GET {RDS_URL}/{a}?params，返回 tushare 同构 dict。"""
    if not RDS_KEY:
        raise RuntimeError("TUSHARE_RDS_KEY 未配置（检查 skills/data/tushare-proxy/.env）")
    r = requests.get(
        f"{RDS_URL}/{a}",
        params=p,
        headers={"X-API-Key": RDS_KEY},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _parse(raw, df=True):
    """把 {code:0, data:{fields, items}} 解析为 DataFrame 或 list[dict]。"""
    if not isinstance(raw, dict) or raw.get("code") != 0:
        raise RuntimeError(f"接口返回异常: {raw}")
    d = raw.get("data") or {}
    fields, items = d.get("fields", []), d.get("items", [])
    if df:
        import pandas as pd

        return pd.DataFrame(items, columns=fields) if items else pd.DataFrame(columns=fields)
    return [dict(zip(fields, row)) for row in items]


def _call(fn, a, retries, **p):
    last_err = None
    for i in range(retries + 1):
        try:
            return _parse(fn(a, **p))
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(0.8 * (i + 1))
    raise last_err


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------
def get(a, channel="auto", retries=2, **p):
    """统一数据入口。

    channel: auto（默认，优先 promax 失败切 RDS）| promax | rds
    返回 pandas DataFrame；需要 dict 列表时用 get(..., df=False)。
    """
    if channel == "promax":
        return _call(ts, a, retries, **p)
    if channel == "rds":
        return _call(rds, a, retries, **p)
    # auto：promax 优先，失败切 RDS
    try:
        return _call(ts, a, retries, **p)
    except Exception:  # noqa: BLE001
        return _call(rds, a, retries, **p)


def get_dict(a, channel="auto", **p):
    """返回 list[dict] 形态（内部转 DataFrame 再还原，保证同构解析逻辑唯一）。"""
    df = get(a, channel=channel, **p)
    return df.to_dict("records")


# ---------------------------------------------------------------------------
# 1min 批量拉取（回测场景核心）
# ---------------------------------------------------------------------------
def fetch_1min(ts_code, trade_dates, freq="1min", sleep=0.5, resume_file=None):
    """按交易日列表批量拉取分钟线。

    参数:
        ts_code     : 带后缀代码，如 '000533.SZ'
        trade_dates : 交易日字符串列表 ['20260701', ...]
        freq        : '1min' / '5min' / '15min' / '30min' / '60min'
        sleep       : 每请求间隔秒数（默认 0.5，实测 4.2s/次 时 1min 全量可用）
        resume_file : 断点续传进度文件路径（可选）

    返回:
        DataFrame，列同 stk_mins（ts_code/trade_time/...），按时间升序。
    """
    done = set()
    if resume_file and os.path.exists(resume_file):
        done = set(x.strip() for x in open(resume_file, encoding="utf-8") if x.strip())
    frames = []
    todo = [d for d in trade_dates if d not in done]
    for i, d in enumerate(todo, 1):
        try:
            df = get(
                "stk_mins", ts_code=ts_code, freq=freq, start_date=d, end_date=d, retries=1
            )
            if len(df):
                frames.append(df)
            done.add(d)
            if resume_file:
                with open(resume_file, "a", encoding="utf-8") as f:
                    f.write(d + "\n")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] {d} 失败: {e}")
        if i < len(todo):
            time.sleep(sleep)
    if not frames:
        return None
    import pandas as pd

    out = pd.concat(frames, ignore_index=True)
    return out.sort_values("trade_time") if "trade_time" in out.columns else out


if __name__ == "__main__":
    # 冒烟测试：两条通道各拉一条
    print("== promax daily ==")
    d1 = ts("daily", ts_code="000001.SZ", start_date="20260701", end_date="20260703")
    print(_parse(d1).to_string())
    print("== RDS stock-basic ==")
    d2 = rds("stock-basic", limit=3)
    print(_parse(d2).to_string())
    print("OK")

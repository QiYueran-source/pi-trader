#!/opt/hermes/.venv/bin/python3
"""
Tushare 数据缓存工具。

用法：
  # 查缓存（有则返回JSON，无则返回空）
  /opt/hermes/.venv/bin/python3 ts_cache.py get <cache_key>

  # 写入缓存
  /opt/hermes/.venv/bin/python3 ts_cache.py set <cache_key> '<json_data>'
  
  # 查缓存，没有的话执行 Python 表达式拉数据并缓存
  /opt/hermes/.venv/bin/python3 ts_cache.py fetch <cache_key> '<python_expression>'

缓存路径：/tmp/tushare_cache/{cache_key}.json
缓存有效期：默认当天（按自然日过期）
"""

import json
import os
import sys
import hashlib
from datetime import date

CACHE_DIR = "/tmp/tushare_cache"


def _ensure_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _key_to_path(cache_key: str) -> str:
    # 将 cache_key 哈希为文件名，避免特殊字符问题
    h = hashlib.md5(cache_key.encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{h}.json")


def _is_fresh(path: str) -> bool:
    """检查缓存文件是否是今天的"""
    today = date.today().isoformat()
    try:
        with open(path) as f:
            meta = json.load(f)
        return meta.get("date") == today
    except (json.JSONDecodeError, FileNotFoundError, KeyError):
        return False


def cmd_get(cache_key: str):
    """查缓存，存在且当天有效则输出JSON，否则输出空"""
    path = _key_to_path(cache_key)
    if os.path.exists(path) and _is_fresh(path):
        with open(path) as f:
            data = json.load(f)
        print(json.dumps(data["data"]))
    else:
        print("")


def cmd_set(cache_key: str, json_data: str):
    """写入缓存"""
    _ensure_dir()
    path = _key_to_path(cache_key)
    payload = {
        "date": date.today().isoformat(),
        "key": cache_key,
        "data": json.loads(json_data),
    }
    with open(path, "w") as f:
        json.dump(payload, f, ensure_ascii=False)
    print("CACHED")


def cmd_fetch(cache_key: str, expr: str):
    """
    查缓存，有则直接返回；没有则执行 Python 表达式拉数据，写入缓存后再输出。
    expr 是返回 dict 或 list 的 Python 表达式（可执行环境已导入 ts + pro）。
    用法示例：
      ts_cache.py fetch "index_sh_20260709" "pro.index_daily(ts_code='000001.SH', start_date='20260703', end_date='20260709').to_dict('records')"
    """
    path = _key_to_path(cache_key)
    if os.path.exists(path) and _is_fresh(path):
        with open(path) as f:
            data = json.load(f)
        print(json.dumps(data["data"], ensure_ascii=False))
        return

    # 没缓存，拉取
    _ensure_dir()
    import tushare as ts
    from dotenv import load_dotenv
    load_dotenv("/hermes-trader/.env")
    pro = ts.pro_api()

    result = eval(expr)
    payload = {
        "date": date.today().isoformat(),
        "key": cache_key,
        "data": result,
    }
    with open(path, "w") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: ts_cache.py <get|set|fetch> <cache_key> [data_or_expr]")
        sys.exit(1)

    action = sys.argv[1]
    cache_key = sys.argv[2]

    if action == "get":
        cmd_get(cache_key)
    elif action == "set":
        if len(sys.argv) < 4:
            print("set 需要第3个参数: JSON data")
            sys.exit(1)
        cmd_set(cache_key, sys.argv[3])
    elif action == "fetch":
        if len(sys.argv) < 4:
            print("fetch 需要第3个参数: Python 表达式")
            sys.exit(1)
        cmd_fetch(cache_key, sys.argv[3])
    else:
        print(f"未知动作: {action}")
        sys.exit(1)

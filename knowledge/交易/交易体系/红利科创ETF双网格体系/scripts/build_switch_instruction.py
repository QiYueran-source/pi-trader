#!/usr/bin/env python3
"""根据已固化的状态迁移和仓位快照生成切换执行指令。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any

from runtime_support import SYSTEM_ID, artifact_path, load_parameters, normalize_date, read_json, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成红利科创 ETF 双网格状态切换指令")
    parser.add_argument("--date", required=True, help="运行日期，YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true", help="只输出结果，不写过程资料")
    return parser.parse_args()


def position_shares(snapshot: dict[str, Any] | None, instrument_id: str) -> int | None:
    if not isinstance(snapshot, dict):
        return None
    positions = snapshot.get("positions")
    if not isinstance(positions, dict) or not isinstance(positions.get(instrument_id), dict):
        return None
    shares = positions[instrument_id].get("shares")
    return int(shares) if isinstance(shares, int) and shares >= 0 else None


def action(instrument_id: str, action_type: str, shares: int | None, reason: str) -> dict[str, Any]:
    return {
        "instrument_id": instrument_id,
        "action": action_type,
        "shares": shares,
        "reason": reason,
        "requires_manual_order_details": True,
    }


def main() -> None:
    args = parse_args()
    _, directory_date = normalize_date(args.date)
    parameters = load_parameters()
    before = read_json(artifact_path(directory_date, "state_before.json"))
    after = read_json(artifact_path(directory_date, "state_after.json"))
    transition = after.get("transition")
    if not isinstance(transition, dict):
        raise ValueError("state_after.json 缺少 transition")
    source = transition["from_state"]
    target = transition["to_state"]
    instructions: list[dict[str, Any]] = []

    if transition["decision"] == "transition":
        current_positions = before.get("position_snapshot")
        if source == "normal" and target == "bull":
            instructions.append(action("dividend", "sell_all", position_shares(current_positions, "dividend"), "进入 bull，按状态约束清空红利仓位"))
        elif source == "normal" and target == "bear":
            instructions.append(action("growth", "sell_all", position_shares(current_positions, "growth"), "进入 bear，按状态约束清空双创仓位"))
        elif source == "bull" and target == "normal":
            instructions.append(action("growth", "sell_all", position_shares(current_positions, "growth"), "退出 bull，恢复 normal 前清空双创趋势仓位"))
            instructions.append(action("dividend", "restore_snapshot", position_shares(after.get("restoration_reference_positions"), "dividend"), "恢复进入 bull 前的红利仓位快照"))
        elif source == "bear" and target == "normal":
            instructions.append(action("dividend", "sell_all", position_shares(current_positions, "dividend"), "退出 bear，恢复 normal 前清空红利趋势仓位"))
            instructions.append(action("growth", "restore_snapshot", position_shares(after.get("restoration_reference_positions"), "growth"), "恢复进入 bear 前的双创仓位快照"))
        else:
            raise ValueError(f"未定义的状态切换: {source} -> {target}")

    target_mode = parameters["state_machine"]["states"][target]
    output = {
        "date": directory_date,
        "system_id": SYSTEM_ID,
        "artifact": "switch_instruction",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "transition": {
            "decision": transition["decision"],
            "from_state": source,
            "to_state": target,
        },
        "order_instructions": instructions,
        "condition_order_modes": {
            instrument_id: {
                "buy_enabled": mode["buy_enabled"],
                "sell_enabled": mode["sell_enabled"],
            }
            for instrument_id, mode in target_mode.items()
            if instrument_id in {"dividend", "growth"}
        },
        "notice": "本文件是人工券商执行指令，不直接下单；价格、时点与成交结果必须在交易计划和执行记录中确认。",
    }
    if args.dry_run:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    path = artifact_path(directory_date, "switch_instruction.json")
    write_json(path, output)
    print(path)


if __name__ == "__main__":
    main()
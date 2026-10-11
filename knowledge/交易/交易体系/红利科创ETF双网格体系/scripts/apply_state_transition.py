#!/usr/bin/env python3
"""校验并固化 Agent 已作出的状态迁移决策，不负责市场判断。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime_support import SYSTEM_ID, artifact_path, load_parameters, load_prior_state, normalize_date, read_json, write_json


REQUIRED_PROPOSAL_FIELDS = {
    "date",
    "system_id",
    "from_state",
    "to_state",
    "decision",
    "confidence",
    "evidence_summary",
    "conflict_resolution",
    "decided_by",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="固化红利科创 ETF 双网格状态迁移")
    parser.add_argument("--date", required=True, help="运行日期，YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--proposal", required=True, help="Agent 状态迁移提案 JSON")
    parser.add_argument("--positions", required=True, help="账户持仓事实 JSON")
    parser.add_argument("--dry-run", action="store_true", help="只校验并输出，不写过程资料")
    return parser.parse_args()


def load_proposal(path: str, directory_date: str) -> dict[str, Any]:
    proposal = read_json(Path(path))
    missing = REQUIRED_PROPOSAL_FIELDS - proposal.keys()
    if missing:
        raise ValueError(f"状态迁移提案缺少字段: {', '.join(sorted(missing))}")
    if proposal["date"] != directory_date or proposal["system_id"] != SYSTEM_ID:
        raise ValueError("状态迁移提案的 date 或 system_id 不匹配")
    if proposal["decision"] not in {"keep", "transition"}:
        raise ValueError("状态迁移提案 decision 必须为 keep 或 transition")
    if proposal["confidence"] not in {"high", "medium", "low"}:
        raise ValueError("状态迁移提案 confidence 必须为 high、medium 或 low")
    if not isinstance(proposal["evidence_summary"], list) or not proposal["evidence_summary"]:
        raise ValueError("状态迁移提案 evidence_summary 必须为非空数组")
    return proposal


def load_positions(path: str) -> dict[str, Any]:
    document = read_json(Path(path))
    if not isinstance(document.get("positions"), dict):
        raise ValueError("持仓事实必须包含 positions 对象")
    return document


def main() -> None:
    args = parse_args()
    _, directory_date = normalize_date(args.date)
    parameters = load_parameters()
    state_config = parameters["state_machine"]
    proposal = load_proposal(args.proposal, directory_date)
    prior_state = load_prior_state(directory_date)
    positions = load_positions(args.positions)
    current_state = prior_state["state"]

    if proposal["from_state"] != current_state:
        raise ValueError(f"提案前置状态不匹配: 当前为 {current_state}，提案为 {proposal['from_state']}")
    target_state = proposal["to_state"]
    if target_state not in state_config["states"]:
        raise ValueError(f"提案目标状态无效: {target_state}")
    is_transition = proposal["decision"] == "transition"
    if is_transition and target_state == current_state:
        raise ValueError("transition 决策不能保持原状态")
    if not is_transition and target_state != current_state:
        raise ValueError("keep 决策的目标状态必须等于当前状态")
    if is_transition and target_state not in state_config["allowed_transitions"][current_state]:
        raise ValueError(f"不允许状态迁移: {current_state} -> {target_state}")

    before = {
        "date": directory_date,
        "system_id": SYSTEM_ID,
        "artifact": "state_before",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "state": current_state,
        "source_state": prior_state.get("source", "prior_snapshot"),
        "position_snapshot": positions,
    }
    after = {
        "date": directory_date,
        "system_id": SYSTEM_ID,
        "artifact": "state_after",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "state": target_state,
        "transition": {
            "decision": proposal["decision"],
            "from_state": current_state,
            "to_state": target_state,
            "confidence": proposal["confidence"],
            "evidence_summary": proposal["evidence_summary"],
            "conflict_resolution": proposal["conflict_resolution"],
            "decided_by": proposal["decided_by"],
            "proposal_source": str(Path(args.proposal)),
        },
    }
    if current_state == "normal" and target_state in {"bull", "bear"}:
        after["trend_entry_position_snapshot"] = positions
    elif current_state in {"bull", "bear"} and target_state == "normal":
        after["restoration_reference_positions"] = prior_state.get("trend_entry_position_snapshot")
    elif prior_state.get("trend_entry_position_snapshot"):
        after["trend_entry_position_snapshot"] = prior_state["trend_entry_position_snapshot"]

    output = {"state_before": before, "state_after": after}
    if args.dry_run:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    write_json(artifact_path(directory_date, "state_before.json"), before)
    write_json(artifact_path(directory_date, "state_after.json"), after)
    print(json.dumps({"state_before": str(artifact_path(directory_date, "state_before.json")), "state_after": str(artifact_path(directory_date, "state_after.json"))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
"""Autonomous 4th-Turn Compounder & 50-Step 4-Hour Cron Planner.
Every 4 turns, summarizes the previous 3 turns into a permanent NouGen shard,
and plans the next 4-hour execution roadmap across the fleet.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from datetime import datetime, timezone

STATE_FILE = Path.home() / ".nougen" / "state" / "turn_compounding_state.json"


def record_turn(turn_summary: str) -> dict:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = {"turn_count": 0, "recent_turns": []}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    state["turn_count"] = state.get("turn_count", 0) + 1
    state.setdefault("recent_turns", []).append({
        "turn": state["turn_count"],
        "summary": turn_summary,
        "timestamp": time.time()
    })

    is_4th = (state["turn_count"] % 4 == 0)
    return {
        "turn_count": state["turn_count"],
        "is_4th_turn": is_4th,
        "history_len": len(state["recent_turns"])
    }

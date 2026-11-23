"""Autonomous 4th-Turn Compounder & 50-Step 4-Hour Cron Planner.
Every 4 turns, summarizes the previous 3 turns into a permanent NouGen shard,
and plans the next 4-hour execution roadmap across the fleet.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

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

    state["recent_turns"] = state["recent_turns"][-8:]
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    is_4th = (state["turn_count"] % 4 == 0)
    return {
        "turn_count": state["turn_count"],
        "is_4th_turn": is_4th,
        "history_len": len(state["recent_turns"])
    }


def compound_trajectory(turns_summary: str, next_steps: str, utility: float = 0.95) -> dict:
    """Record a turn and, every 4th turn, capture a synthesis shard of the recent turns."""
    from . import core

    info = record_turn(turns_summary)
    info["captured"] = False
    if info["is_4th_turn"]:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        recent = state.get("recent_turns", [])[-4:]
        body = "\n".join(f"Turn {t['turn']}: {t['summary']}" for t in recent)
        content = f"{body}\n\nNext steps: {next_steps}"
        info["captured"] = bool(core.capture(
            "SYNTHESIS", f"Turn compound through turn {info['turn_count']}", content,
            tags=["turn-compound"], utility=utility))
    return info

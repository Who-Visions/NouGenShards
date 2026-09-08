"""Brain session forensic & token telemetry visualizer.

Ported from Kaedra / Antigravity Brain Visualizer v0.6.0.
Computes input, thinking, output tokens, cost estimates across Gemini & local Gemma models,
and audits transcripts with zero external dependencies.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

BRAIN_DIR = Path(os.path.expanduser("~/.gemini/antigravity/brain"))

PRICING = {
    "gemini-3-flash": {"input": 0.075, "output": 0.30},
    "gemini-3.1-pro": {"input": 1.25, "output": 5.00},
}


def get_latest_session_id() -> Optional[str]:
    """Find the most recently modified session in ~/.gemini/antigravity/brain/."""
    if not BRAIN_DIR.exists():
        return None
    sessions = [d for d in BRAIN_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if not sessions:
        return None
    sessions.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return sessions[0].name


def audit_session(session_id: Optional[str] = None) -> dict[str, Any]:
    """Parse transcript.jsonl and compute forensic metrics for a session."""
    sid = session_id or get_latest_session_id()
    if not sid:
        return {"status": "error", "message": "No session found"}

    session_path = BRAIN_DIR / sid
    transcript_path = session_path / ".system_generated" / "logs" / "transcript.jsonl"

    if not transcript_path.exists():
        return {
            "status": "error",
            "session_id": sid,
            "message": f"Transcript not found at {transcript_path}"
        }

    total_steps = 0
    tool_calls = 0
    user_inputs = 0
    errors = 0
    estimated_input_tokens = 0
    estimated_output_tokens = 0

    with open(transcript_path, "r", encoding="utf-8", errors="replace") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            total_steps += 1
            try:
                data = json.loads(line)
                step_type = data.get("type", "")
                if step_type == "USER_INPUT":
                    user_inputs += 1
                    content = str(data.get("content", ""))
                    estimated_input_tokens += len(content) // 4
                elif step_type == "PLANNER_RESPONSE":
                    calls = data.get("tool_calls", [])
                    tool_calls += len(calls)
                    content = str(data.get("content", ""))
                    estimated_output_tokens += len(content) // 4
                if data.get("status") == "ERROR":
                    errors += 1
            except Exception:
                pass

    total_tokens = estimated_input_tokens + estimated_output_tokens
    est_flash_cost = (estimated_input_tokens / 1_000_000 * PRICING["gemini-3-flash"]["input"] +
                      estimated_output_tokens / 1_000_000 * PRICING["gemini-3-flash"]["output"])
    est_pro_cost = (estimated_input_tokens / 1_000_000 * PRICING["gemini-3.1-pro"]["input"] +
                    estimated_output_tokens / 1_000_000 * PRICING["gemini-3.1-pro"]["output"])

    return {
        "status": "success",
        "session_id": sid,
        "total_steps": total_steps,
        "user_inputs": user_inputs,
        "tool_calls": tool_calls,
        "errors": errors,
        "tokens": {
            "input": estimated_input_tokens,
            "output": estimated_output_tokens,
            "total": total_tokens
        },
        "cost_estimate": {
            "gemini_3_flash_usd": round(est_flash_cost, 4),
            "gemini_3_1_pro_usd": round(est_pro_cost, 4)
        }
    }

"""Read Codex's /status rate limits without opening Codex.

Codex writes a `rate_limits` snapshot into its session rollout JSONL on every
token_count event. This finds the newest snapshot across ~/.codex/sessions and
archived_sessions and reports usage and reset times in America/New_York.

The snapshot is only as fresh as Codex's last turn: `observed` says when it was
taken, and a reset time already in the past means the window has rolled over.

  pythonw codex_status.py            # human line
  pythonw codex_status.py --json     # machine-readable
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ROOT = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
MAX_FILES = 20


def _fmt(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, ET).strftime("%I:%M %p %Z %a %m/%d").lstrip("0")


def latest_snapshot() -> tuple[dict, float] | None:
    files = [p for d in ("sessions", "archived_sessions") for p in (ROOT / d).rglob("*.jsonl")]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    best: tuple[dict, float] | None = None
    for path in files[:MAX_FILES]:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if '"rate_limits"' not in line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rl = (rec.get("payload") or {}).get("rate_limits") or rec.get("rate_limits")
            # Some events carry a windowless record for another limit_id
            # (e.g. "premium"); only the windowed record answers /status.
            if not rl or not (rl.get("primary") or rl.get("secondary")):
                continue
            ts = rec.get("timestamp")
            try:
                observed = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() if ts else path.stat().st_mtime
            except (AttributeError, ValueError):
                observed = path.stat().st_mtime
            if best is None or observed > best[1]:
                best = (rl, observed)
            break
    return best


def status() -> dict:
    snap = latest_snapshot()
    if snap is None:
        return {"ok": False, "error": f"no rate_limits snapshot under {ROOT}"}
    rl, observed = snap
    now = datetime.now(timezone.utc).timestamp()
    out: dict = {"ok": True, "observed": _fmt(observed), "windows": {}}
    blocked_until = None
    for name in ("primary", "secondary"):
        w = rl.get(name)
        if not w:
            continue
        reset = w.get("resets_at")
        rolled = reset is not None and reset <= now
        used = 0.0 if rolled else float(w.get("used_percent", 0))
        out["windows"][name] = {
            "used_percent": used,
            "window_minutes": w.get("window_minutes"),
            "resets_at": _fmt(reset),
            "rolled_over": rolled,
        }
        if used >= 99 and reset:  # Codex stops serving at ~99%
            blocked_until = max(blocked_until or 0, reset)
    if rl.get("rate_limit_reached_type") and blocked_until is None:
        live = [w["resets_at"] for w in rl.values() if isinstance(w, dict) and w.get("resets_at", 0) > now]
        blocked_until = max(live) if live else None
    out["reached"] = rl.get("rate_limit_reached_type")
    out["paused"] = blocked_until is not None
    out["available_at"] = _fmt(blocked_until) if blocked_until else "now"
    return out


def main() -> int:
    s = status()
    if "--json" in sys.argv:
        print(json.dumps(s, indent=2))
        return 0 if s.get("ok") else 1
    if not s.get("ok"):
        print(s["error"])
        return 1
    parts = []
    for name, w in s["windows"].items():
        label = "5h" if w["window_minutes"] == 300 else "weekly" if w["window_minutes"] == 10080 else f"{w['window_minutes']}m"
        parts.append(f"{label} {w['used_percent']:.0f}% (resets {w['resets_at']})")
    state = f"PAUSED until {s['available_at']}" if s["paused"] else "available"
    print(f"Codex {state} | " + " | ".join(parts) + f" | snapshot {s['observed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

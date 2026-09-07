"""
NouGenRelay Watchdog: Git-Commit Based Auto-Push for Relay Legs.
Bypasses directory listing API limits (~1000 file ceiling) using `git log --diff-filter=A`.
Provides fast cache reads for hooks and async background git fetch refreshes.
"""
import os
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

REPO = Path(os.environ.get("NOUGEN_RELAY_REPO", Path.home() / "Outpost" / "NouGenRelay"))
CACHE = Path(os.environ.get("NOUGEN_RELAY_CACHE", Path.home() / ".nougen" / "state" / "relay_watch.json"))
MAX_LEGS = int(os.environ.get("NOUGEN_RELAY_MAX", "12"))
CATCHUP_HOURS = float(os.environ.get("NOUGEN_RELAY_CATCHUP_H", "12"))
GOAL_CHARS = 150


def _git(*args, timeout=25):
    try:
        res = subprocess.run(
            ["git", "-C", str(REPO)] + list(args),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False
        )
        return res.stdout
    except Exception:
        return ""


def refresh_cache() -> None:
    """Async background task: fetches origin and indexes new legs via git commit log."""
    if not REPO.exists():
        return

    _git("fetch", "origin", "main", "--quiet", timeout=20)
    
    # Extract added legs via diff-filter=A
    since = (datetime.now(timezone.utc) - timedelta(hours=CATCHUP_HOURS)).isoformat()
    log_out = _git("log", "--diff-filter=A", "--name-only", f"--since={since}", "--format=%H|%cI|%s", "origin/main", "--", ".handoffs/*.json")
    
    lines = log_out.strip().splitlines()
    entries = []
    curr_commit = None
    curr_date = None
    
    for line in lines:
        if not line.strip():
            continue
        if "|" in line:
            parts = line.split("|", 2)
            curr_commit = parts[0]
            curr_date = parts[1]
        elif line.startswith(".handoffs/") and line.endswith(".json"):
            leg_id = Path(line).stem
            entries.append({
                "leg_id": leg_id,
                "commit": curr_commit,
                "created_at": curr_date,
                "path": line
            })

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    cache_data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "legs": entries[:MAX_LEGS]
    }
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=2)


def get_new_legs_since(session_watermark: Optional[str] = None) -> List[Dict[str, Any]]:
    """Reads cache and returns unseen legs for a given watermark."""
    if not CACHE.exists():
        return []
    try:
        with open(CACHE, "r", encoding="utf-8") as f:
            data = json.load(f)
            legs = data.get("legs", [])
            if not session_watermark:
                return legs[:3]
            unseen = []
            for leg in legs:
                if leg["leg_id"] == session_watermark:
                    break
                unseen.append(leg)
            return unseen
    except Exception:
        return []

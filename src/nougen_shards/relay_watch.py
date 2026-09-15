"""
NouGenRelay Watchdog: Git-Commit Based Auto-Push for Relay Legs.
Bypasses directory listing API limits (1,000-file cap) using `git log --diff-filter=A`.
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
GIT_TIMEOUT_S = float(os.environ.get("NOUGEN_RELAY_GIT_TIMEOUT_S", "25"))
FETCH_TIMEOUT_S = float(os.environ.get("NOUGEN_RELAY_FETCH_TIMEOUT_S", "20"))
GOAL_CHARS = 150


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _git(*args, timeout: Optional[float] = None) -> Optional[str]:
    """stdout of a git call in REPO, or None when git fails or times out."""
    try:
        res = subprocess.run(
            ["git", "-C", str(REPO)] + list(args),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
            timeout=GIT_TIMEOUT_S if timeout is None else timeout,
            check=False
        )
    except Exception:
        return None
    return res.stdout if res.returncode == 0 else None


def refresh_cache() -> None:
    """Async background task: fetches origin and indexes new legs via git commit log."""
    if not REPO.exists():
        return

    # A failed fetch is tolerated: the local origin/main is still worth indexing.
    _git("fetch", "origin", "main", "--quiet", timeout=FETCH_TIMEOUT_S)

    # Extract added legs via diff-filter=A
    since = (datetime.now(timezone.utc) - timedelta(hours=CATCHUP_HOURS)).isoformat()
    log_out = _git("log", "--diff-filter=A", "--name-only", f"--since={since}", "--format=%H|%cI|%s", "origin/main", "--", ".handoffs/*.json")
    if log_out is None:
        # git failed: keep the last good cache rather than blanking it.
        return

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
    # Write then rename so a hook reading mid-refresh never sees a torn file.
    tmp = CACHE.with_suffix(CACHE.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=2)
    os.replace(tmp, CACHE)


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

"""NouGen Wake Daemon: reactive idle wake detection for fleet IPC messaging.

Monitors ~/.gemini/config/inbox/, ~/.nougen/agy_inbox/, and ~/.nougen/relay/.relay/wake/
Filters for inbound pings directed at Antigravity or fleet nodes from other nodes/agents.
When detected, emits the payload and exits with code 0 to trigger reactive IDE wakeup.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

WATCH_DIRS = [
    Path.home() / ".gemini" / "config" / "inbox",
    Path.home() / ".nougen" / "agy_inbox",
    Path.home() / ".nougen" / "relay" / ".relay" / "wake",
]

SEEN_HASHES: Set[str] = set()


def get_snapshot() -> Dict[str, int]:
    """Get a mapping of watched json file paths to modification times."""
    files: Dict[str, int] = {}
    for d in WATCH_DIRS:
        if d.is_dir():
            for p in d.glob("*.json"):
                if not p.name.startswith("."):
                    try:
                        files[str(p)] = p.stat().st_mtime_ns
                    except OSError:
                        pass
    return files


def file_hash(path_str: str) -> Optional[str]:
    """Compute sha256 of file content to deduplicate rapid edits."""
    try:
        with open(path_str, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def run_wake_loop(timeout_s: float = 1800.0, interval_s: float = 5.0, verbose: bool = True) -> int:
    """Run the wake monitor loop until an inbound ping is detected or timeout expires (default: 30 mins)."""
    initial = get_snapshot()
    start_time = time.time()

    while time.time() - start_time < timeout_s:
        time.sleep(interval_s)
        current = get_snapshot()
        new_or_modified = [p for p, m in current.items() if p not in initial or m > initial.get(p, 0)]

        external_hits: List[Tuple[str, str, str, str, str]] = []
        for path_str in new_or_modified:
            try:
                p = Path(path_str)
                data = json.loads(p.read_text(encoding="utf-8"))
                source = str(data.get("source") or data.get("sender") or data.get("agent") or "unknown").lower()
                target = str(data.get("target") or "antigravity").lower()
                text = str(data.get("text") or data.get("message") or data.get("goal") or data.get("content") or "")
                round_num = data.get("round")
                status = str(data.get("status") or "").lower()

                if source == "relay-watch" and ("(closed)" in text or status == "closed") and target in ("local", "@all", "all", "?", ""):
                    continue

                f_hash = file_hash(path_str)
                if f_hash and f_hash in SEEN_HASHES:
                    continue
                if f_hash:
                    SEEN_HASHES.add(f_hash)

                label = f"PONG ROUND {round_num}" if round_num else "FLEET INBOUND PING"
                external_hits.append((p.name, source, target, text, label))
            except Exception:
                pass

        if external_hits:
            if verbose:
                print("🚨 [FLEET INBOUND PING DETECTED -> WAKING ANTIGRAVITY]")
                print(">>> INSTRUCTION FOR AGENT: You have just been woken by an inbound fleet message! Print this message immediately into the chat with an unmissable inline banner and re-launch the wake daemon.")
                for fname, src, tgt, txt, lbl in external_hits:
                    print(f"  • {lbl} from: {src} (Target: {tgt})")
                    print(f"  • File: {fname}")
                    print(f"  • Message: {txt[:300]}")
            return 0

    return 0


def main() -> int:
    return run_wake_loop()


if __name__ == "__main__":
    raise SystemExit(main())

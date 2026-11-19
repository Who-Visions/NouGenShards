"""NouGen Wake Daemon: reactive idle wake detection for fleet IPC messaging.

Monitors ~/.gemini/config/inbox/, ~/.nougen/agy_inbox/, and the resolved relay
wake directory (NOUGEN_RELAY_DIR / FLEET_RELAY_DIR, else ~/.nougen/relay/.relay/wake)
Filters for inbound pings directed at Antigravity or fleet nodes from other nodes/agents.
When detected, emits the payload and exits with code 0 to trigger reactive IDE wakeup.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

ENV_TIMEOUT_S = "NOUGEN_WAKE_TIMEOUT_S"
ENV_POLL_INTERVAL_S = "NOUGEN_WAKE_POLL_INTERVAL_S"
_FALLBACK_TIMEOUT_S = 1800.0
_FALLBACK_POLL_INTERVAL_S = 5.0

def watch_dirs() -> List[Path]:
    """Inboxes to watch, including wherever the writer resolves the wake dir.

    #495 taught the writer to honour NOUGEN_RELAY_DIR/FLEET_RELAY_DIR, but this
    list stayed hard-coded to the canonical path: on whoart, where the env var
    points at Outpost\\NouGenRelay, the writer moved and the reader did not, so
    the split survived the fix in the other direction. Both sides resolve the
    same way now, and the canonical path stays in the list so a node whose env
    changes mid-flight still sees tickets already written.
    """
    from .wake.quota import CANONICAL_RELAY_DIR, relay_wake_dir

    dirs = [
        Path.home() / ".gemini" / "config" / "inbox",
        Path.home() / ".nougen" / "agy_inbox",
        relay_wake_dir(),
        CANONICAL_RELAY_DIR / ".relay" / "wake",
    ]
    seen: Set[str] = set()
    return [d for d in dirs if not (str(d) in seen or seen.add(str(d)))]


#: Back-compat module attribute. Resolved at import; call ``watch_dirs()``
#: if the environment can change after import.
WATCH_DIRS = watch_dirs()

SEEN_HASHES: Set[str] = set()


def _emit(line: str) -> None:
    """Write a banner line that cannot kill the daemon.

    The wake banner carries emoji; a Windows console on cp1252 raises
    UnicodeEncodeError on the very write that reports the ping, so the daemon
    died exactly when it succeeded. Fall back to an ASCII-safe rendering.
    """
    stream = sys.stdout
    try:
        stream.write(line + "\n")
    except UnicodeEncodeError:
        enc = getattr(stream, "encoding", None) or "ascii"
        stream.write(line.encode(enc, "replace").decode(enc, "replace") + "\n")
    try:
        stream.flush()
    except Exception:
        pass


def get_snapshot() -> Dict[str, int]:
    """Get a mapping of watched json file paths to modification times."""
    files: Dict[str, int] = {}
    for d in watch_dirs():
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


def _env_seconds(name: str, fallback: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        logger.debug("%s unset; using logged fallback %r", name, fallback)
        return fallback
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s=%r is not a number; using logged fallback %r", name, raw, fallback)
        return fallback
    if value <= 0:
        logger.warning("%s=%r must be positive; using logged fallback %r", name, raw, fallback)
        return fallback
    return value


def resolve_timeout_s() -> float:
    """Idle seconds before the loop gives up, from NOUGEN_WAKE_TIMEOUT_S."""
    return _env_seconds(ENV_TIMEOUT_S, _FALLBACK_TIMEOUT_S)


def resolve_poll_interval_s() -> float:
    """Seconds between inbox snapshots, from NOUGEN_WAKE_POLL_INTERVAL_S."""
    return _env_seconds(ENV_POLL_INTERVAL_S, _FALLBACK_POLL_INTERVAL_S)


def status() -> Dict[str, Any]:
    """Resolved wake settings, as reported by the wake_daemon_status MCP tool."""
    return {
        "poll_interval_s": resolve_poll_interval_s(),
        "timeout_s": resolve_timeout_s(),
        "watch_dirs": [str(d) for d in watch_dirs()],
        "status": "armed",
    }


def _wait_for_change(dirs: List[Path], timeout_s: float) -> None:
    """Block until a watched directory changes or ``timeout_s`` elapses.

    Uses Win32 ``FindFirstChangeNotificationW`` + ``WaitForMultipleObjects`` on
    Windows for sub-50ms wake latency when ``timeout_s > 0.2``, falling back to
    ``time.sleep`` on POSIX, short test intervals, or if no watched dir exists.
    """
    if os.name != "nt" or timeout_s <= 0.2:
        time.sleep(timeout_s)
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.FindFirstChangeNotificationW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL, wintypes.DWORD]
        kernel32.FindFirstChangeNotificationW.restype = wintypes.HANDLE
        kernel32.WaitForMultipleObjects.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE), wintypes.BOOL, wintypes.DWORD]
        kernel32.WaitForMultipleObjects.restype = wintypes.DWORD
        kernel32.FindCloseChangeNotification.argtypes = [wintypes.HANDLE]
        kernel32.FindCloseChangeNotification.restype = wintypes.BOOL

        invalid_handle = wintypes.HANDLE(-1).value
        notify_mask = 0x00000001 | 0x00000010  # FILE_NOTIFY_CHANGE_FILE_NAME | LAST_WRITE
        handles: List[int] = []
        try:
            for d in dirs:
                if d.is_dir():
                    h = kernel32.FindFirstChangeNotificationW(str(d), False, notify_mask)
                    if h and h != invalid_handle:
                        handles.append(h)
            if not handles:
                time.sleep(timeout_s)
                return
            arr = (wintypes.HANDLE * len(handles))(*handles)
            kernel32.WaitForMultipleObjects(len(handles), arr, False, max(1, int(timeout_s * 1000)))
        finally:
            for h in handles:
                kernel32.FindCloseChangeNotification(h)
    except Exception:
        time.sleep(timeout_s)


def run_wake_loop(timeout_s: Optional[float] = None, interval_s: Optional[float] = None,
                  verbose: bool = True) -> int:
    """Run the wake monitor loop until an inbound ping is detected or timeout expires.

    None resolves from NOUGEN_WAKE_TIMEOUT_S / NOUGEN_WAKE_POLL_INTERVAL_S (fallback 30 min / 5 s).
    """
    if timeout_s is None:
        timeout_s = resolve_timeout_s()
    if interval_s is None:
        interval_s = resolve_poll_interval_s()
    initial = get_snapshot()
    start_time = time.time()

    while time.time() - start_time < timeout_s:
        _wait_for_change(watch_dirs(), interval_s)
        current = get_snapshot()
        new_or_modified = [p for p, m in current.items() if p not in initial or m > initial.get(p, 0)]

        external_hits: List[Tuple[str, str, str, str, str]] = []
        for path_str in new_or_modified:
            try:
                p = Path(path_str)
                try:
                    raw_text = p.read_text(encoding="utf-8")
                    data = json.loads(raw_text)
                except (OSError, json.JSONDecodeError):
                    # Concurrent writer may still be flushing; retry once after a short settle.
                    time.sleep(0.02)
                    data = json.loads(p.read_text(encoding="utf-8"))
                source = str(data.get("source") or data.get("sender") or data.get("agent") or "unknown").lower()
                target = str(data.get("target") or "antigravity").lower()
                text = str(data.get("text") or data.get("message") or data.get("goal") or data.get("content") or "")
                round_num = data.get("round")
                status = str(data.get("status") or "").lower()

                if source == "relay-watch" and ("(closed)" in text or status == "closed") and target in ("local", "@all", "all", "?", ""):
                    initial[path_str] = current[path_str]
                    continue

                f_hash = file_hash(path_str)
                if f_hash and f_hash in SEEN_HASHES:
                    initial[path_str] = current[path_str]
                    continue
                if f_hash:
                    SEEN_HASHES.add(f_hash)

                label = f"PONG ROUND {round_num}" if round_num else "FLEET INBOUND PING"
                external_hits.append((p.name, source, target, text, label))
            except Exception:
                pass

        if external_hits:
            if verbose:
                _emit("🚨 [FLEET INBOUND PING DETECTED -> WAKING ANTIGRAVITY]")
                _emit(">>> INSTRUCTION FOR AGENT: You have just been woken by an inbound fleet message! Print this message immediately into the chat with an unmissable inline banner and re-launch the wake daemon.")
                for fname, src, tgt, txt, lbl in external_hits:
                    _emit(f"  • {lbl} from: {src} (Target: {tgt})")
                    _emit(f"  • File: {fname}")
                    _emit(f"  • Message: {txt[:300]}")
            return 0

    return 0


def main() -> int:
    return run_wake_loop()


if __name__ == "__main__":
    raise SystemExit(main())

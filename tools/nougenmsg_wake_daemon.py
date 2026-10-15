#!/usr/bin/env python3
"""
~/.nougen/bin/nougenmsg_wake_daemon.py
Zero-poll kernel-event wake daemon for Antigravity CLI.
Grounded in NouGenShards PR #498 (dynamic watch_dirs), PR #502 (live pipe check),
and Phoebus/Blade inbox cursor watermarks.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# --- 1. Dynamic Fleet Path Resolution (Honors NOUGEN_RELAY_DIR per PR #498) ---
HOME = Path.home()
STATE_DIR = HOME / ".nougen" / "state"
CURSOR_PATH = STATE_DIR / "agy_inbox_cursor.json"
LOCK_PATH = STATE_DIR / "nougenmsg_wake_daemon.lock"
STALE_CUTOFF_S = 24 * 3600  # 24h hard cutoff (Shard 27321@db9)

NOISE_RE = re.compile(
    r"^(ack\b|ack-msg\b|acknowledged\b|received\b|antigravity turn sync|error:\s*(403|429)\b)",
    re.IGNORECASE,
)


def resolve_watch_dirs() -> List[Path]:
    relay_root = Path(os.environ.get("NOUGEN_RELAY_DIR", str(HOME / "Outpost" / "NouGenRelay")))
    candidates = [
        HOME / ".gemini" / "config" / "inbox",
        HOME / ".nougen" / "agy_inbox",
        relay_root / ".relay" / "wake",
        relay_root / ".handoffs",
    ]
    watchtower_relay = HOME / "Watchtower" / "NouGen" / "NouGenRelay-main" / ".relay" / "wake"
    try:
        if watchtower_relay.exists():
            candidates.append(watchtower_relay)
    except OSError:
        pass
    valid_dirs = []
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            if d.is_dir():
                valid_dirs.append(d)
        except OSError:
            pass
    return valid_dirs


# --- 2. UTF-8 Safe Emission (Prevents cp1252 crash on Windows — Shard 19579@db3) ---
def safe_emit(text: str) -> None:
    try:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
        sys.stdout.flush()


# --- 3. Singleton Process Guard (Prevents duplicate daemon fan-out — Shard 30848@db5) ---
def acquire_singleton_lock() -> Optional[object]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fh = open(LOCK_PATH, "a+b")
    fh.seek(0)
    if fh.tell() == 0:
        fh.write(b"0")
        fh.flush()
    fh.seek(0)
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.seek(0)
        fh.truncate()
        fh.write(f"{os.getpid()}\n".encode("ascii"))
        fh.flush()
        return fh
    except OSError:
        fh.close()
        return None


# --- 4. Atomic Cursor Watermark (Zero duplicate wakes) ---
def load_cursor() -> Tuple[float, Set[str]]:
    if not CURSOR_PATH.exists():
        return 0.0, set()
    try:
        data = json.loads(CURSOR_PATH.read_text(encoding="utf-8"))
        return float(data.get("mtime_watermark", 0.0)), set(data.get("seen_hashes", []))
    except Exception:
        return 0.0, set()


def save_cursor(mtime_watermark: float, seen_hashes: Set[str]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CURSOR_PATH.with_suffix(".tmp")
    payload = {
        "mtime_watermark": mtime_watermark,
        "seen_hashes": list(seen_hashes)[-500:],  # Bounded ring buffer
        "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, CURSOR_PATH)


# --- 5. Fast Delta Scan with Noise & Staleness Filtering ---
def scan_unseen_actionable(watch_dirs: List[Path], watermark: float, seen: Set[str]) -> List[Dict]:
    now = time.time()
    cutoff = now - STALE_CUTOFF_S
    actionable: List[Dict] = []

    for d in watch_dirs:
        if not d.exists():
            continue
        try:
            with os.scandir(d) as it:
                for entry in it:
                    if not entry.is_file() or not entry.name.endswith(".json"):
                        continue
                    try:
                        stat = entry.stat()
                    except OSError:
                        continue
                    if stat.st_mtime < cutoff:
                        continue
                    if stat.st_mtime <= watermark:
                        continue
                    p = Path(entry.path)
                    try:
                        raw = p.read_bytes()
                    except OSError:
                        continue
                    digest = hashlib.sha256(raw).hexdigest()[:16]
                    if digest in seen:
                        continue
                    try:
                        doc = json.loads(raw.decode("utf-8", errors="replace"))
                    except json.JSONDecodeError:
                        seen.add(digest)
                        continue

                    body = str(doc.get("body") or doc.get("text") or doc.get("message") or doc.get("content") or doc.get("goal") or "").strip()
                    if not body or NOISE_RE.search(body):
                        seen.add(digest)
                        continue

                    sender = doc.get("sender") or doc.get("source") or doc.get("node") or "fleet"
                    priority = doc.get("priority") or ("high" if doc.get("leg_id") else "normal")
                    actionable.append({
                        "path": str(p),
                        "digest": digest,
                        "mtime": stat.st_mtime,
                        "sender": sender,
                        "priority": priority,
                        "body": body,
                        "leg_id": doc.get("leg_id"),
                    })
        except OSError:
            continue

    actionable.sort(key=lambda x: x["mtime"])
    return actionable


# --- 6. Win32 Kernel Directory Event Wait (Zero CPU while idle) ---
def wait_for_fs_event_win32(watch_dirs: List[Path], timeout_ms: int = 5000) -> bool:
    kernel32 = ctypes.windll.kernel32
    FILE_NOTIFY_CHANGE_FILE_NAME = 0x00000001
    FILE_NOTIFY_CHANGE_LAST_WRITE = 0x00000010
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    WAIT_OBJECT_0 = 0x00000000

    handles = []
    for d in watch_dirs:
        h = kernel32.FindFirstChangeNotificationW(
            str(d), False, FILE_NOTIFY_CHANGE_FILE_NAME | FILE_NOTIFY_CHANGE_LAST_WRITE
        )
        if h and h != INVALID_HANDLE_VALUE:
            handles.append(h)

    if not handles:
        time.sleep(timeout_ms / 1000.0)
        return False

    try:
        arr_type = ctypes.c_void_p * len(handles)
        handle_array = arr_type(*handles)
        res = kernel32.WaitForMultipleObjects(len(handles), handle_array, False, timeout_ms)
        return WAIT_OBJECT_0 <= res < (WAIT_OBJECT_0 + len(handles))
    finally:
        for h in handles:
            kernel32.FindCloseChangeNotification(h)


def run_daemon() -> int:
    lock_fh = acquire_singleton_lock()
    if lock_fh is None:
        safe_emit("[wake-daemon] Already running under singleton lock; exiting.")
        return 0

    watch_dirs = resolve_watch_dirs()
    watermark, seen = load_cursor()
    safe_emit(f"[wake-daemon] Armed on {len(watch_dirs)} dirs (watermark={watermark:.2f})")

    while True:
        hits = scan_unseen_actionable(watch_dirs, watermark, seen)
        if hits:
            safe_emit(f"[wake-daemon] WAKE_SIGNAL count={len(hits)} latest={hits[-1]['sender']}")
            return 0  # Exit 0 immediately so calling process/hook continues

        if sys.platform == "win32":
            wait_for_fs_event_win32(watch_dirs, timeout_ms=15000)
        else:
            time.sleep(1.5)


if __name__ == "__main__":
    raise SystemExit(run_daemon())

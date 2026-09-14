"""Wispr Flow Voice Dictation & Transcript Ingestion for NouGen.

Connects to local Wispr Flow SQLite database across platforms (Windows / macOS).
Streams live voice dictation into the NouGen shard memory cluster in real-time.
"""
from __future__ import annotations

import os
import sys
import time
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

DEFAULT_WIN_PATH = Path(os.environ.get("APPDATA", "")) / "Wispr Flow" / "flow.sqlite"
DEFAULT_MAC_PATH = Path.home() / "Library" / "Application Support" / "Wispr Flow" / "flow.sqlite"


def resolve_wispr_db() -> Optional[Path]:
    custom = os.environ.get("WISPR_DB_PATH")
    if custom and Path(custom).exists():
        return Path(custom)
    if DEFAULT_MAC_PATH.exists():
        return DEFAULT_MAC_PATH
    if DEFAULT_WIN_PATH.exists():
        return DEFAULT_WIN_PATH
    cand = list(Path.home().glob("**/Wispr Flow/flow.sqlite"))
    if cand:
        return cand[0]
    return None


def get_latest_transcript(db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    path = db_path or resolve_wispr_db()
    if not path or not path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT asrText, formattedText, timestamp, status FROM History ORDER BY timestamp DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if row:
            return dict(row)
    except Exception as e:
        return {"error": str(e)}
    return None


def list_transcripts(limit: int = 20, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = db_path or resolve_wispr_db()
    if not path or not path.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3.0)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT asrText, formattedText, timestamp, status FROM History ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def watch_and_shard(interval_s: float = 1.0, auto_shard: bool = True, verbose: bool = True):
    from nougen_shards import core
    path = resolve_wispr_db()
    if not path:
        print("[!] Wispr Flow SQLite DB not located on local machine.")
        return

    if verbose:
        print(f"🎙️  Monitoring Wispr Flow DB: {path}")
        print("⚡ Live transcription streaming into NouGen memory substrate...")

    last_ts = None
    try:
        while True:
            row = get_latest_transcript(path)
            if row and "error" not in row:
                ts = row.get("timestamp")
                if ts and ts != last_ts:
                    text = row.get("formattedText") or row.get("asrText") or ""
                    if text.strip():
                        if verbose:
                            print(f"[{ts}] 🎙️ Voice Ingest: {text}")
                        if auto_shard and len(text.strip()) > 5:
                            shard_res = core.capture(
                                title=f"Voice Dictation {ts}",
                                content=text,
                                utility=0.85,
                                provenance={"source": "wispr_flow", "timestamp": ts}
                            )
                            if verbose:
                                print(f"  ✨ Captured Shard: {shard_res}")
                    last_ts = ts
            time.sleep(interval_s)
    except KeyboardInterrupt:
        if verbose:
            print("\n🎙️ Wispr monitoring stopped.")

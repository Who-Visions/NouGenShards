#!/usr/bin/env python3
"""
Dynamic Voice Resolver & WhoArt Fleet Voice Sync.
Dynamically discovers and queries WhoArt's active voice favorites leaderboard,
caches the preferences locally in ~/.nougen/state/whoart_voice_favorites.json,
and provides dynamic voice resolution across the NouGen fleet.
"""
import os
import json
import time
import subprocess
from pathlib import Path

WHOART_IP = "10.0.0.178"
SSH_KEY = Path.home() / ".ssh" / "kaedra_swarm_key"
CACHE_FILE = Path.home() / ".nougen" / "state" / "whoart_voice_favorites.json"
CACHE_TTL = 3600  # 1 hour cache

def fetch_whoart_favorites() -> dict:
    """Fetch remote voice favorites from WhoArt via SSH."""
    if not SSH_KEY.is_file():
        return {}
    
    cmd = [
        "ssh", "-i", str(SSH_KEY),
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=3",
        "-o", "StrictHostKeyChecking=accept-new",
        f"super@{WHOART_IP}",
        "powershell -Command \"python -c \\\"import sys, json; sys.path.insert(0, r'C:\\Users\\super\\.nougen\\bin'); from agy_voice import VOICE_FAVORITES; print(json.dumps(VOICE_FAVORITES))\\\"\""
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout.strip())
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({"updated_at": time.time(), "favorites": data}, f, indent=2)
            return data
    except Exception:
        pass
    return {}

def get_voice_favorites(force_refresh: bool = False) -> dict:
    """Get voice favorites, using local cache when fresh or fetching remote updates."""
    if not force_refresh and CACHE_FILE.is_file():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
                if time.time() - cached.get("updated_at", 0) < CACHE_TTL:
                    return cached.get("favorites", {})
        except Exception:
            pass
    
    remote = fetch_whoart_favorites()
    if remote:
        return remote
    
    # Fallback to cached copy if remote is temporarily unreachable
    if CACHE_FILE.is_file():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("favorites", {})
        except Exception:
            pass
    return {}

def resolve_dynamic_voice(requested: str | None = None) -> tuple[str, float]:
    """
    Dynamically resolve the voice ID and speed.
    Priority:
    1. Explicit requested / env override (e.g. NOUGEN_VOICE)
    2. WhoArt #1 favorite (or River if specified)
    3. Safe default 'af_river'
    """
    req = requested or os.environ.get("NOUGEN_VOICE")
    if req:
        req_clean = req.lower().strip()
        # If explicitly asking for river / koroko
        if req_clean in ("river", "koroko", "koroko river", "kokoro river", "af_river"):
            return "af_river", 1.05
        # If stale bf_emma is sitting in parent shell, fall through to WhoArt favorite / River
        if req_clean in ("bf_emma", "emma"):
            req_clean = None
        elif req_clean in ("adam", "am_adam"):
            return "am_adam", 0.98
        elif req_clean in ("nova", "af_nova"):
            return "af_nova", 0.96
        elif req_clean in ("heart", "af_heart"):
            return "af_heart", 0.98
        elif req_clean in ("eric", "am_eric"):
            return "am_eric", 0.96
        elif req_clean in ("onyx", "am_onyx"):
            return "am_onyx", 0.95
        elif req_clean:
            return req_clean, float(os.environ.get("NOUGEN_VOICE_SPEED", "1.05"))

    faves = get_voice_favorites()
    # If WhoArt favorites leaderboard is synced, dynamically pull rank 1
    if faves:
        female_faves = faves.get("female", [])
        if female_faves:
            top = female_faves[0]
            return top.get("voice_id", "af_river"), top.get("speed", 1.0)
    
    return "af_river", 1.05

if __name__ == "__main__":
    faves = get_voice_favorites(force_refresh=True)
    print("WhoArt Voice Favorites Synced:")
    print(json.dumps(faves, indent=2))
    v, s = resolve_dynamic_voice()
    print(f"\nResolved Active Dynamic Voice: {v} (speed: {s})")

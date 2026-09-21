"""Grounding + chat wrapper for the local Yukiai persona.

Ollama models cannot read the vault or the relay board; asked "todays shards" they can only stall.
This pulls the real data and puts it in front of the model as a [GROUNDING] block.

    python tools/yuki_ground.py                 # interactive chat (model Yukiai:e2b)
    python tools/yuki_ground.py --show shards   # print the grounding block only (no model)
    python tools/yuki_ground.py --show relays

Read-only: shards are read from the local vault DBs, legs from `git fetch origin main` + `git show`
(the working tree of the relay clone is never touched). Local lane only (Rule 0.3/0.7); max_tokens 2048.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VAULT = Path(os.environ.get("NOUGEN_VAULT_DIR") or Path.home() / ".nougen" / "shards").expanduser()
RELAY = Path(os.environ.get("NOUGEN_RELAY_CLONE", r"C:\Users\super\Outpost\NouGenRelay"))
OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("YUKI_MODEL", "Yukiai:e2b")


def day_start_utc() -> datetime:
    """Start of today in the machine's local zone (WhoArt is set to Eastern), as UTC."""
    now = datetime.now().astimezone()
    return now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def shards_today(limit: int = 30) -> str:
    start = day_start_utc().strftime("%Y-%m-%dT%H:%M:%S")
    rows = []
    for db in sorted(glob.glob(str(VAULT / "nougen_shards_*.db"))):
        m = re.search(r"_(\d+)\.db$", db)
        try:
            c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
            for sid, ts, title, dom in c.execute(
                    "SELECT id, timestamp, title, domain_key FROM shards WHERE timestamp >= ? "
                    "AND event_type != 'CONTEXT_EVENT'", (start,)):
                rows.append((ts, f"{sid}@db{m.group(1)}", title or "", dom or ""))
            c.close()
        except sqlite3.Error:
            continue
    rows.sort(reverse=True)
    lines = [f"{ts[:16]}Z {ref} [{dom[:24]}] {title[:110]}" for ts, ref, title, dom in rows[:limit]]
    return f"SHARDS written since {start}Z: {len(rows)} total, newest {len(lines)}:\n" + "\n".join(lines)


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(RELAY), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60).stdout


def relays_today(limit: int = 30) -> str:
    subprocess.run(["git", "-C", str(RELAY), "fetch", "-q", "origin", "main"], capture_output=True, timeout=90)
    start = day_start_utc().strftime("%Y%m%dT%H%M%SZ")
    names = [n for n in _git("ls-tree", "--name-only", "origin/main", ".handoffs/").splitlines()
             if n.endswith(".json") and re.match(r"\.handoffs/\d{8}T\d{6}Z__", n)]
    today = sorted((n for n in names if n.split("/")[-1][:16] >= start), reverse=True)
    lines = []
    for n in today[:limit]:
        leg = n.split("/")[-1][:-5]
        try:
            d = json.loads(_git("show", f"origin/main:{n}"))
        except ValueError:
            d = {}
        lane = leg.split("__", 1)[1] if "__" in leg else "?"
        lines.append(f"{leg[:16]} {lane[:34]} :: {str(d.get('goal', ''))[:120]} [{d.get('status', 'open')}]")
    return f"RELAY LEGS filed since {start} (origin/main): {len(today)} total, newest {len(lines)}:\n" + "\n".join(lines)


def grounding_for(text: str) -> str:
    low = text.lower()
    parts = []
    if re.search(r"\b(shard|shards|recall|memory|memories)\b", low):
        parts.append(shards_today())
    if re.search(r"\b(relay|relays|leg|legs|handoff|handoffs|baton)\b", low):
        parts.append(relays_today())
    return "\n\n".join(parts)


def ask(messages: list) -> str:
    body = {"model": MODEL, "messages": messages, "max_tokens": 2048, "temperature": 0.5}
    req = urllib.request.Request(OLLAMA + "/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=180).read())["choices"][0]["message"]["content"]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) == 3 and sys.argv[1] == "--show":
        print(shards_today() if sys.argv[2] == "shards" else relays_today())
        return
    history: list = []
    print(f"Yuki ({MODEL}) grounded chat. Ctrl+C to quit.")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not text:
            continue
        g = grounding_for(text)
        content = f"[GROUNDING]\n{g}\n[/GROUNDING]\n\n{text}" if g else text
        history.append({"role": "user", "content": content})
        try:
            reply = ask(history[-8:])
        except Exception as exc:  # pylint: disable=broad-except
            print(f"(ollama unavailable: {exc})")
            history.pop()
            continue
        history.append({"role": "assistant", "content": reply})
        print(f"yuki> {reply}\n")


if __name__ == "__main__":
    main()

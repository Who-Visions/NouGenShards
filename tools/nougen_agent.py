"""NouGen-fluent local agent: a local Ollama model with real tools over the NouGen infrastructure.

    python tools/nougen_agent.py                      # chat (Yukiai:e2b)
    python tools/nougen_agent.py --model Yukiai:e4b   # bigger local model
    python tools/nougen_agent.py --ask "what came in today?"   # one-shot
    python tools/nougen_agent.py --selftest           # run every tool once, no model

The model decides which tool to call (Ollama native /api/chat tool calling); this file executes them and feeds
results back. Everything stays on loopback Ollama (Rules 0.3/0.7): if Ollama is down it says so and stops.

Tools are READ-ONLY except `capture_shard`, which appends one shard to the canonical vault (~/.nougen/shards,
path pinned here, write verified by re-reading) -- append-only, never edits or deletes. Relay legs are read, never
filed: publishing is a deliberate act done from NouGenRelay.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
VAULT = Path(os.environ.get("NOUGEN_VAULT_DIR") or HOME / ".nougen" / "shards").expanduser()
os.environ["NOUGEN_VAULT_DIR"] = str(VAULT)          # pin BEFORE nougen_shards is ever imported
RELAY = Path(os.environ.get("NOUGEN_RELAY_CLONE", r"C:\Users\super\Outpost\NouGenRelay"))
NOUGEN_SRC = Path(os.environ.get("NOUGEN_SRC", r"C:\Users\super\Outpost\NouGen\src"))
OLLAMA = "http://127.0.0.1:11434"
EASTERN_NOTE = "America/New_York"
MAX_OUT = 3500                                        # chars of any tool result handed to the model


# ------------------------------------------------------------------ helpers
def _dbs():
    for db in sorted(glob.glob(str(VAULT / "nougen_shards_*.db"))):
        m = re.search(r"_(\d+)\.db$", db)
        if m:
            yield int(m.group(1)), db


def _ro(db):
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)


def _clip(s: str, n: int = MAX_OUT) -> str:
    return s if len(s) <= n else s[:n] + f"\n...[clipped, {len(s) - n} more chars]"


def _local_now() -> datetime:
    return datetime.now().astimezone()


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(RELAY), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60).stdout


# ------------------------------------------------------------------ tools
def now() -> str:
    n = _local_now()
    return f"{n.strftime('%A %Y-%m-%d %I:%M %p')} {n.tzname()} ({EASTERN_NOTE}); UTC {n.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')}"


def shards_search(query: str, limit: int = 8) -> str:
    """Full-text search of the shard vault (FTS5), all DBs, best matches first."""
    q = " ".join(re.findall(r"[A-Za-z0-9_]{2,}", query))
    if not q:
        return "empty query"
    hits = []
    for idx, db in _dbs():
        try:
            c = _ro(db)
            for sid, ts, title, dom, snip in c.execute(
                    "SELECT s.id, s.timestamp, s.title, s.domain_key, snippet(shards_fts, 1, '[', ']', ' ... ', 18) "
                    "FROM shards_fts f JOIN shards s ON s.id = f.rowid WHERE shards_fts MATCH ? "
                    "ORDER BY rank LIMIT ?", (q, int(limit))):
                hits.append((f"{sid}@db{idx}", (ts or "")[:10], (dom or "")[:22], title or "", snip or ""))
            c.close()
        except sqlite3.Error:
            continue
    if not hits:
        return f"no shards match '{q}'"
    return _clip("\n".join(f"{r} {d} [{dom}] {t[:100]} :: {sn[:160]}" for r, d, dom, t, sn in hits[:int(limit)]))


def shards_today(limit: int = 25) -> str:
    """Shards written since local midnight (Eastern), newest first."""
    start = _local_now().replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    rows = []
    for idx, db in _dbs():
        try:
            c = _ro(db)
            rows += [(ts, f"{sid}@db{idx}", dom or "", title or "") for sid, ts, title, dom in c.execute(
                "SELECT id, timestamp, title, domain_key FROM shards WHERE timestamp >= ? "
                "AND event_type != 'CONTEXT_EVENT'", (start,))]
            c.close()
        except sqlite3.Error:
            continue
    rows.sort(reverse=True)
    return _clip(f"{len(rows)} shards since {start}Z (newest {min(len(rows), int(limit))}):\n" +
                 "\n".join(f"{ts[:16]}Z {r} [{d[:22]}] {t[:110]}" for ts, r, d, t in rows[:int(limit)]))


def shard_get(ref: str, chars: int = 2500) -> str:
    """Read one shard by ref like '24332@db2' (body clipped)."""
    m = re.match(r"^\s*(\d+)@db(\d+)\s*$", ref or "")
    if not m:
        return "ref must look like 24332@db2"
    path = VAULT / f"nougen_shards_{m.group(2)}.db"
    if not path.exists():
        return f"no such db: db{m.group(2)}"
    c = _ro(path)
    row = c.execute("SELECT timestamp, event_type, title, domain_key, tags, content, enc FROM shards WHERE id=?",
                    (int(m.group(1)),)).fetchone()
    c.close()
    if not row:
        return f"{ref} not found"
    ts, ev, title, dom, tags, content, enc = row
    if enc:
        return f"{ref} is encrypted (private/secret); body not shown. title={title}"
    return _clip(f"{ref} {ts} {ev} [{dom}] tags={tags}\nTITLE: {title}\n{content}", int(chars))


def relays_today(limit: int = 25) -> str:
    """Relay legs (fleet handoffs) filed today, from origin/main of NouGenRelay."""
    subprocess.run(["git", "-C", str(RELAY), "fetch", "-q", "origin", "main"], capture_output=True, timeout=90)
    start = _local_now().replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    names = [n for n in _git("ls-tree", "--name-only", "origin/main", ".handoffs/").splitlines()
             if n.endswith(".json") and re.match(r"\.handoffs/\d{8}T\d{6}Z__", n)]
    today = sorted((n for n in names if n.split("/")[-1][:16] >= start), reverse=True)
    out = []
    for n in today[:int(limit)]:
        leg = n.split("/")[-1][:-5]
        try:
            d = json.loads(_git("show", f"origin/main:{n}"))
        except ValueError:
            d = {}
        out.append(f"{leg[:16]} {leg.split('__', 1)[-1][:32]} :: {str(d.get('goal', ''))[:110]} [{d.get('status', 'open')}]")
    return _clip(f"{len(today)} legs since {start} (newest {len(out)}):\n" + "\n".join(out))


def relay_read(leg_id: str, chars: int = 2500) -> str:
    """Read one relay leg by its id (e.g. 20260920T191021Z__chatgpt-app__g-whoentertains)."""
    leg = re.sub(r"\.(json|md)$", "", leg_id.strip())
    if not re.match(r"^[\w\-.]+$", leg):
        return "bad leg id"
    raw = _git("show", f"origin/main:.handoffs/{leg}.json")
    if not raw:
        return f"{leg} not found on origin/main"
    try:
        d = json.loads(raw)
    except ValueError:
        return _clip(raw, int(chars))
    body = _git("show", f"origin/main:.handoffs/{leg}.md") or str(d.get("message", ""))
    return _clip(f"{leg} status={d.get('status')}\nGOAL: {d.get('goal')}\n{body}", int(chars))


def relays_open(limit: int = 20) -> str:
    """Recent relay legs still open (unacked), newest first, from the last 3 days."""
    subprocess.run(["git", "-C", str(RELAY), "fetch", "-q", "origin", "main"], capture_output=True, timeout=90)
    names = sorted((n for n in _git("ls-tree", "--name-only", "origin/main", ".handoffs/").splitlines()
                    if n.endswith(".json") and re.match(r"\.handoffs/\d{8}T\d{6}Z__", n)), reverse=True)[:400]
    out = []
    for n in names:
        try:
            d = json.loads(_git("show", f"origin/main:{n}"))
        except ValueError:
            continue
        if str(d.get("status", "open")).lower() == "open" and "hourly_shard" not in n:
            out.append(f"{n.split('/')[-1][:-5][:50]} :: {str(d.get('goal', ''))[:100]}")
        if len(out) >= int(limit):
            break
    return _clip(f"{len(out)} open (of last 400 legs, hourly bots excluded):\n" + "\n".join(out))


def fleet_status() -> str:
    """Nodes from ~/.nougen/nodes.json, local Ollama models, machine health."""
    parts = []
    nodes = HOME / ".nougen" / "nodes.json"
    if nodes.exists():
        try:
            d = json.loads(nodes.read_text(encoding="utf-8"))
            d = d.get("nodes", d) if isinstance(d, dict) else d
            for k, v in (d.items() if isinstance(d, dict) else []):
                parts.append(f"node {k}: host={v.get('host') if isinstance(v, dict) else v}")
        except (ValueError, OSError):
            parts.append("nodes.json unreadable")
    try:
        ps = json.loads(urllib.request.urlopen(OLLAMA + "/api/ps", timeout=5).read())
        parts.append("ollama loaded: " + (", ".join(m["name"] for m in ps.get("models", [])) or "nothing"))
        tags = json.loads(urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5).read())
        parts.append("ollama models: " + ", ".join(m["name"] for m in tags.get("models", [])))
    except Exception as exc:  # pylint: disable=broad-except
        parts.append(f"ollama: {exc}")
    du = shutil.disk_usage(str(HOME))
    parts.append(f"C: free {du.free / 1e9:.1f} GB of {du.total / 1e9:.0f} GB")
    parts.append(f"vault: {sum(1 for _ in _dbs())} DBs at {VAULT}")
    return "\n".join(parts)


def capture_shard(title: str, content: str, tags: list | None = None) -> str:
    """Append ONE shard to the canonical vault and verify it landed. Append-only."""
    if not title or len(content or "") < 10:
        return "need a title and content (>=10 chars)"
    sys.path.insert(0, str(NOUGEN_SRC))
    from nougen_shards import core  # imported after NOUGEN_VAULT_DIR is pinned
    ok = core.capture("KNOWLEDGE", title, content, tags=list(tags or []) + ["local-agent"])
    for idx, db in _dbs():
        try:
            c = _ro(db)
            row = c.execute("SELECT id FROM shards WHERE title = ? ORDER BY id DESC LIMIT 1", (title,)).fetchone()
            c.close()
            if row:
                return f"captured and verified: {row[0]}@db{idx}"
        except sqlite3.Error:
            continue
    return f"capture returned {ok} but the shard was NOT found on re-read; treat as not stored"


TOOLS = {f.__name__: f for f in (now, shards_search, shards_today, shard_get, relays_today, relay_read,
                                 relays_open, fleet_status, capture_shard)}


def _schema(fn) -> dict:
    import inspect
    props, req = {}, []
    for name, p in inspect.signature(fn).parameters.items():
        typ = {"int": "integer", "list": "array"}.get(str(p.annotation).replace("<class '", "").replace("'>", "").split(" ")[0], "string")
        if p.annotation is inspect._empty and isinstance(p.default, int):
            typ = "integer"
        props[name] = {"type": typ, **({"items": {"type": "string"}} if typ == "array" else {})}
        if p.default is inspect._empty:
            req.append(name)
    return {"type": "function", "function": {"name": fn.__name__, "description": (fn.__doc__ or "").strip().split("\n")[0],
                                             "parameters": {"type": "object", "properties": props, "required": req}}}


SCHEMAS = [_schema(f) for f in TOOLS.values()]
SYSTEM_NOTE = (
    "You have live tools over the NouGen infrastructure. Call them instead of guessing: shards_search / shards_today / "
    "shard_get for memory, relays_today / relays_open / relay_read for the fleet handoff board, fleet_status for nodes and "
    "Ollama, now for the clock, capture_shard to store a durable finding. Quote refs (like 24332@db2) exactly as returned. "
    "If a tool returns nothing, say so; never invent ids, counts or times. Times are US Eastern."
)


# ------------------------------------------------------------------ chat loop
def chat(model: str, messages: list, max_rounds: int = 5) -> str:
    for _ in range(max_rounds):
        body = {"model": model, "messages": messages, "tools": SCHEMAS, "stream": False,
                "options": {"num_predict": 2048, "num_ctx": 8192, "temperature": 0.4}}
        req = urllib.request.Request(OLLAMA + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
        msg = json.loads(urllib.request.urlopen(req, timeout=240).read())["message"]
        calls = msg.get("tool_calls") or []
        messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
        if not calls:
            return msg.get("content") or "(no answer)"
        for c in calls:
            fn = c["function"]["name"]
            args = c["function"].get("arguments") or {}
            try:
                result = TOOLS[fn](**args) if fn in TOOLS else f"unknown tool {fn}"
            except Exception as exc:  # pylint: disable=broad-except
                result = f"tool error: {type(exc).__name__}: {exc}"
            print(f"  [tool] {fn}({', '.join(f'{k}={v!r}'[:40] for k, v in args.items())})", flush=True)
            messages.append({"role": "tool", "tool_name": fn, "content": _clip(str(result))})
    return "(stopped: too many tool rounds)"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:]
    model = argv[argv.index("--model") + 1] if "--model" in argv else os.environ.get("YUKI_MODEL", "Yukiai:e2b")
    if "--selftest" in argv:
        for name, fn in TOOLS.items():
            if name == "capture_shard":
                continue
            args = {"shards_search": {"query": "canon lock"}, "shard_get": {"ref": "24332@db2"},
                    "relay_read": {"leg_id": "20260920T191021Z__chatgpt-app__g-whoentertains"}}.get(name, {})
            print(f"--- {name}\n{fn(**args)[:400]}\n")
        return
    history = [{"role": "system", "content": SYSTEM_NOTE}]
    if "--ask" in argv:
        history.append({"role": "user", "content": argv[argv.index("--ask") + 1]})
        print(chat(model, history))
        return
    print(f"NouGen agent on {model}. Ctrl+C to quit.")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if text:
            history.append({"role": "user", "content": text})
            try:
                print(f"yuki> {chat(model, history)}\n")
            except Exception as exc:  # pylint: disable=broad-except
                print(f"(ollama unavailable: {exc})")
                history.pop()


if __name__ == "__main__":
    main()

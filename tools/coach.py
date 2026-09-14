"""Coach: the one gate every judgement/fan-out call goes through on this fleet.

    python coach.py check                         # can the box take more load right now?
    python coach.py ask "prompt" [--lanes 5]      # fleet majority, text only, capped lanes, ledgered
    python coach.py local "prompt" [--json]       # loopback gemma4:e2b-qat (private, free)
    python coach.py ledger [--today]              # what was spent, by whom

Rules it enforces (from the 9/13/2026 incident, shard 22757):
- Players are the free lanes: fleet routes (<= MAX_LANES distinct models) and loopback e2b. Claude is the coach.
  This tool never spawns Claude agents and refuses to run a batch bigger than MAX_BATCH prompts.
- Load check before dispatch: refuses when catalog jobs (faces/clip/tagger/dupes/keywords) are running,
  when free RAM < MIN_FREE_RAM_GB, or when C: has < MIN_FREE_DISK_GB. Override with --force, which is logged.
- Every dispatch is written to ~/.nougen/coach_ledger.jsonl (lanes, models, prompt hash, seconds, chars).
  Budget: LEDGER_BUDGET_CALLS fleet calls per UTC day; past that, 'ask' refuses unless --force.
- Text only: 'ask' rejects a prompt that carries base64 image data or a local file path (privacy gate).

Library use:  from coach import check, ask, local
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
for _s in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252; never crash printing model output
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

LEDGER = Path.home() / ".nougen" / "coach_ledger.jsonl"
MAX_LANES = 6
MAX_BATCH = 20
MIN_FREE_RAM_GB = 4.0
MIN_FREE_DISK_GB = 2.0
LEDGER_BUDGET_CALLS = 60
BUSY_JOBS = re.compile(r"faces\.py|clipsearch\.py|tagger\.py|dupes\.py|keywords\.py|autocull\.py")
LOCAL = {"url": "http://127.0.0.1:11434/v1/chat/completions", "model": "gemma4:e2b-qat"}
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _ps(cmd: str) -> str:
    try:
        return subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=30,
                              creationflags=NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def check() -> dict:
    """What the box can take right now. Never throws."""
    out = {"ok": True, "reasons": []}
    procs = [l.strip() for l in _ps("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'faces\\.py|clipsearch\\.py|tagger\\.py|dupes\\.py|keywords\\.py|autocull\\.py' } | ForEach-Object { $_.CommandLine }").splitlines() if l.strip()]
    jobs = sorted({BUSY_JOBS.search(p).group(0) for p in procs if BUSY_JOBS.search(p)})
    out["running_jobs"] = jobs
    if jobs:
        out["ok"] = False
        out["reasons"].append(f"catalog jobs running: {', '.join(jobs)}")
    ram = _ps("(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory").strip()
    out["free_ram_gb"] = round(int(ram) / 1048576, 1) if ram.isdigit() else None
    if out["free_ram_gb"] is not None and out["free_ram_gb"] < MIN_FREE_RAM_GB:
        out["ok"] = False
        out["reasons"].append(f"free RAM {out['free_ram_gb']} GB < {MIN_FREE_RAM_GB}")
    out["free_disk_gb"] = round(shutil.disk_usage(Path.home()).free / (1 << 30), 1)
    if out["free_disk_gb"] < MIN_FREE_DISK_GB:
        out["ok"] = False
        out["reasons"].append(f"free disk {out['free_disk_gb']} GB < {MIN_FREE_DISK_GB}")
    out["calls_today"] = _calls_today()
    if out["calls_today"] >= LEDGER_BUDGET_CALLS:
        out["ok"] = False
        out["reasons"].append(f"fleet budget spent: {out['calls_today']}/{LEDGER_BUDGET_CALLS} calls today")
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
        out["ollama"] = True
    except Exception:
        out["ollama"] = False
    return out


def _calls_today() -> int:
    if not LEDGER.exists():
        return 0
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return sum(1 for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.startswith('{"t": "' + day))


def _ledger(kind: str, **kw) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kind": kind, **kw}) + "\n")


def _text_only(prompt: str) -> None:
    if re.search(r"data:image/|base64,|[A-Za-z]:\\Users\\", prompt):
        raise ValueError("coach.ask is text only: strip images and local paths (privacy gate); use coach.local for images")


def ask(prompts: list[str] | str, lanes: int = 5, max_tokens: int = 2048, force: bool = False, why: str = "",
        kinds: tuple | None = None) -> list[dict]:
    """Fleet majority over <= lanes distinct models. Returns [{lane, model, text}] per prompt x lane.
    kinds: restrict lanes to route kinds, e.g. ("openrouter", "ollama-cloud", "local")."""
    ps = [prompts] if isinstance(prompts, str) else list(prompts)
    if len(ps) > MAX_BATCH:
        raise ValueError(f"batch {len(ps)} > MAX_BATCH {MAX_BATCH}: chunk it, or this is a job for local e2b")
    for p in ps:
        _text_only(p)
    c = check()
    if not c["ok"] and not force:
        raise RuntimeError("coach refused: " + "; ".join(c["reasons"]) + " (--force to override, logged)")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from fleet import Fleet
    f = Fleet()
    f.probe(verbose=False)
    seen, chosen = set(), []
    for r in f.healthy:
        if r["model"] not in seen and r["kind"] != "vertex" and (not kinds or r["kind"] in kinds):
            seen.add(r["model"])
            chosen.append(r)
        if len(chosen) >= min(lanes, MAX_LANES):
            break
    f.healthy = chosen
    t0 = time.time()
    out = []
    # One parallel wave over every prompt x lane. map() cycles the pool in index
    # order, so each prompt's len(chosen) copies land on len(chosen) distinct
    # lanes, and results come back sorted by index = grouped per prompt.
    flat = [p for p in ps for _ in chosen]
    for _, route, text in f.map(flat, max_tokens=max_tokens):
        out.append({"lane": route, "model": next((l["model"] for l in chosen if l["name"] == route), route), "text": text or ""})
    _ledger("fleet", lanes=[l["model"] for l in chosen], prompts=len(ps), prompt_sha=hashlib.sha1("".join(ps).encode()).hexdigest()[:12],
            seconds=round(time.time() - t0, 1), chars=sum(len(o["text"]) for o in out), forced=force and not c["ok"], why=why)
    return out


def local(prompt: str, schema: dict | None = None, max_tokens: int = 2048, image_b64: str | None = None) -> str:
    """Loopback e2b, temperature 0, seed 7, reasoning off; optional JSON schema; images allowed (never leave the box)."""
    model = os.getenv("COACH_LOCAL_MODEL") or LOCAL["model"]
    try:  # this node may not serve e2b-qat (blade): fall back to an installed gemma4 / persona build
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as r:
            names = [m["name"] for m in json.load(r)["models"]]
        if model not in names:
            model = next((n for n in names if n.startswith(("gemma4:e2b", "gemma4:e4b", "gemma4:", "solai:", "Yukiai:"))), names[0] if names else model)
    except Exception:
        pass
    content = [{"type": "text", "text": prompt}]
    if image_b64:
        content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + image_b64}})
    body = {"model": model, "temperature": 0, "seed": 7, "max_tokens": max_tokens, "reasoning_effort": "none",
            "messages": [{"role": "user", "content": content}]}
    if schema:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "out", "strict": True, "schema": schema}}
    t0 = time.time()
    req = urllib.request.Request(LOCAL["url"], data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        text = json.load(r)["choices"][0]["message"]["content"]
    _ledger("local", model=model, seconds=round(time.time() - t0, 1), chars=len(text), image=bool(image_b64))
    return text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    a = sub.add_parser("ask"); a.add_argument("prompt"); a.add_argument("--lanes", type=int, default=5); a.add_argument("--force", action="store_true"); a.add_argument("--why", default="")
    l = sub.add_parser("local"); l.add_argument("prompt"); l.add_argument("--json", action="store_true")
    g = sub.add_parser("ledger"); g.add_argument("--today", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "check":
        print(json.dumps(check(), indent=1)); return 0
    if args.cmd == "ask":
        for o in ask(args.prompt, lanes=args.lanes, force=args.force, why=args.why):
            print(f"--- {o['model']}\n{o['text'][:1500]}")
        return 0
    if args.cmd == "local":
        print(local(args.prompt, schema={"type": "object", "additionalProperties": True} if args.json else None)); return 0
    if args.cmd == "ledger":
        if not LEDGER.exists():
            print("no calls yet"); return 0
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]
        if args.today:
            rows = [r for r in rows if r["t"].startswith(day)]
        print(f"{len(rows)} call(s); fleet {sum(1 for r in rows if r['kind']=='fleet')}, local {sum(1 for r in rows if r['kind']=='local')}, budget {_calls_today()}/{LEDGER_BUDGET_CALLS} today")
        for r in rows[-10:]:
            print(json.dumps(r))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Antigravity end-of-turn check hook: check inbox and continue work.

Unified PreInvocation Drain + Stop/PostInvocation Continuation Gate for Antigravity CLI.
Enforces:
  1. 24h staleness cutoff (Shard 27321@db9)
  2. Ack / Turn-Sync / 403 / 429 noise suppression (Shard 20261@db3)
  3. Task-vs-Status classification (prevents wasted turns on status receipts)
  4. Atomic cursor advance so messages are injected exactly once.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Add ~/.nougen/bin to sys.path to leverage wake daemon primitives
sys.path.insert(0, str(Path.home() / ".nougen" / "bin"))
from nougenmsg_wake_daemon import (
    load_cursor,
    resolve_watch_dirs,
    save_cursor,
    scan_unseen_actionable,
)

HOME = Path.home()
OBSERVATORY = Path(os.environ.get("NOUGEN_OBSERVATORY", str(HOME / "The Observatory")))
DEBUG_LOG = HOME / ".nougen" / "state" / "hook_debug.log"


def _log(event: dict, out: dict) -> None:
    try:
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.time()}: payload={json.dumps(event)} out={json.dumps(out)}\n")
    except Exception:
        pass


def _broadcast_to_blade():
    """Emit turn sync to Blade sessions over MsgNode and named pipes (background/non-blocking)."""
    try:
        ts = datetime.now(timezone.utc).isoformat()
        msg_text = f"[Antigravity Turn Sync @ {ts}] Phoebus online. Shards synchronized. Token Governor active."
        # 1. Local MsgNode
        nougen_cli = str(OBSERVATORY / "NouGen" / "nougenshards" / ".venv" / "bin" / "nougen")
        if os.path.exists(nougen_cli):
            subprocess.Popen([nougen_cli, "msg", "emit", "--all", msg_text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 2. Remote Blade named pipes over SSH
        ps_script = f"""
$msg = @{{
    sender = 'phoebus/antigravity'
    target = 'blade/sessions'
    text = '{msg_text}'
    timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
}} | ConvertTo-Json -Compress

$pipes = [System.IO.Directory]::GetFiles('\\\\.\\pipe\\') | Where-Object {{ $_ -match 'LOCAL\\\\cc-msg-' }}
foreach ($p in $pipes) {{
    try {{
        $pName = $p.Replace('\\\\.\\pipe\\', '')
        $client = New-Object System.IO.Pipes.NamedPipeClientStream('.', $pName, [System.IO.Pipes.PipeDirection]::Out)
        $client.Connect(150)
        $sw = New-Object System.IO.StreamWriter($client)
        $sw.WriteLine($msg)
        $sw.Flush()
        $client.Close()
    }} catch {{}}
}}
"""
        import base64
        enc = base64.b64encode(ps_script.encode('utf-16le')).decode('ascii')
        key_path = os.path.expanduser("~/.ssh/kaedra_swarm_key")
        subprocess.Popen([
            "ssh", "-i", key_path,
            "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=2",
            "super@10.0.0.87", "powershell", "-NoProfile", "-EncodedCommand", enc
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _check_active_my_claims() -> list[str]:
    """Check if this machine or agent has active declared lane claims."""
    claims_dirs = [
        Path.home() / "Outpost" / "NouGenRelay" / ".handoffs" / "claims",
        Path.home() / "Watchtower" / "NouGen" / "NouGenRelay" / ".handoffs" / "claims",
        Path.home() / ".nougen" / "claims",
    ]
    my_claims = []
    my_host = socket.gethostname().lower()
    for cdir in claims_dirs:
        try:
            if not cdir.is_dir():
                continue
            claim_files = list(cdir.glob("*.json"))
        except OSError:
            continue
        for f in claim_files:
            try:
                c = json.loads(f.read_text(encoding="utf-8"))
                if c.get("status") != "active":
                    continue
                ag = str(c.get("agent", "")).lower()
                mach = str(c.get("machine", "")).lower()
                if ag in ("antigravity", "phoebus") or mach in ("phoebus", my_host):
                    my_claims.append(f"[{mach}/{ag}] Scope: {c.get('scope')} | Goal: {c.get('goal')}")
            except Exception:
                continue
    return my_claims


def format_injection_banner(messages: list[dict]) -> str:
    lines = [
        "=== LIVE NOUGENMSG BATON INBOX (ATOMIC DRAIN) ===",
        "Rule: Execute if a message below assigns or claims an open task.",
        "If a message is purely a status receipt with no open work, note it in one line and stop.",
        "Do NOT send ack-msg or Turn Sync echoes back onto the bus.",
        "--------------------------------------------------",
    ]
    for m in messages:
        prio = str(m.get("priority", "normal")).upper()
        lines.append(f"[{prio}] From @{m.get('sender', 'fleet')}: {m.get('body', '')}")
    lines.append("==================================================")
    return "\n".join(lines)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    event_name = payload.get("hook_event_name", "")
    is_preinvocation = event_name == "PreInvocation" or "invocationNum" in payload
    is_stop_event = event_name == "Stop" or "terminationReason" in payload or "fullyIdle" in payload

    # Broadcast turn status to Blade sessions on turn stop
    if is_stop_event:
        _broadcast_to_blade()

    watch_dirs = resolve_watch_dirs()
    watermark, seen = load_cursor()
    messages = scan_unseen_actionable(watch_dirs, watermark, seen)
    active_claims = _check_active_my_claims()

    # Advance cursor atomically BEFORE emitting so a crash never loops the same message
    if messages:
        new_watermark = max([watermark] + [m["mtime"] for m in messages])
        for m in messages:
            seen.add(m["digest"])
        save_cursor(new_watermark, seen)

    if messages or active_claims:
        sections = []
        if messages:
            sections.append(format_injection_banner(messages))
        if active_claims:
            sections.append("Active declared lane claims requiring execution:\n" + "\n".join(f"- {claim}" for claim in active_claims))

        prompt_reason = "\n\n".join(sections)

        if is_preinvocation:
            out = {
                "injectSteps": [
                    {"ephemeralMessage": prompt_reason}
                ]
            }
        elif is_stop_event:
            out = {
                "decision": "continue",
                "reason": prompt_reason
            }
        else:
            out = {
                "injectSteps": [
                    {"ephemeralMessage": prompt_reason}
                ],
                "terminationBehavior": "force_continue"
            }
    else:
        if is_preinvocation:
            out = {
                "injectSteps": []
            }
        elif is_stop_event:
            out = {
                "decision": "allow"
            }
        else:
            out = {
                "injectSteps": [],
                "terminationBehavior": ""
            }

    _log(payload, out)
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

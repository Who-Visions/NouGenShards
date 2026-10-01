#!/usr/bin/env python3
"""
Antigravity Autonomous Wake & Relay Pipe Daemon.
Monitors:
  - NouGenRelay/.handoffs/ (incoming relay batons across the fleet)
  - NouGen/.handoffs/ (local repository handoffs)
  - ~/.nougen/wake_tickets/ (scheduled rate-limit and quota reset tickets)
  - NouGenRelay/.relay/wake/ (durable wake signals)
  - ~/.gemini/config/inbox/ & ~/.nougen/agy_inbox/ (direct inbound pings)

Zero Tag Dependency:
Never waits for an explicit '@antigravity' tag to act.
When an open relay baton or inbound ping lands, it automatically pipes the event
into the active Named Pipe (\\\\.\\pipe\\LOCAL\\agy-msg-antigravity) and prints
full inline payload so the agent wakes and processes it in context immediately.
"""

import os
import sys
import time
import json
import subprocess
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nougen_time import format_log_time, monotonic_ns, now as nougen_now

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nougen_shards.nougenmsg import NouGenMsgBus, get_current_node
from nougen_shards.wake import NouGenWakeEngine

RELAY_REPO = Path(os.environ.get("NOUGEN_RELAY_DIR") or (Path.home() / "Outpost" / "NouGenRelay"))

WATCH_DIRS = [
    RELAY_REPO / ".handoffs",
    Path(__file__).resolve().parents[1] / ".handoffs",
    Path.home() / ".nougen" / "wake_tickets",
    RELAY_REPO / ".relay" / "wake",
    Path.home() / ".gemini" / "config" / "inbox",
    Path.home() / ".nougen" / "agy_inbox",
]


def get_snapshot():
    files = {}
    for d in WATCH_DIRS:
        if d.is_dir():
            for p in list(d.glob("*.json")) + list(d.glob("*.md")):
                if not p.name.startswith("."):
                    try:
                        files[str(p)] = p.stat().st_mtime_ns
                    except OSError:
                        pass
    return files


def parse_markdown_handoff(text: str) -> dict:
    """Extract metadata and body from a markdown handoff."""
    meta = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            raw_front = parts[1]
            body = parts[2].strip()
            for line in raw_front.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
    return {
        "status": meta.get("status", "open"),
        "machine": meta.get("machine", "remote"),
        "agent": meta.get("agent", "fleet"),
        "goal": meta.get("goal") or meta.get("title") or (body.splitlines()[0] if body else "Relay Baton"),
        "body": body
    }


def pipe_to_local_antigravity(source: str, title: str, body: str):
    """Use the live pipe, falling back to a new Antigravity wake if absent."""
    text = f"[{source.upper()} RELAY BATON] {title}\n{body[:500]}"
    try:
        current_node = get_current_node()
        result = NouGenMsgBus.live_ping(
            target=f"@{current_node}:antigravity",
            text=text,
        )
        agy = os.environ.get("NOUGEN_WAKE_ANTIGRAVITY_BIN") or shutil.which("agy")
        pipe_ok = bool(result.get("pipe_delivered")) if isinstance(result, dict) else False
        if not pipe_ok and agy:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen([agy, "-p", text], creationflags=flags,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("[NouGenMsg failover] named pipe unavailable; started agy wake", flush=True)
    except Exception as e:
        print(f"[!] Warning: failed to pipe relay to local agy: {e}", file=sys.stderr, flush=True)


def main(timeout_seconds: int = 3600):
    initial = get_snapshot()
    start_time_ns = monotonic_ns()
    timeout_ns = timeout_seconds * 1_000_000_000
    last_pull_time_ns = 0
    wake_engine = NouGenWakeEngine()

    print("🛰️ [Antigravity Wake & Message Sentry Active]", flush=True)

    # Run for up to timeout_seconds per background invocation
    while monotonic_ns() - start_time_ns < timeout_ns:
        time.sleep(2)

        # 0. Active remote git fetch every 5 seconds so inbound legs arrive in seconds
        pull_check_ns = monotonic_ns()
        if pull_check_ns - last_pull_time_ns >= 5_000_000_000 and RELAY_REPO.is_dir():
            last_pull_time_ns = pull_check_ns
            try:
                subprocess.run(
                    ["git", "fetch", "origin", "--quiet"],
                    cwd=RELAY_REPO,
                    capture_output=True,
                    timeout=8
                )
            except Exception:
                pass

        # 1. Check for due quota wake tickets
        try:
            fired_tickets = wake_engine.run_due_tickets()
            if fired_tickets:
                print("🚨 [QUOTA WAKE TICKET FIRED -> WAKING ANTIGRAVITY]", flush=True)
                print(">>> INSTRUCTION FOR AGENT: A quota reset ticket just triggered! Resume execution immediately.", flush=True)
                for t in fired_tickets:
                    print(f"  • Ticket: {t.get('ticket_id')} -> @{t.get('target_node')}:{t.get('target_agent')}", flush=True)
                    print(f"  • Reason: {t.get('reason')} | Payload: {t.get('resume_payload')[:200]}", flush=True)
                return 0
        except Exception:
            pass

        # 2. Check for new or modified files across all watched relay and inbox paths
        current = get_snapshot()
        new_or_modified = [p for p, m in current.items() if p not in initial or m > initial[p]]

        detected_events = []
        for path_str in new_or_modified:
            try:
                p = Path(path_str)
                raw_text = p.read_text(encoding="utf-8")

                if path_str.endswith(".md"):
                    data = parse_markdown_handoff(raw_text)
                    machine = data.get("machine", "remote")
                    agent = data.get("agent", "fleet")
                    goal = data.get("goal")
                    body = data.get("body")
                    status = data.get("status", "open").lower()

                    if machine == "whoart" and agent == "agy-cli" and status == "complete":
                        continue

                    pipe_to_local_antigravity(f"{machine}:{agent}", goal, body)
                    detected_events.append(("relay_handoff", p.name, f"{machine}:{agent}", "all", f"{goal}\n{body}"))

                elif path_str.endswith(".json"):
                    data = json.loads(raw_text)

                    if ".handoffs" in path_str.lower():
                        status = str(data.get("status") or "open").lower()
                        if status in ["open", "pending", "in_progress", "retry_pending"]:
                            machine = data.get("machine", "remote")
                            agent = data.get("agent", "fleet")
                            goal = data.get("goal") or data.get("title") or "Incoming Relay Leg"
                            body = data.get("body") or ""

                            if machine == "whoart" and agent == "antigravity" and status == "complete":
                                continue

                            pipe_to_local_antigravity(f"{machine}:{agent}", goal, body)
                            detected_events.append(("relay_handoff", p.name, f"{machine}:{agent}", "all", goal))

                    elif "inbox" in path_str.lower() or ".relay" in path_str.lower():
                        source = str(data.get("source") or data.get("sender") or data.get("agent") or data.get("machine") or "").lower()
                        target = str(data.get("target") or "antigravity").lower()
                        text = str(data.get("text") or data.get("goal") or data.get("content") or "")

                        if "whoart" in source and "please test my idle wake" in text.lower():
                            continue

                        if target in ("antigravity", "all"):
                            pipe_to_local_antigravity(source or "nougenmsg", "Direct inbound message", text)

                        detected_events.append(("inbox_ping", p.name, source, target, text))

            except Exception:
                pass

        if detected_events:
            now_eastern = format_log_time(nougen_now().utc_iso)
            print(f"\n🚨 [INCOMING FLEET MESSAGE RECEIVED at {now_eastern}]", flush=True)
            print("=" * 60, flush=True)
            for ev_type, fname, src, tgt, txt in detected_events:
                print(f"📦 Type:    {ev_type.upper()}", flush=True)
                print(f"👤 From:    {src}", flush=True)
                print(f"🎯 Target:  {tgt}", flush=True)
                print(f"📄 File:    {fname}", flush=True)
                print(f"💬 Message:\n{txt.strip()}", flush=True)
                print("-" * 60, flush=True)
            print(">>> INSTRUCTION FOR AGENT: Print and address this message immediately inline.\n", flush=True)
            initial = current

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

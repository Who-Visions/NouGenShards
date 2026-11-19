#!/usr/bin/env python3
"""NouGenRelay MCP Server — Decentralized Fleet Handoff & Session Baton Transport.

Git is the bus. Each node in the NouGenAi fleet maintains its own namespace under
`~/.nougen/relay/<machine>/`. Batons represent session lifecycles:
  - start: initialize or adopt a session
  - mid: checkpoint progress, record token metrics & confidence
  - end: seal the baton and emit a clean handoff packet

Stdlib only. Zero third-party dependencies.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0

SERVER_NAME = "nougen-relay"
VERSION = "1.0.0"

SUPPORTED_PROTOCOLS: Tuple[str, ...] = ("2025-06-18", "2025-03-26", "2024-11-05")
PREFERRED_PROTOCOL = SUPPORTED_PROTOCOLS[0]


def log(message: str) -> None:
    """stderr only — stdout belongs strictly to the JSON-RPC protocol."""
    print(f"[{SERVER_NAME}] {message}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Resolution & Configuration (Dynamic over hardcode)
# ---------------------------------------------------------------------------

def relay_root() -> Path:
    explicit = os.environ.get("NOUGEN_RELAY_DIR", "").strip()
    if explicit:
        p = Path(explicit)
        p.mkdir(parents=True, exist_ok=True)
        return p
    default = Path.home() / ".nougen" / "relay"
    default.mkdir(parents=True, exist_ok=True)
    return default


def slugify_machine(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "unknown-machine"


def resolve_machine(override: Optional[str] = None) -> str:
    if override and override.strip():
        return slugify_machine(override.strip())
    explicit = os.environ.get("NOUGEN_MACHINE", "").strip()
    if explicit:
        return slugify_machine(explicit)
    try:
        return slugify_machine(socket.gethostname())
    except Exception:
        return "unknown-machine"


def machine_relay_dir(machine: Optional[str] = None) -> Path:
    m = resolve_machine(machine)
    mdir = relay_root() / m
    mdir.mkdir(parents=True, exist_ok=True)
    return mdir


def now_utc_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def today_utc_str() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


class RelayError(RuntimeError):
    """Custom exception for operational relay errors."""
    pass


# ---------------------------------------------------------------------------
# Tool Implementations
# ---------------------------------------------------------------------------

def tool_relay_status(machine: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    m = resolve_machine(machine)
    mdir = machine_relay_dir(m)
    current_file = mdir / "current.json"
    session_file = mdir / ".current_session"
    last_mid_file = mdir / ".last_mid"

    current_data: Dict[str, Any] = {}
    if current_file.exists():
        try:
            with open(current_file, "r", encoding="utf-8") as f:
                current_data = json.load(f)
        except Exception as e:
            current_data = {"error": f"Failed reading current.json: {e}"}

    session_id = None
    if session_file.exists():
        try:
            session_id = session_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    last_mid = None
    if last_mid_file.exists():
        try:
            last_mid = last_mid_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    # Git status check on relay root
    git_info: Dict[str, Any] = {"clean": True, "branch": "unknown", "remote": None}
    r_root = relay_root()
    if (r_root / ".git").exists():
        try:
            res_branch = subprocess.run(
                ["git", "-C", str(r_root), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW
            )
            if res_branch.returncode == 0:
                git_info["branch"] = res_branch.stdout.strip()

            res_remote = subprocess.run(
                ["git", "-C", str(r_root), "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW
            )
            if res_remote.returncode == 0:
                git_info["remote"] = res_remote.stdout.strip()

            res_status = subprocess.run(
                ["git", "-C", str(r_root), "status", "--porcelain"],
                capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW
            )
            if res_status.returncode == 0:
                uncommitted = [line for line in res_status.stdout.splitlines() if line.strip()]
                git_info["clean"] = len(uncommitted) == 0
                git_info["uncommitted_count"] = len(uncommitted)
        except Exception as exc:
            git_info["git_error"] = str(exc)

    # Find latest baton
    baton_files = sorted(mdir.glob("baton_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    latest_baton = baton_files[0].name if baton_files else None

    result_data = {
        "machine": m,
        "relay_root": str(r_root),
        "machine_dir": str(mdir),
        "active": current_data.get("active", False),
        "phase": current_data.get("phase", "none"),
        "mission": current_data.get("mission", "None set"),
        "session_id": current_data.get("session", session_id),
        "updated_utc": current_data.get("updated_utc"),
        "last_mid": last_mid,
        "latest_baton_file": latest_baton,
        "git": git_info
    }

    prose = (
        f"NouGenRelay Node Status: [{m}]\n"
        f"Active Session: {result_data['session_id'] or 'None'} (Phase: {result_data['phase']})\n"
        f"Mission: {result_data['mission']}\n"
        f"Last Update: {result_data['updated_utc'] or 'Never'}\n"
        f"Latest Baton: {latest_baton or 'No batons logged'}\n"
        f"Git Transport: branch '{git_info['branch']}' on {git_info.get('remote') or 'local'} (clean: {git_info['clean']})"
    )
    return prose, result_data


def tool_relay_start_session(
    mission: str,
    machine: Optional[str] = None,
    session_id: Optional[str] = None,
    note: Optional[str] = None
) -> Tuple[str, Dict[str, Any]]:
    m = resolve_machine(machine)
    mdir = machine_relay_dir(m)
    now = now_utc_iso()
    today = today_utc_str()

    sid = (session_id or "").strip()
    if not sid:
        sid = secrets.token_hex(4)

    # Write .current_session
    session_file = mdir / ".current_session"
    session_file.write_text(sid, encoding="utf-8")

    # Prepare initial baton
    baton_file = mdir / f"baton_{today}_{sid}.json"
    baton_data = {
        "schema": 1,
        "machine": m,
        "session": sid,
        "mission": mission,
        "legs": [
            {
                "phase": "start",
                "ts_utc": now,
                "note": note or f"Session started on {m}",
                "totals": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_read": 0,
                    "cache_creation": 0,
                    "reasoning": 0,
                    "invocations": 0
                },
                "confidence": 1.0
            }
        ]
    }

    with open(baton_file, "w", encoding="utf-8") as f:
        json.dump(baton_data, f, indent=2, sort_keys=True)

    # Update current.json
    current_file = mdir / "current.json"
    current_data = {
        "schema": 1,
        "machine": m,
        "session": sid,
        "mission": mission,
        "phase": "start",
        "active": True,
        "updated_utc": now
    }
    with open(current_file, "w", encoding="utf-8") as f:
        json.dump(current_data, f, indent=2, sort_keys=True)

    result_data = {
        "machine": m,
        "session_id": sid,
        "baton_file": str(baton_file),
        "mission": mission,
        "phase": "start",
        "created_utc": now
    }
    prose = (
        f"Started NouGenRelay Session [{sid}] for machine '{m}'.\n"
        f"Mission: {mission}\n"
        f"Baton File: {baton_file.name}\n"
        f"State: active=True, phase=start"
    )
    return prose, result_data


def tool_relay_checkpoint(
    note: str,
    confidence: Optional[float] = 1.0,
    tokens: Optional[Dict[str, int]] = None,
    machine: Optional[str] = None
) -> Tuple[str, Dict[str, Any]]:
    m = resolve_machine(machine)
    mdir = machine_relay_dir(m)
    now = now_utc_iso()

    current_file = mdir / "current.json"
    if not current_file.exists():
        raise RelayError(f"No active session found on machine '{m}'. Call relay_start_session first.")

    with open(current_file, "r", encoding="utf-8") as f:
        current_data = json.load(f)

    sid = current_data.get("session")
    if not sid:
        raise RelayError(f"current.json on machine '{m}' does not contain an active session ID.")

    # Locate baton file
    baton_candidates = list(mdir.glob(f"baton_*_{sid}.json"))
    if not baton_candidates:
        today = today_utc_str()
        baton_file = mdir / f"baton_{today}_{sid}.json"
        baton_data = {
            "schema": 1,
            "machine": m,
            "session": sid,
            "mission": current_data.get("mission", ""),
            "legs": []
        }
    else:
        baton_file = sorted(baton_candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        with open(baton_file, "r", encoding="utf-8") as f:
            baton_data = json.load(f)

    # Calculate or use tokens
    tok = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read": 0,
        "cache_creation": 0,
        "reasoning": 0,
        "invocations": 0
    }
    if tokens:
        for k in tok:
            if k in tokens:
                tok[k] = int(tokens[k])

    leg = {
        "phase": "mid",
        "ts_utc": now,
        "note": note,
        "totals": tok,
        "confidence": float(confidence if confidence is not None else 1.0)
    }

    baton_data.setdefault("legs", []).append(leg)
    with open(baton_file, "w", encoding="utf-8") as f:
        json.dump(baton_data, f, indent=2, sort_keys=True)

    # Update .last_mid and current.json
    (mdir / ".last_mid").write_text(now, encoding="utf-8")
    current_data["phase"] = "mid"
    current_data["active"] = True
    current_data["updated_utc"] = now
    with open(current_file, "w", encoding="utf-8") as f:
        json.dump(current_data, f, indent=2, sort_keys=True)

    leg_count = len(baton_data["legs"])
    result_data = {
        "machine": m,
        "session_id": sid,
        "leg_number": leg_count,
        "phase": "mid",
        "note": note,
        "confidence": leg["confidence"],
        "checkpoint_utc": now
    }
    prose = (
        f"NouGenRelay Checkpoint Leg #{leg_count} added for session [{sid}] on '{m}'.\n"
        f"Note: {note}\n"
        f"Confidence: {leg['confidence']:.4f}\n"
        f"Timestamp: {now}"
    )
    return prose, result_data


def tool_relay_handoff(
    summary: str,
    next_steps: Optional[str] = None,
    machine: Optional[str] = None
) -> Tuple[str, Dict[str, Any]]:
    m = resolve_machine(machine)
    mdir = machine_relay_dir(m)
    now = now_utc_iso()

    current_file = mdir / "current.json"
    if not current_file.exists():
        raise RelayError(f"No current.json found on machine '{m}'. Nothing to hand off.")

    with open(current_file, "r", encoding="utf-8") as f:
        current_data = json.load(f)

    sid = current_data.get("session")
    if not sid:
        raise RelayError(f"current.json on machine '{m}' does not contain an active session ID.")

    baton_candidates = list(mdir.glob(f"baton_*_{sid}.json"))
    if not baton_candidates:
        today = today_utc_str()
        baton_file = mdir / f"baton_{today}_{sid}.json"
        baton_data = {"schema": 1, "machine": m, "session": sid, "mission": current_data.get("mission", ""), "legs": []}
    else:
        baton_file = sorted(baton_candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        with open(baton_file, "r", encoding="utf-8") as f:
            baton_data = json.load(f)

    note_text = summary
    if next_steps:
        note_text += f"\nNext Steps: {next_steps}"

    closing_leg = {
        "phase": "end",
        "ts_utc": now,
        "note": note_text,
        "confidence": 1.0
    }
    baton_data.setdefault("legs", []).append(closing_leg)
    with open(baton_file, "w", encoding="utf-8") as f:
        json.dump(baton_data, f, indent=2, sort_keys=True)

    # Deactivate session in current.json
    current_data["phase"] = "end"
    current_data["active"] = False
    current_data["updated_utc"] = now
    current_data["last_handoff_summary"] = summary
    with open(current_file, "w", encoding="utf-8") as f:
        json.dump(current_data, f, indent=2, sort_keys=True)

    result_data = {
        "machine": m,
        "session_id": sid,
        "mission": current_data.get("mission"),
        "total_legs": len(baton_data["legs"]),
        "handoff_summary": summary,
        "next_steps": next_steps or "None",
        "completed_utc": now
    }

    prose = (
        f"🏁 NouGenRelay Baton Handoff Completed for Session [{sid}] on '{m}'.\n"
        f"Mission: {current_data.get('mission')}\n"
        f"Total Legs Recorded: {result_data['total_legs']}\n"
        f"Summary: {summary}\n"
        f"Next Steps: {result_data['next_steps']}\n"
        f"Session is now marked inactive (ready for handoff pickup)."
    )
    return prose, result_data


def tool_relay_read_baton(
    session_id: Optional[str] = None,
    machine: Optional[str] = None,
    limit_legs: int = 10
) -> Tuple[str, Dict[str, Any]]:
    m = resolve_machine(machine)
    mdir = machine_relay_dir(m)

    if session_id:
        batons = list(mdir.glob(f"baton_*_{session_id}.json"))
    else:
        batons = sorted(mdir.glob("baton_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not batons:
        msg = f"No baton logs found for machine '{m}'" + (f" and session '{session_id}'" if session_id else "")
        return msg, {"machine": m, "batons": []}

    baton_file = batons[0]
    with open(baton_file, "r", encoding="utf-8") as f:
        baton_data = json.load(f)

    legs = baton_data.get("legs", [])
    recent_legs = legs[-limit_legs:] if limit_legs > 0 else legs

    summary_lines = [
        f"Baton File: {baton_file.name} (Machine: {baton_data.get('machine')}, Session: {baton_data.get('session')})",
        f"Mission: {baton_data.get('mission')}",
        f"Total Legs: {len(legs)} (Showing last {len(recent_legs)})",
        "--- Legs Timeline ---"
    ]
    for i, leg in enumerate(recent_legs, start=max(1, len(legs) - len(recent_legs) + 1)):
        p = leg.get("phase", "unknown").upper()
        ts = leg.get("ts_utc", "")
        note = leg.get("note", "").replace("\n", " ")
        conf = leg.get("confidence")
        conf_str = f" [conf: {conf:.2f}]" if conf is not None else ""
        summary_lines.append(f"  #{i} [{p}] {ts}{conf_str}: {note[:120]}")

    return "\n".join(summary_lines), {
        "file": str(baton_file),
        "machine": baton_data.get("machine"),
        "session": baton_data.get("session"),
        "mission": baton_data.get("mission"),
        "total_legs": len(legs),
        "legs": recent_legs
    }


def tool_relay_fleet_status() -> Tuple[str, Dict[str, Any]]:
    root = relay_root()
    machines_data = []

    for item in sorted(root.iterdir()):
        if not item.is_dir() or item.name.startswith(".") or item.name in ("archive", "__pycache__"):
            continue
        m = item.name
        curr = item / "current.json"
        data: Dict[str, Any] = {"machine": m, "active": False, "session": None, "mission": None, "updated_utc": None}
        if curr.exists():
            try:
                with open(curr, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                data.update({
                    "active": cdata.get("active", False),
                    "session": cdata.get("session"),
                    "mission": cdata.get("mission"),
                    "phase": cdata.get("phase"),
                    "updated_utc": cdata.get("updated_utc")
                })
            except Exception:
                pass
        machines_data.append(data)

    lines = [f"NouGenRelay Fleet Status ({len(machines_data)} machines registered):"]
    for md in machines_data:
        status_marker = "🟢 ACTIVE" if md["active"] else "⚪ IDLE"
        lines.append(
            f"  {status_marker} {md['machine']} (Phase: {md.get('phase', 'none')}, Session: {md.get('session') or '-'})\n"
            f"      Mission: {md.get('mission') or 'None'}\n"
            f"      Last Seen: {md.get('updated_utc') or 'Unknown'}"
        )

    return "\n".join(lines), {"machine_count": len(machines_data), "fleet": machines_data}


def tool_relay_sync(action: str = "status") -> Tuple[str, Dict[str, Any]]:
    r_root = relay_root()
    if not (r_root / ".git").exists():
        raise RelayError(f"Relay root {r_root} is not a git repository.")

    action = action.lower().strip()
    if action not in ("status", "fetch", "pull", "diff", "push"):
        raise RelayError(f"Invalid action '{action}'. Supported: status, fetch, pull, diff, push")

    cmd = ["git", "-C", str(r_root)]
    if action == "status":
        cmd.extend(["status", "--short", "--branch"])
    elif action == "fetch":
        cmd.extend(["fetch", "origin"])
    elif action == "pull":
        cmd.extend(["pull", "--ff-only", "origin", "relay"])
    elif action == "diff":
        cmd.extend(["diff", "--stat"])
    elif action == "push":
        # Safe commit and push for active machine
        m = resolve_machine()
        # Stage only machine directory to enforce namespace isolation
        try:
            subprocess.run(["git", "-C", str(r_root), "add", m], capture_output=True, check=False, timeout=10, stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW)
            commit_msg = f"relay: {m} {now_utc_iso()[:16]}Z"
            subprocess.run(["git", "-C", str(r_root), "commit", "-m", commit_msg], capture_output=True, check=False, timeout=20, stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW)
        except subprocess.TimeoutExpired as exc:
            raise RelayError(f"git stage/commit timed out in {r_root} (check signing/hooks): {exc}")
        cmd.extend(["push", "origin", "relay"])

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW)
        stdout = res.stdout.strip()
        stderr = res.stderr.strip()
        out = stdout or stderr or "(clean / no output)"
        success = (res.returncode == 0)
    except Exception as exc:
        raise RelayError(f"Git command failed: {exc}")

    prose = f"NouGenRelay git {action} (exit {res.returncode}):\n{out}"
    return prose, {"action": action, "returncode": res.returncode, "output": out, "success": success}


# ---------------------------------------------------------------------------
# NouGenMsg Tool Implementations (Grounded in Local Inbox & Pipe Storage)
# ---------------------------------------------------------------------------

def _inbox_dir() -> Path:
    explicit = os.environ.get("NOUGEN_AGY_INBOX", "").strip()
    if explicit:
        p = Path(explicit)
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = Path.home() / ".nougen" / "agy_inbox"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _outbox_dir(machine: Optional[str] = None) -> Path:
    """Per-machine relay mailbox. Writes stay inside this node's namespace so git pushes never conflict."""
    p = machine_relay_dir(machine) / "nougenmsg"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _message_files() -> List[Path]:
    """Local inbox plus every node's relay mailbox (arrives via relay_sync pull), newest first, de-duplicated by id."""
    files: List[Path] = list(_inbox_dir().glob("*.json"))
    try:
        files.extend(relay_root().glob("*/nougenmsg/*.json"))
    except Exception:
        pass
    seen: Dict[str, Path] = {}
    for f in files:
        try:
            if f.stem not in seen or os.path.getmtime(f) > os.path.getmtime(seen[f.stem]):
                seen[f.stem] = f
        except OSError:
            continue
    return sorted(seen.values(), key=os.path.getmtime, reverse=True)


def _parse_envelope(raw_dict: Dict[str, Any], filepath: Optional[Path] = None) -> Dict[str, Any]:
    """Normalize raw message json into canonical NouGenMsg envelope."""
    msg_id = raw_dict.get("id") or raw_dict.get("event_id") or (filepath.stem if filepath else f"msg_{int(time.time()*1000)}")
    ts = raw_dict.get("timestamp") or (filepath.stat().st_mtime if filepath and filepath.is_file() else time.time())
    ts_iso = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).isoformat()

    sender_raw = raw_dict.get("sender") or raw_dict.get("source") or "unknown"
    sender_dict = sender_raw if isinstance(sender_raw, dict) else {}

    origin_machine = sender_dict.get("node") or (sender_raw if isinstance(sender_raw, str) and not sender_raw.startswith("{") else resolve_machine())
    origin_agent = sender_dict.get("agent") or raw_dict.get("agent") or "unknown-agent"
    origin_provider = sender_dict.get("provider") or raw_dict.get("provider") or "local"

    judgment = raw_dict.get("wake_judgment", {})
    origin_verified = bool(judgment.get("approved") or "owner verified" in str(judgment.get("reason", "")).lower())

    return {
        "id": msg_id,
        "created_utc": raw_dict.get("created_utc") or ts_iso,
        "timestamp": ts,
        "origin_machine": origin_machine,
        "origin_agent": origin_agent,
        "origin_provider": origin_provider,
        "origin_verified": origin_verified,
        "destination": raw_dict.get("target") or raw_dict.get("destination") or "antigravity",
        "audience": raw_dict.get("audience") or "agent",
        "message_type": raw_dict.get("type") or "live_message",
        "body": raw_dict.get("text") or raw_dict.get("content") or raw_dict.get("body") or "",
        "reply_to": raw_dict.get("reply_to"),
        "correlation_id": raw_dict.get("correlation_id") or raw_dict.get("leg_id"),
        "trigger_source": raw_dict.get("trigger_source") or ("relay" if raw_dict.get("leg_id") else "nougenmsg"),
        "status": raw_dict.get("status") or "delivered",
    }


def tool_nougenmsg_latest(limit: int = 10) -> Tuple[str, Dict[str, Any]]:
    inbox = _inbox_dir()
    files = _message_files()
    recent = files[:max(1, limit)]

    messages = []
    for f in recent:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            messages.append(_parse_envelope(d, f))
        except Exception:
            continue

    summary_lines = [
        f"NouGenMsg Latest ({len(messages)} of {len(files)} total):",
        "--- Messages Stream ---"
    ]
    for m in messages:
        sender_str = f"{m['origin_machine']}/{m['origin_agent']}"
        body_snip = m['body'].replace('\n', ' ')[:100]
        summary_lines.append(f"  • [{m['created_utc'][:19]}Z] [{sender_str}] -> [{m['destination']}]: {body_snip}")

    return "\n".join(summary_lines), {
        "complete": True,
        "total_messages": len(files),
        "returned": len(messages),
        "messages": messages
    }


def tool_nougenmsg_inbox(target: Optional[str] = None, limit: int = 10) -> Tuple[str, Dict[str, Any]]:
    inbox = _inbox_dir()
    files = _message_files()
    target_clean = (target or "").lower().strip()

    messages = []
    for f in files:
        if len(messages) >= max(1, limit):
            break
        try:
            with open(f, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            env = _parse_envelope(d, f)
            if target_clean:
                dest = env["destination"].lower()
                if target_clean not in dest and dest not in target_clean:
                    continue
            messages.append(env)
        except Exception:
            continue

    summary_lines = [
        f"NouGenMsg Inbox (target: {target or 'all'}, returned: {len(messages)}):",
        "--- Inbox Messages ---"
    ]
    for m in messages:
        sender_str = f"{m['origin_machine']}/{m['origin_agent']}"
        summary_lines.append(f"  • [{m['created_utc'][:19]}Z] from {sender_str}: {m['body'][:100]}")

    return "\n".join(summary_lines), {
        "complete": True,
        "target": target or "all",
        "returned": len(messages),
        "messages": messages
    }


def tool_nougenmsg_read(message_id: str) -> Tuple[str, Dict[str, Any]]:
    inbox = _inbox_dir()
    target_f = None
    for f in _message_files():
        if message_id in f.stem or f.stem in message_id:
            target_f = f
            break

    if not target_f or not target_f.is_file():
        raise RelayError(f"Message ID '{message_id}' not found in inbox.")

    with open(target_f, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    envelope = _parse_envelope(raw, target_f)

    prose = (
        f"NouGenMsg [{envelope['id']}]\n"
        f"  Created: {envelope['created_utc']}\n"
        f"  Origin: {envelope['origin_machine']} / {envelope['origin_agent']} (Verified: {envelope['origin_verified']})\n"
        f"  Destination: {envelope['destination']}\n"
        f"  Type: {envelope['message_type']} | Trigger: {envelope['trigger_source']}\n"
        f"\nBody:\n{envelope['body']}"
    )
    return prose, envelope


def tool_nougenmsg_search(query: Optional[str] = None, origin: Optional[str] = None, destination: Optional[str] = None, limit: int = 10) -> Tuple[str, Dict[str, Any]]:
    inbox = _inbox_dir()
    files = _message_files()
    q_lower = (query or "").lower().strip()
    orig_lower = (origin or "").lower().strip()
    dest_lower = (destination or "").lower().strip()

    matches = []
    for f in files:
        if len(matches) >= max(1, limit):
            break
        try:
            with open(f, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            env = _parse_envelope(d, f)
            if q_lower and (q_lower not in env["body"].lower() and q_lower not in env["id"].lower()):
                continue
            if orig_lower and (orig_lower not in env["origin_machine"].lower() and orig_lower not in env["origin_agent"].lower()):
                continue
            if dest_lower and (dest_lower not in env["destination"].lower()):
                continue
            matches.append(env)
        except Exception:
            continue

    summary_lines = [
        f"NouGenMsg Search (query='{query or ''}', matches: {len(matches)}):",
        "--- Matched Messages ---"
    ]
    for m in matches:
        summary_lines.append(f"  • [{m['created_utc'][:19]}Z] {m['origin_machine']} -> {m['destination']}: {m['body'][:90]}")

    return "\n".join(summary_lines), {
        "complete": True,
        "query": query,
        "returned": len(matches),
        "messages": matches
    }


def tool_nougenmsg_send(
    body: str,
    target: str = "all",
    message_type: str = "live_message",
    agent: str = "antigravity",
    reply_to: Optional[str] = None,
    correlation_id: Optional[str] = None,
    push: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    body = (body or "").strip()
    if not body:
        raise RelayError("Message body is empty.")
    machine = resolve_machine()
    ts = time.time()
    msg_id = f"msg_{machine}_{int(ts * 1000)}_{secrets.token_hex(3)}"
    raw = {
        "id": msg_id,
        "created_utc": now_utc_iso(),
        "timestamp": ts,
        "sender": {"node": machine, "agent": agent, "provider": "local"},
        "target": target or "all",
        "audience": "agent",
        "type": message_type,
        "body": body,
        "reply_to": reply_to,
        "correlation_id": correlation_id,
        "trigger_source": "nougenmsg",
        "status": "sent",
    }
    written = []
    for d in (_outbox_dir(machine), _inbox_dir()):
        p = d / f"{msg_id}.json"
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(raw, fh, indent=2)
        written.append(str(p))

    push_info: Dict[str, Any] = {"pushed": False}
    if push:
        try:
            _, push_info = tool_relay_sync("push")
            push_info["pushed"] = bool(push_info.get("success"))
        except RelayError as exc:
            push_info = {"pushed": False, "error": str(exc)}

    prose = (
        f"NouGenMsg SENT [{msg_id}] {machine}/{agent} -> [{raw['target']}]\n"
        f"  Written: {len(written)} file(s) | Pushed to fleet: {push_info.get('pushed')}"
        + (f" ({push_info.get('error') or push_info.get('output', '')[:120]})" if push else "")
    )
    return prose, {"id": msg_id, "target": raw["target"], "files": written, **push_info}


# ---------------------------------------------------------------------------
# MCP Tool Registry & Schemas
# ---------------------------------------------------------------------------

TOOLS: Dict[str, Dict[str, Any]] = {
    "relay_status": {
        "fn": tool_relay_status,
        "title": "Relay node status",
        "description": "Inspect the local or specified machine's NouGenRelay state, active mission, session ID, phase, and git bus status.",
        "schema": {
            "type": "object",
            "properties": {
                "machine": {"type": "string", "description": "Machine name slug (e.g. blade1tb, phoebus). Defaults to local node."}
            },
            "additionalProperties": False
        }
    },
    "relay_start_session": {
        "fn": tool_relay_start_session,
        "title": "Start relay session",
        "description": "Initialize a fresh mission session on this node, allocate an 8-char hex session ID, and create the initial baton leg.",
        "schema": {
            "type": "object",
            "properties": {
                "mission": {"type": "string", "description": "Clear statement of session mission or objective."},
                "machine": {"type": "string", "description": "Optional machine slug override."},
                "session_id": {"type": "string", "description": "Optional custom 8-hex session ID."},
                "note": {"type": "string", "description": "Optional kickoff note."}
            },
            "required": ["mission"],
            "additionalProperties": False
        }
    },
    "relay_checkpoint": {
        "fn": tool_relay_checkpoint,
        "title": "Checkpoint baton progress",
        "description": "Record a mid-session progress milestone leg on the active baton with notes, confidence score, and optional token tracking.",
        "schema": {
            "type": "object",
            "properties": {
                "note": {"type": "string", "description": "Progress note summarizing completed work or milestone."},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0, "description": "Confidence ratio (0.0 to 1.0) of results."},
                "tokens": {
                    "type": "object",
                    "properties": {
                        "input_tokens": {"type": "integer"},
                        "output_tokens": {"type": "integer"},
                        "cache_read": {"type": "integer"},
                        "cache_creation": {"type": "integer"},
                        "reasoning": {"type": "integer"},
                        "invocations": {"type": "integer"}
                    },
                    "description": "Optional token breakdown for this leg."
                },
                "machine": {"type": "string", "description": "Optional machine slug override."}
            },
            "required": ["note"],
            "additionalProperties": False
        }
    },
    "relay_handoff": {
        "fn": tool_relay_handoff,
        "title": "Complete session and hand off",
        "description": "Seal the active session baton with a final end leg and emit a clean handoff summary for subsequent agents.",
        "schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Comprehensive summary of findings, code changes, and resolved state."},
                "next_steps": {"type": "string", "description": "Actionable instructions for the next agent picking up this baton."},
                "machine": {"type": "string", "description": "Optional machine slug override."}
            },
            "required": ["summary"],
            "additionalProperties": False
        }
    },
    "relay_read_baton": {
        "fn": tool_relay_read_baton,
        "title": "Read session baton",
        "description": "Read and inspect historical or active session baton legs, timestamps, notes, and metrics for continuity.",
        "schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Specific session hex ID. If omitted, reads most recent baton."},
                "machine": {"type": "string", "description": "Optional machine slug override."},
                "limit_legs": {"type": "integer", "default": 10, "description": "Maximum number of recent legs to return."}
            },
            "additionalProperties": False
        }
    },
    "relay_fleet_status": {
        "fn": tool_relay_fleet_status,
        "title": "Fleet relay overview",
        "description": "Scan and report all machines registered in the relay transport, their active states, and recent mission timestamps.",
        "schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    },
    "relay_sync": {
        "fn": tool_relay_sync,
        "title": "Sync relay transport via git",
        "description": "Execute git transport commands (status, fetch, pull, diff, push) on the relay repository.",
        "schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "fetch", "pull", "diff", "push"],
                    "default": "status",
                    "description": "Git transport action."
                }
            },
            "additionalProperties": False
        }
    },
    "nougenmsg_latest": {
        "fn": tool_nougenmsg_latest,
        "title": "Latest NouGen messages",
        "description": "Read newest inter-agent and fleet messages from the NouGenMsg bus ordered by creation timestamp.",
        "schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10, "description": "Maximum messages to return."}
            },
            "additionalProperties": False
        }
    },
    "nougenmsg_inbox": {
        "fn": tool_nougenmsg_inbox,
        "title": "NouGen inbox messages",
        "description": "Read messages addressed to a specific agent, lane, node, or audience.",
        "schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Filter by destination (e.g. antigravity, codex, blade, all)."},
                "limit": {"type": "integer", "default": 10, "description": "Maximum messages to return."}
            },
            "additionalProperties": False
        }
    },
    "nougenmsg_read": {
        "fn": tool_nougenmsg_read,
        "title": "Read single NouGen message",
        "description": "Retrieve the complete canonical envelope and body for a specific NouGen message ID.",
        "schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Exact message ID or filename identifier."}
            },
            "required": ["message_id"],
            "additionalProperties": False
        }
    },
    "nougenmsg_search": {
        "fn": tool_nougenmsg_search,
        "title": "Search NouGen message history",
        "description": "Search historical NouGen messages by keyword, origin node/agent, or destination.",
        "schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text query to match in body or ID."},
                "origin": {"type": "string", "description": "Filter by sender node or agent."},
                "destination": {"type": "string", "description": "Filter by target destination."},
                "limit": {"type": "integer", "default": 10, "description": "Maximum results to return."}
            },
            "additionalProperties": False
        }
    },
    "nougenmsg_send": {
        "fn": tool_nougenmsg_send,
        "title": "Send a NouGen message",
        "description": "Send a message to a node/agent or 'all'. Writes to this node's relay mailbox (relay/<machine>/nougenmsg/) and local inbox; push=true ships it to every node via the relay git bus.",
        "schema": {
            "type": "object",
            "properties": {
                "body": {"type": "string", "description": "Message text."},
                "target": {"type": "string", "default": "all", "description": "Destination node/agent (apollo, hyperion, phoebus, codex, ...) or 'all'."},
                "message_type": {"type": "string", "default": "live_message", "description": "Message type label (live_message, broadcast, directive, ack)."},
                "agent": {"type": "string", "default": "antigravity", "description": "Sending agent name."},
                "reply_to": {"type": "string", "description": "Message ID being replied to."},
                "correlation_id": {"type": "string", "description": "Optional baton leg or thread ID."},
                "push": {"type": "boolean", "default": True, "description": "Commit and push the relay so other nodes receive it."}
            },
            "required": ["body"],
            "additionalProperties": False
        }
    }
}


def tool_descriptor(name: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": name,
        "title": spec["title"],
        "description": spec["description"],
        "inputSchema": spec["schema"],
    }


# ---------------------------------------------------------------------------
# JSON-RPC Protocol Loop
# ---------------------------------------------------------------------------

def send_rpc(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def respond_rpc(msg_id: Any, result: Any = None, error: Optional[Dict[str, Any]] = None) -> None:
    payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    send_rpc(payload)


def call_tool_rpc(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    spec = TOOLS.get(name)
    if not spec:
        raise KeyError(name)
    allowed = set(spec["schema"].get("properties", {}))
    unknown = set(args) - allowed
    if unknown:
        raise ValueError(f"Unknown argument(s): {', '.join(sorted(unknown))}")
    text, data = spec["fn"](**args)
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": data,
        "isError": False
    }


def handle_rpc(message: Dict[str, Any]) -> None:
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        respond_rpc(msg_id, {
            "protocolVersion": PREFERRED_PROTOCOL,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False}
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": VERSION,
                "title": "NouGenRelay Fleet Handoff & Baton Transport"
            },
            "instructions": (
                "Coordinate decentralized fleet work across nodes using git-backed batons. "
                "Inspect status with relay_status, start sessions with relay_start_session, "
                "checkpoint milestones with relay_checkpoint, and pass batons with relay_handoff."
            )
        })
    elif method in ("notifications/initialized", "initialized", "ping"):
        if method == "ping" and msg_id is not None:
            respond_rpc(msg_id, {})
    elif method == "tools/list":
        respond_rpc(msg_id, {"tools": [tool_descriptor(n, s) for n, s in TOOLS.items()]})
    elif method == "resources/list":
        respond_rpc(msg_id, {"resources": []})
    elif method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            res = call_tool_rpc(name, args)
            respond_rpc(msg_id, res)
        except KeyError:
            respond_rpc(msg_id, error={"code": -32601, "message": f"Tool not found: {name}"})
        except ValueError as exc:
            respond_rpc(msg_id, error={"code": -32602, "message": str(exc)})
        except RelayError as exc:
            respond_rpc(msg_id, {"content": [{"type": "text", "text": f"Relay Error: {exc}"}], "isError": True})
        except Exception as exc:
            log(f"Unhandled error in {name}: {exc}")
            respond_rpc(msg_id, error={"code": -32603, "message": f"Internal error: {exc}"})
    else:
        if msg_id is not None:
            respond_rpc(msg_id, error={"code": -32601, "message": f"Method '{method}' not implemented."})


def run_selftest() -> int:
    print(f"[{SERVER_NAME}] Running self-test suite...")
    status_prose, status_data = tool_relay_status()
    assert "machine" in status_data, "relay_status missing machine"
    print(f"  [OK] relay_status ok (machine: {status_data['machine']})")

    fleet_prose, fleet_data = tool_relay_fleet_status()
    assert "machine_count" in fleet_data, "relay_fleet_status missing machine_count"
    print(f"  [OK] relay_fleet_status ok ({fleet_data['machine_count']} machines)")

    baton_prose, baton_data = tool_relay_read_baton(limit_legs=3)
    print(f"  [OK] relay_read_baton ok ({baton_data.get('total_legs', 0)} legs)")

    git_prose, git_data = tool_relay_sync(action="status")
    print(f"  [OK] relay_sync ok (status returncode: {git_data.get('returncode')})")

    # NouGenMsg tests
    msg_prose, msg_data = tool_nougenmsg_latest(limit=3)
    assert "messages" in msg_data, "nougenmsg_latest missing messages"
    print(f"  [OK] nougenmsg_latest ok ({len(msg_data['messages'])} returned)")

    inbox_prose, inbox_data = tool_nougenmsg_inbox(limit=3)
    assert "messages" in inbox_data, "nougenmsg_inbox missing messages"
    print(f"  [OK] nougenmsg_inbox ok ({len(inbox_data['messages'])} returned)")

    search_prose, search_data = tool_nougenmsg_search(query="relay", limit=3)
    assert "messages" in search_data, "nougenmsg_search missing messages"
    print(f"  [OK] nougenmsg_search ok ({len(search_data['messages'])} matches for 'relay')")

    send_prose, send_data = tool_nougenmsg_send(body="selftest ping", target="selftest", push=False)
    _, read_back = tool_nougenmsg_read(send_data["id"])
    assert read_back["body"] == "selftest ping", "nougenmsg_send round-trip failed"
    for fp in send_data["files"]:
        Path(fp).unlink(missing_ok=True)
    print(f"  [OK] nougenmsg_send ok (round-trip {send_data['id']})")

    print(f"[{SERVER_NAME}] All self-tests passed successfully!")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="NouGenRelay MCP Server")
    parser.add_argument("--selftest", action="store_true", help="Run self-tests and exit")
    args = parser.parse_args()

    if args.selftest:
        sys.exit(run_selftest())

    log(f"Starting server v{VERSION} on stdio (PID: {os.getpid()})")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            handle_rpc(msg)
        except json.JSONDecodeError:
            respond_rpc(None, error={"code": -32700, "message": "Parse error"})
        except Exception as exc:
            log(f"Fatal error handling input: {exc}")


if __name__ == "__main__":
    main()

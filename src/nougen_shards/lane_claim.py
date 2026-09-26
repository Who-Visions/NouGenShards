"""Native NouGen Lane Claim & Autonomous Execution Enforcement.

Ensures that whenever any agent or lane claims a work scope:
1. The claim is recorded in the shared handoffs/claims registry.
2. The claim is replicated natively into the NouGen shard memory cluster.
3. An immediate wake + execution enforcement event is dispatched across the
   NouGenMsg bus and local agent pipes, forcing the claimed lane to execute
   substantive work without pausing.
"""
from __future__ import annotations

import fnmatch
import json
import os
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def resolve_claims_dir() -> Path:
    env_dir = os.environ.get("NOUGEN_RELAY_LOCAL_DIR") or os.environ.get("NOUGEN_RELAY_DIR")
    if env_dir and Path(env_dir).exists():
        p = Path(env_dir)
        return (p / ".handoffs" / "claims") if not p.name.endswith(".handoffs") else (p / "claims")
    candidates = [
        Path.home() / ".nougen" / "relay" / ".handoffs" / "claims",
        Path.home() / ".nougen" / "claims",
        Path.home() / "Outpost" / "NouGenRelay" / ".handoffs" / "claims",
        Path.home() / "Watchtower" / "NouGen" / "NouGenRelay" / ".handoffs" / "claims",
        Path(__file__).resolve().parents[2] / ".handoffs" / "claims",
    ]
    for c in candidates:
        try:
            if c.parent.is_dir() or c.is_dir():
                return c
        except OSError:
            continue
    return Path.home() / ".nougen" / "claims"


CLAIMS_DIR = resolve_claims_dir()
AGENT = os.environ.get("NOUGEN_AGENT", "antigravity")
MACHINE = os.environ.get("COMPUTERNAME", socket.gethostname()).lower()
TTL_HOURS = float(os.environ.get("NOUGEN_CLAIM_TTL_HOURS", 8))


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def my_claim_path(agent: Optional[str] = None, machine: Optional[str] = None) -> Path:
    a = agent or AGENT
    m = (machine or MACHINE).lower()
    return CLAIMS_DIR / f"{m}__{a}.json"


def active_claims(claims_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    cdir = claims_dir or CLAIMS_DIR
    out = []
    if not cdir.is_dir():
        return out
    for f in cdir.glob("*.json"):
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if c.get("status") == "released":
            continue
        try:
            born = datetime.strptime(c["created_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        ttl = float(c.get("ttl_hours", 8))
        if (datetime.now(timezone.utc) - born).total_seconds() < ttl * 3600:
            out.append(c)
    return out


def conflicts_for(paths: List[str], me_agent: str, me_machine: str,
                  claims_dir: Optional[Path] = None) -> List[Tuple[str, Dict[str, Any]]]:
    """Return list of (path, conflicting_claim) for paths claimed by someone else."""
    hits = []
    for c in active_claims(claims_dir=claims_dir):
        if c.get("agent") == me_agent and str(c.get("machine", "")).lower() == me_machine.lower():
            continue
        scopes = c.get("scope", "")
        scopes = scopes if isinstance(scopes, list) else [s.strip() for s in str(scopes).split(",") if s.strip()]
        for p in paths:
            norm = p.replace("\\", "/")
            for scope in scopes:
                if fnmatch.fnmatch(norm, scope) or norm == scope:
                    hits.append((p, c))
    return hits


def replicate_to_nougen_shards(claim: Dict[str, Any]) -> bool:
    """Store claim into the native NouGen shard cluster."""
    try:
        from .core import capture
        title = f"Lane Claim: {claim.get('machine')}/{claim.get('agent')} - {claim.get('goal')}"
        content = json.dumps(claim, indent=2)
        tags = ["lane_claim", str(claim.get("agent")), str(claim.get("machine"))]
        return bool(capture(
            event_type="lane_claim",
            title=title,
            content=content,
            tags=tags,
            source_uri=f"nougen://claims/{claim.get('machine')}/{claim.get('agent')}",
        ))
    except Exception:
        return False


def dispatch_lane_wake(claim: Dict[str, Any]) -> Dict[str, Any]:
    """Emit priority wake ping over NouGenMsg bus and local inboxes."""
    agent = claim.get("agent", "all")
    machine = claim.get("machine", "local")
    scope = claim.get("scope", [])
    goal = claim.get("goal", "working")
    wake_text = (
        f"🚨 [MANDATORY LANE WORK EXECUTION] Claim on {scope} active for {machine}/{agent}. "
        f"Goal: {goal}. Immediately execute substantive physical engineering work."
    )

    results: Dict[str, Any] = {}
    try:
        from .nougenmsg import NouGenMsgBus
        origin = {
            "trigger_source": "lane_claim",
            "lane": agent,
            "machine": machine,
            "timestamp": datetime.now(timezone.utc).timestamp(),
        }
        res = NouGenMsgBus.live_ping(target=agent, text=wake_text, origin=origin)
        results["local_ping"] = res
    except Exception as exc:
        results["local_ping_err"] = str(exc)

    # Deliver to local inbox for Antigravity continuation hooks
    inbox = Path.home() / ".nougen" / "agy_inbox"
    try:
        inbox.mkdir(parents=True, exist_ok=True)
        mid = f"claim_{int(datetime.now(timezone.utc).timestamp() * 1000)}_{agent}"
        msg_file = inbox / f"{mid}.json"
        msg_payload = {
            "type": "live_message",
            "priority": "high",
            "sender": f"claim:{machine}/{agent}",
            "target": agent,
            "text": wake_text,
            "claim": claim,
            "timestamp": datetime.now(timezone.utc).timestamp(),
        }
        msg_file.write_text(json.dumps(msg_payload, indent=2), encoding="utf-8")
        results["inbox_written"] = str(msg_file)
    except Exception as exc:
        results["inbox_err"] = str(exc)

    return results


def claim_lane(
    scope: List[str],
    goal: str = "working",
    agent: Optional[str] = None,
    machine: Optional[str] = None,
    ttl_hours: Optional[float] = None,
    execute_cmd: Optional[str] = None,
    claims_dir: Optional[Path] = None,
    replicate_shard: bool = True,
    notify: bool = True,
) -> Dict[str, Any]:
    """Declare an active lane claim, replicate natively, and enforce execution."""
    cdir = claims_dir or CLAIMS_DIR
    cdir.mkdir(parents=True, exist_ok=True)
    a = agent or AGENT
    m = (machine or MACHINE).lower()
    ttl = ttl_hours if ttl_hours is not None else TTL_HOURS

    claim = {
        "machine": m,
        "agent": a,
        "goal": goal,
        "scope": [s.replace("\\", "/") for s in scope],
        "created_utc": utc_now(),
        "ttl_hours": ttl,
        "status": "active",
    }
    p = cdir / f"{m}__{a}.json"
    p.write_text(json.dumps(claim, indent=2), encoding="utf-8")

    result: Dict[str, Any] = {
        "status": "claimed",
        "claim": claim,
        "path": str(p),
    }

    if replicate_shard:
        result["shard_replicated"] = replicate_to_nougen_shards(claim)

    if notify:
        result["wake_dispatch"] = dispatch_lane_wake(claim)

    if execute_cmd:
        try:
            proc = subprocess.Popen(
                execute_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            result["execution_pid"] = proc.pid
            result["execution_command"] = execute_cmd
        except Exception as exc:
            result["execution_error"] = str(exc)

    return result


def release_lane(agent: Optional[str] = None, machine: Optional[str] = None,
                 claims_dir: Optional[Path] = None) -> bool:
    """Release active claim on file."""
    cdir = claims_dir or CLAIMS_DIR
    a = agent or AGENT
    m = (machine or MACHINE).lower()
    p = cdir / f"{m}__{a}.json"
    if not p.exists():
        return False
    try:
        c = json.loads(p.read_text(encoding="utf-8"))
        c["status"] = "released"
        c["released_utc"] = utc_now()
        p.write_text(json.dumps(c, indent=2), encoding="utf-8")
        return True
    except (OSError, ValueError):
        return False

"""Native hi/bye/hijack session probes — the cross-platform, node-agnostic
successor to Yuki-Ai's Windows-only hi_probe.py / bye_probe.py / yuki_hijack.py.

Where those scripts hardcode %USERPROFILE%\\Outpost paths and a private
antigravity_memory.db, these probes read NOUGEN_HOME / repo discovery and
reuse this package's own handoff, machine, and relay plumbing — so the same
`nougen hi` / `nougen bye` works unmodified on phoebus, blade, or whoart.

hi   — session open: identity, fleet pulse, open handoffs, shard counts.
bye  — session close: dirty-repo sweep, handoff write, next-session primer.
hijack — force a foreign/legacy handoff or shard record to point at this
         node's canonical paths, for migrating an import from another agent.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from . import handoff, machine, relay_watch

# Repos this probe sweeps for dirty state. Override with NOUGEN_PROBE_REPOS
# (":"-separated absolute paths). Falls back to this repo plus any sibling
# checkouts one level up that look like git repos.
_ENV_REPOS = os.environ.get("NOUGEN_PROBE_REPOS")

# Ports a leftover dev/mesh process is likely bound to. Node-agnostic — no
# assumption about which ones this machine actually runs.
DEV_SERVER_PORTS = [
    (3000, "Node/React dev"),
    (5173, "Vite dev"),
    (8000, "Python HTTP/dev"),
    (8080, "Generic dev"),
    (8765, "Mesh service"),
    (4444, "NGS node (primary)"),
    (4445, "NGS node (secondary)"),
    (11434, "Ollama"),
]


def _discover_repos() -> List[Path]:
    if _ENV_REPOS:
        return [Path(p) for p in _ENV_REPOS.split(":") if p.strip()]
    repos = [handoff.PROJECT_ROOT]
    parent = handoff.PROJECT_ROOT.parent
    try:
        for child in parent.iterdir():
            if child.is_dir() and (child / ".git").exists() and child != handoff.PROJECT_ROOT:
                repos.append(child)
    except OSError:
        pass
    return repos


def _repo_git_status(repo: Path) -> Dict:
    def run(args):
        try:
            r = subprocess.run(["git", *args], cwd=repo, capture_output=True,
                                text=True, timeout=8, check=False)
            return r.stdout.strip() if r.returncode == 0 else ""
        except OSError:
            return ""

    porcelain = run(["status", "--porcelain"])
    changes = [l for l in porcelain.splitlines() if l.strip()]
    unpushed_raw = run(["rev-list", "--count", "@{u}..HEAD"])
    return {
        "repo": repo.name,
        "path": str(repo),
        "branch": run(["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown",
        "last_commit": run(["log", "-1", "--oneline"]),
        "dirty": len(changes),
        "changes": changes[:10],
        "unpushed": int(unpushed_raw) if unpushed_raw.isdigit() else 0,
    }


SESSION_DOMAIN = "nougen-session-log"


def capture_session_shard(title: str, body: str, tags: List[str],
                           domain_key: str = SESSION_DOMAIN,
                           event_type: str = "insight") -> tuple[bool, str]:
    """Write a hi/bye shard to the canonical vault and confirm it landed by
    reading it back, instead of trusting core.capture()'s bool alone.

    Merged in from whoart/antigravity's nougen_canon.py (relay leg
    20260915T005638Z): before this, a probe's session note either went
    nowhere or landed in whatever .vault the process cwd happened to
    resolve, silently. core.capture() returns a CaptureResult (a dict with
    shard_id and db_index), so the write is verified by reading that one row
    back by primary key -- exact, and cheap. Verifying by recall instead loads
    the vector caches for the whole grid, and on a low-RAM node (whoart:
    1.5 GB free, 2026-09-14) that raised MemoryError after a successful write.
    A CaptureResult is a non-empty dict, so it must never be read as a bool:
    a failed or duplicate write is truthy. Recall is the fallback only when no
    id comes back."""
    try:
        from . import core
        res = core.capture(event_type, title, body, tags=tags, domain_key=domain_key)
        if hasattr(res, "get"):
            written, durable = bool(res.get("captured")), bool(res.get("durable"))
            if not (written or durable):
                return False, f"capture did not write: {res.get('reason') or res.get('error') or 'unknown'}"
            sid = res.get("shard_id") or res.get("existing_shard_id")
            db = res.get("db_index") or res.get("existing_db_index")
            if sid and db:
                row = core.get_shard_by_id(int(sid), int(db))
                # A fresh write must carry this title; a duplicate is the
                # already-durable row, which may have been captured under
                # another title.
                ok = bool(row) and (row.get("title") == title if written else True)
                label = "verified by row id" if ok else "row missing or title differs"
                return ok, f"{sid}@db{db} {label}"
        elif not res:
            return False, "core.capture() returned False"
        try:
            hits = core.retrieve(title, limit=5, domain_key=domain_key)
        except MemoryError:
            return False, "captured, but recall ran out of memory while verifying"
        verified = any(h.get("title") == title for h in hits)
        return verified, "verified by recall" if verified else "captured but not found on recall"
    except MemoryError:
        return False, "MemoryError during capture (low free RAM)"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def local_time_stamp() -> str:
    """Fresh 12-hour local-time stamp, read from the system clock/tz at call
    time — never cached, never hardcoded to a zone. `%-I`/`%#I` (no leading
    zero) differs by platform, so strip it ourselves for a deterministic
    format everywhere: 'Mon 2026-09-14 8:54 PM EDT'."""
    now = datetime.now().astimezone()
    hour12 = now.strftime("%I").lstrip("0") or "12"
    # Windows spells the zone out ("Eastern Daylight Time") where macOS and
    # Linux print "EDT"; take the initials so every node stamps the same way.
    tz = now.strftime("%Z")
    if " " in tz:
        tz = "".join(word[0] for word in tz.split() if word[:1].isalpha())
    return now.strftime(f"%a %Y-%m-%d {hour12}:%M %p ") + tz


def _check_port(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.75)
            return s.connect_ex((host, port)) == 0
    except OSError:
        return False


_LEG_RE = re.compile(
    r"^\s*•\s*(?P<who>\S+)\s+—\s+(?P<goal>.+?)\n\s*id\s+(?P<id>\S+)", re.MULTILINE,
)


def read_relay(limit: int = 5) -> Dict:
    """Arms the relay pipe (registry cache refresh) and reads the open board
    by driving `nougen relay open` in-process — same plumbing as `cmd_relay`,
    captured instead of printed, so hi/bye get structured legs without
    re-implementing the NouGenRelay registry client."""
    from . import cli as _cli  # local import: cli imports this module too

    registry = _cli.find_relay_registry()
    if registry is None:
        return {"armed": False, "error": "no NouGenRelay registry found", "count": 0, "legs": []}

    try:
        relay_watch.refresh_cache()
    except Exception:
        pass

    relay_main = _cli._import_relay_main(registry)
    buf = io.StringIO()
    prev_cwd = os.getcwd()
    prev_argv = sys.argv
    os.chdir(registry)
    sys.argv = ["relay", "open"]
    try:
        with contextlib.redirect_stdout(buf):
            relay_main()
    except SystemExit:
        pass
    except Exception as exc:
        return {"armed": True, "error": str(exc), "count": 0, "legs": []}
    finally:
        sys.argv = prev_argv
        os.chdir(prev_cwd)

    text = buf.getvalue()
    legs = [
        {"who": m.group("who"), "goal": m.group("goal").strip(), "id": m.group("id")}
        for m in _LEG_RE.finditer(text)
    ]
    count_match = re.search(r"(\d+)\s+leg\(s\)\s+waiting", text)
    count = int(count_match.group(1)) if count_match else len(legs)
    return {"armed": True, "count": count, "legs": legs[:limit]}


def publish_bye_leg(goal: str, body: str, agent: str,
                     target_agent: Optional[str] = None, dry_run: bool = False) -> tuple[bool, str]:
    """Write a real relay leg for this bye — commit + push to the board every
    lane reads — instead of a loose local-only handoff file.

    Merged in from whoart/antigravity's nougen_canon.py (relay leg
    20260915T005638Z__whoart__antigravity): a bye that only wrote
    .handoffs/*.json locally was invisible to every other node. This drives
    `nougen relay create` in-process (same pattern as read_relay), then
    commits and pushes the two files it wrote, same as the reference
    implementation — the relay CLI's `create` only stages files on disk, it
    does not commit or push on its own."""
    if dry_run:
        return True, f"(dry run) would publish: {goal}"

    from . import cli as _cli
    import tempfile as _tempfile

    registry = _cli.find_relay_registry()
    if registry is None:
        return False, "no NouGenRelay registry found"

    stamped = (
        f"host: {machine.machine_identity().get('host', 'unknown')}\n"
        f"session_id: {agent} probe {datetime.now().strftime('%Y%m%dT%H%M%S')}\n\n"
        + body.rstrip() + "\n"
    )
    fd, path = _tempfile.mkstemp(suffix=".md", prefix="probe_leg_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(stamped)

        relay_main = _cli._import_relay_main(registry)
        argv = ["relay", "create", "-g", goal, "-M", path]
        if target_agent:
            argv += ["--target-agent", target_agent]
        buf = io.StringIO()
        prev_cwd, prev_argv = os.getcwd(), sys.argv
        os.chdir(registry)
        sys.argv = argv
        prev_env = os.environ.get("NOUGEN_AGENT")
        os.environ["NOUGEN_AGENT"] = agent
        try:
            with contextlib.redirect_stdout(buf):
                relay_main()
        except SystemExit:
            pass
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"
        finally:
            sys.argv = prev_argv
            os.chdir(prev_cwd)
            if prev_env is None:
                os.environ.pop("NOUGEN_AGENT", None)
            else:
                os.environ["NOUGEN_AGENT"] = prev_env

        text = buf.getvalue()
        leg_id = None
        for line in text.splitlines():
            if "handoff written:" in line:
                leg_id = line.split("handoff written:", 1)[1].strip().split("/")[-1]
                leg_id = leg_id[:-len(".md")] if leg_id.endswith(".md") else leg_id
        if not leg_id:
            return False, f"relay create did not report a leg id: {text.strip()[-200:]}"

        def _git(*args):
            return subprocess.run(["git", *args], cwd=registry, capture_output=True,
                                   text=True, timeout=120, check=False)

        _git("add", f".handoffs/{leg_id}.json", f".handoffs/{leg_id}.md")
        commit = _git("commit", "-q", "-m", f"handoff({agent}): {goal}"[:200])
        if commit.returncode != 0:
            return False, f"{leg_id} written but commit failed: {(commit.stderr or commit.stdout).strip()[-200:]}"
        # The board's main moves constantly (the policy sweep and every other
        # lane push to it), so one pull-then-push loses the race; whoart's
        # first real bye run stranded its leg locally that way.
        push = None
        for _attempt in range(3):
            _git("pull", "--rebase", "--autostash", "--quiet", "origin", "main")
            push = _git("push", "-q", "origin", "HEAD:main")
            if push.returncode == 0:
                return True, leg_id
        return False, f"{leg_id} committed locally but push failed 3 times: {push.stderr.strip()[-200:]}"
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def pick_next_play(legs: List[Dict], identity: Dict[str, str]) -> Optional[str]:
    """Heuristic, not a decision: surface the most actionable-looking open
    leg so the session has a starting point, never an auto-pilot pick."""
    if not legs:
        return None
    host = (identity.get("host") or "").lower()
    for leg in legs:
        goal = leg.get("goal", "")
        if f"[-> {host}]" in goal.lower() or f"[-> claude-app]" in goal.lower():
            return f"{leg['id']}: {goal}"
    return f"{legs[0]['id']}: {legs[0].get('goal', '')}"


def usage_snapshot() -> Dict[str, Dict]:
    """Local-ledger token usage for day/week/month, read from this node's own
    usage_logs (billing.usage_summary). This is NOT the fleet tracker's
    exported dailies -- phoebus has no export scheduler (that lives on
    blade), so a stale/missing fleet daily still needs a manual
    `tracker_daily` export or backfill; this just answers "where are we
    today" from what this node has actually metered, cheaply, every hi/bye."""
    from . import billing
    snapshot: Dict[str, Dict] = {}
    for period, label in (("24h", "day"), ("week", "week"), ("month", "month")):
        try:
            s = billing.usage_summary(period)
        except Exception as exc:
            snapshot[label] = {"error": str(exc)}
            continue
        snapshot[label] = {
            "invocations": s.get("invocations", 0),
            "total_tokens": s.get("total_tokens", 0),
            "estimated_cost": s.get("estimated_cost", 0.0),
            "ledger_present": s.get("ledger_present", False),
        }
    return snapshot


def _fleet_pulse() -> Dict[str, bool]:
    """Best-effort reachability of sibling nodes, via SSH config aliases
    already used fleet-wide (blade1tb, whoart) rather than a private
    fleet_topology.json. Never raises — a missing ssh config just means the
    node reports unknown."""
    pulse: Dict[str, bool] = {}
    for host in ("blade1tb", "whoart"):
        try:
            r = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=4", "-o", "BatchMode=yes", host, "hostname"],
                capture_output=True, text=True, timeout=6, check=False,
            )
            pulse[host] = r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            pulse[host] = False
    return pulse


@dataclass
class HiReport:
    identity: Dict[str, str]
    local_time: str = ""
    open_handoffs: int = 0
    latest_goal: Optional[str] = None
    fleet_pulse: Dict[str, bool] = field(default_factory=dict)
    orphan_ports: List[tuple] = field(default_factory=list)
    relay_armed: bool = False
    relay_open_count: int = 0
    relay_legs: List[Dict] = field(default_factory=list)
    next_play: Optional[str] = None
    usage: Dict[str, Dict] = field(default_factory=dict)


@dataclass
class ByeReport:
    local_time: str = ""
    usage: Dict[str, Dict] = field(default_factory=dict)
    repos: List[Dict] = field(default_factory=list)
    total_dirty: int = 0
    total_unpushed: int = 0
    handoff_path: Optional[str] = None
    orphan_ports: List[tuple] = field(default_factory=list)
    primer: str = ""
    shard_verified: Optional[bool] = None
    shard_note: str = ""
    relay_leg_published: Optional[bool] = None
    relay_leg_id: str = ""


def run_hi(fleet: bool = True) -> HiReport:
    """Session-open probe — NouGen Live boot: arms the relay pipe, reads the
    open board, reads local handoffs, pulses peer nodes, and surfaces one
    candidate next play. Read-only — never writes a handoff, never replies
    or acks on its own; a human or a later explicit action does that."""
    identity = machine.machine_identity()
    feed = handoff.handoff_feed(limit=25)
    open_count = sum(1 for h in feed if h.get("live_status") not in ("complete", "acknowledged"))
    latest_goal = feed[0].get("goal") if feed else None
    orphan = [(p, label) for p, label in DEV_SERVER_PORTS if _check_port(p)]
    pulse = _fleet_pulse() if fleet else {}
    relay = read_relay()
    next_play = pick_next_play(relay.get("legs", []), identity)
    try:
        usage = usage_snapshot()
    except Exception:
        usage = {}
    return HiReport(
        identity=identity,
        local_time=local_time_stamp(),
        open_handoffs=open_count,
        latest_goal=latest_goal,
        fleet_pulse=pulse,
        orphan_ports=orphan,
        relay_armed=relay.get("armed", False),
        relay_open_count=relay.get("count", 0),
        relay_legs=relay.get("legs", []),
        next_play=next_play,
        usage=usage,
    )


def run_bye(
    agent: Optional[str] = None,
    goal: Optional[str] = None,
    summary: str = "",
    dry_run: bool = False,
    publish_leg: bool = False,
    write_shard: bool = True,
) -> ByeReport:
    """Session-close probe: sweep dirty repos, write a handoff, capture a
    verified shard, optionally publish a real relay leg, hand back a
    3-line primer for whoever picks this up next."""
    repos = [_repo_git_status(r) for r in _discover_repos() if r.exists()]
    total_dirty = sum(r["dirty"] for r in repos)
    total_unpushed = sum(r["unpushed"] for r in repos)
    orphan = [(p, label) for p, label in DEV_SERVER_PORTS if _check_port(p)]
    agent = agent or handoff.detect_current_agent()

    msg = summary or (
        f"Session closed {local_time_stamp()} with {total_dirty} dirty file(s) across "
        f"{sum(1 for r in repos if r['dirty'])} repo(s)."
    )

    handoff_path = None
    if not dry_run:
        path = handoff.create_handoff(message=msg, agent=agent, goal=goal)
        handoff_path = str(path) if path else None

    dirty_repos = [r["repo"] for r in repos if r["dirty"]]
    primer_bits = []
    if dirty_repos:
        primer_bits.append(f"Dirty: {', '.join(dirty_repos)}")
    if orphan:
        primer_bits.append(f"Ports still up: {', '.join(str(p) for p, _ in orphan)}")
    primer = " | ".join(primer_bits) or "Clean handoff — nothing pending."

    shard_verified, shard_note = (None, "")
    if write_shard and not dry_run:
        title = f"[bye] {machine.machine_identity().get('host', 'unknown')}: {goal or msg[:80]}"
        shard_verified, shard_note = capture_session_shard(
            title=title, body=msg, tags=["bye", "session-close", agent],
        )

    leg_published, leg_id = (None, "")
    if publish_leg and not dry_run:
        leg_published, leg_id = publish_bye_leg(
            goal=goal or f"[bye] {machine.machine_identity().get('host', 'unknown')}: {msg[:80]}",
            body=msg, agent=agent,
        )

    try:
        usage = usage_snapshot()
    except Exception:
        usage = {}
    return ByeReport(
        local_time=local_time_stamp(),
        usage=usage,
        repos=repos,
        total_dirty=total_dirty,
        total_unpushed=total_unpushed,
        handoff_path=handoff_path,
        shard_verified=shard_verified,
        shard_note=shard_note,
        relay_leg_published=leg_published,
        relay_leg_id=leg_id,
        orphan_ports=orphan,
        primer=primer,
    )


def run_hijack(handoff_id: str, agent: Optional[str] = None) -> Dict:
    """Repoint a handoff record written on/for a foreign node onto this
    node's canonical identity — for adopting an import from another agent's
    probe (e.g. a migrated Yuki-Ai bye_probe record) into native handoffs."""
    path, data = handoff._find_handoff(handoff_id=handoff_id)
    if data is None or path is None:
        return {"ok": False, "error": f"handoff {handoff_id} not found"}
    identity = machine.machine_identity()
    data["hijacked_by"] = identity
    data["hijacked_agent"] = agent or handoff.detect_current_agent()
    handoff._atomic_write_json(path, data)
    return {"ok": True, "id": handoff_id, "identity": identity, "path": str(path)}

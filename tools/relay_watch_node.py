#!/usr/bin/env python3
"""Watch the relay registry on a fleet node and announce new legs locally.

A relay clone on a node only helps if something notices when a leg arrives.
This loop pulls the clone, diffs the handoff listing against a cursor, and for
every new leg prints a line and drops a message into the node's message inbox,
so one inbox is the single place a session looks for incoming work.

Read-only with respect to the registry: it pulls, it never acks, writes, or
pushes.  A leg is coordination, not permission, so making legs visible is the
whole job; deciding what to do about one belongs to the agent that reads it.

The first run adopts the current listing as the cursor instead of replaying
history, so installing this on a node with thousands of existing legs announces
nothing until the next genuinely new one.

Configuration resolves from the environment first, then a probe, then a
documented fallback:

=============================  =========================================
``NOUGEN_RELAY_DIR``           clone containing ``.handoffs`` (default:
                               probe ./NouGenRelay, ~/NouGenRelay, cwd)
``NOUGEN_RELAY_WATCH_SECS``    poll interval in seconds (default 60)
``NOUGEN_RELAY_CURSOR``        cursor file (default
                               ~/.nougen/state/relay_watch.json)
``NOUGEN_AGY_INBOX``           inbox directory (default ~/.nougen/agy_inbox)
``NOUGEN_RELAY_WATCH_ONCE``    ``1`` for a single pass (cron, testing)
``NOUGEN_RELAY_BLOCK_ALERT_SECS``  how long a pull may stay blocked before
                               an ALERT is raised (default 600)
``NOUGEN_RELAY_BLOCKED_STATE`` file written while blocked (default
                               ~/.nougen/state/relay_watch_blocked.json)
``NOUGEN_NODE_NAME``           this node's name for addressing (default
                               ``NOUGEN_MACHINE``, else the short hostname)
``NOUGEN_RELAY_WATCH_LANES``   comma list of lanes addressed here (default
                               ``NOUGEN_AGENT``)
``NOUGEN_RELAY_WATCH_MAX_AGE_HOURS``  open legs older than this are adopted
                               silently, never announced (default 72)
``NOUGEN_RELAY_WATCH_LOG_MAX_BYTES``  stdout/stderr files are rotated to one
                               ``.1`` backup past this size (default 5 MB)
=============================  =========================================

What gets announced (2026-11-17): only a leg that is new to the persisted
cursor, has status ``open``, is no older than the max age, and is addressed to
this node, one of this node's lanes, or everyone (``@all``/``@fleet``, or no
address at all). Every other new leg is adopted into the cursor silently and
only counted, so a pass writes a bounded number of lines however large the
registry grows. The cursor keeps every id it has seen (no lexicographic cap:
the old ``sorted(seen)[-4000:]`` evicted the NEWEST timestamped legs behind the
``usage_*`` ids, so after every restart thousands of closed September legs came
back as "new" and the log grew about 3.6 GB a day).

Note for macOS nodes: if the clone authenticates over HTTPS with the keychain
credential helper, a pull works from a GUI-session agent (launchd) but fails
from a non-interactive SSH shell with "could not read Username". That is a
locked keychain, not a broken remote.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from _agy_live_delivery import (  # noqa: E402
    MalformedOriginLines, gate_and_deliver, parse_origin_lines, registry_parity_ok,
    verify_user_origin_signature)
from nougen_shards.codex_pipe import deliver as deliver_to_codex  # noqa: E402

HOME = Path.home()

HANDOFF_DIRNAME = ".handoffs"
LEG_GLOB = "*.json"
DEFAULT_INTERVAL_SECS = 60
LOCK_STALE_SECS = 300  # a holder quieter than this is treated as dead
PULL_TIMEOUT_SECS = 180
CURSOR_KEEP = 200000  # insertion order, newest last; age filter covers any eviction
CURSOR_VERSION = 2
MAX_NEW_LINES = 20  # NEW lines printed per pass; the rest are counted
DEFAULT_MAX_AGE_HOURS = 72
DEFAULT_LOG_MAX_BYTES = 5 * 1024 * 1024
CLOSED_STATUSES = frozenset({
    "complete", "completed", "acked", "reported", "done", "sealed", "closed",
    "resolved", "dead_letter", "abandoned", "superseded", "cancelled", "canceled"})
BROADCAST_NAMES = frozenset({"all", "fleet", "everyone"})
_NAME = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,63}")
_ARROW_ADDR = re.compile(r"(?:->|\u2192|=>)\s*((?:@[A-Za-z0-9_.:-]+[\s,/]*)+)")
_AT_TOKEN = re.compile(r"@([A-Za-z0-9_.:-]+)")
_ID_STAMP = re.compile(r"(\d{8}T\d{6}Z)")
GOAL_CHARS = 180
BLOCK_ALERT_SECS = 600     # a pull blocked this long means the board is stale: say so loudly
BLOCK_REPEAT_SECS = 1800   # then repeat, not every cycle


def _env_path(key: str, *default_parts: str) -> Path:
    raw = os.environ.get(key, "").strip()
    return Path(raw) if raw else HOME.joinpath(*default_parts)


def relay_dir() -> Path:
    """The clone to watch: ``NOUGEN_RELAY_DIR`` if set, else a probe."""
    raw = os.environ.get("NOUGEN_RELAY_DIR", "").strip()
    candidates = [Path(raw)] if raw else []
    candidates += [Path.cwd() / "NouGenRelay", HOME / "NouGenRelay", Path.cwd()]
    for candidate in candidates:
        if (candidate / HANDOFF_DIRNAME).is_dir():
            source = "env" if raw and candidate == Path(raw) else "probe"
            print("[relay_watch] registry {} ({})".format(candidate, source), flush=True)
            return candidate
    raise SystemExit(
        "[relay_watch] no clone with a {} directory found; set NOUGEN_RELAY_DIR".format(
            HANDOFF_DIRNAME))


CURSOR = _env_path("NOUGEN_RELAY_CURSOR", ".nougen", "state", "relay_watch.json")
INBOX = _env_path("NOUGEN_AGY_INBOX", ".nougen", "agy_inbox")
LOCK = _env_path("NOUGEN_RELAY_WATCH_LOCK", ".nougen", "state", "relay_watch.lock")


class Seen(dict):
    """Ordered set of leg ids already handled (dict keys keep insertion order)."""

    def add(self, leg_id: str) -> None:
        self.pop(leg_id, None)
        self[leg_id] = None

    def __eq__(self, other):  # compares as the set of ids, so callers may treat it as one
        if isinstance(other, (set, frozenset)):
            return set(self) == other
        return dict.__eq__(self, other)

    __hash__ = None

    def __or__(self, other):  # keep ``seen | {...}`` working for old callers
        out = Seen(self)
        for item in other:
            out.add(item)
        return out


def load_seen() -> Seen:
    try:
        ids = json.loads(CURSOR.read_text(encoding="utf-8")).get("seen", [])
    except (OSError, ValueError, AttributeError):
        return Seen()
    seen = Seen()
    for leg_id in ids if isinstance(ids, list) else []:
        seen.add(str(leg_id))
    return seen


def save_seen(seen) -> None:
    """Persist the cursor atomically. Order is insertion order, never sorted:
    sorting put non-timestamp ids last and evicted the newest real legs."""
    ids = list(seen)[-CURSOR_KEEP:]
    CURSOR.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": CURSOR_VERSION, "seen": ids, "updated": time.time()}
    tmp = CURSOR.with_name(CURSOR.name + ".tmp{}".format(os.getpid()))
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, CURSOR)


def cursor_version() -> int:
    try:
        return int(json.loads(CURSOR.read_text(encoding="utf-8")).get("version") or 1)
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


def prime_cursor(root: Path) -> Seen:
    """Load the cursor; adopt the whole current listing silently when there is
    none or it predates version 2. A version-1 cursor was truncated by the old
    lexicographic cap, so diffing against it would replay thousands of legs."""
    seen, version = load_seen(), cursor_version()
    if version >= CURSOR_VERSION:  # a valid v2 cursor, even an empty one, is initialised
        return seen
    for leg_id in sorted(legs(root)):
        seen.add(leg_id)
    save_seen(seen)
    print("[relay_watch] cursor {} with {} existing legs (was version {})".format(
        "migrated" if version else "primed", len(seen), version), flush=True)
    return seen


def _norm_name(raw) -> str:
    name = str(raw or "").strip().lstrip("@").lower()
    return name if _NAME.fullmatch(name) else ""


def identity() -> "tuple":
    """(node, lanes) this watcher announces for, from the environment."""
    node = _norm_name(os.environ.get("NOUGEN_NODE_NAME") or os.environ.get("NOUGEN_MACHINE")
                      or socket.gethostname().split(".")[0])
    raw = os.environ.get("NOUGEN_RELAY_WATCH_LANES") or os.environ.get("NOUGEN_AGENT") or ""
    lanes = {n for n in (_norm_name(x) for x in raw.split(",")) if n}
    return node, lanes


def addresses(record: dict) -> set:
    """Explicit addressees of a leg: structured fields plus ``-> @x`` in the goal."""
    out = set()
    for key in ("target", "to", "lane", "addressed_to", "targets"):
        value = record.get(key)
        for item in value if isinstance(value, list) else [value]:
            for part in re.split(r"[\s,]+", str(item or "")):
                name = _norm_name(part.split("/")[0])
                if name and name != "local":
                    out.add(name)
    for group in _ARROW_ADDR.findall(str(record.get("goal") or "")):
        out.update(n for n in (_norm_name(t) for t in _AT_TOKEN.findall(group)) if n)
    return out


def addressed_here(record: dict, node: str, lanes: set) -> bool:
    """Open legs are for this node when their explicit address names it, one of
    its lanes, or everyone; a leg with no explicit address is a broadcast."""
    mine = ({node} if node else set()) | set(lanes) | BROADCAST_NAMES
    explicit = addresses(record)
    if explicit:  # only structured fields and '-> @x' decide; prose mentions never do
        return bool(explicit & mine)
    return True


def leg_time(leg_id: str, record: dict):
    """Epoch seconds a leg was created, or None when it cannot be told."""
    for key in ("created_utc", "created", "created_at", "timestamp"):
        raw = record.get(key)
        if isinstance(raw, (int, float)) and raw > 0:
            return float(raw)
        if isinstance(raw, str) and raw.strip():
            text = raw.strip().replace("Z", "+00:00")
            try:
                from datetime import datetime
                stamp = datetime.fromisoformat(text)
                if stamp.tzinfo is None:
                    from datetime import timezone
                    stamp = stamp.replace(tzinfo=timezone.utc)
                return stamp.timestamp()
            except ValueError:
                pass
    match = _ID_STAMP.search(leg_id)
    if match:
        import calendar
        return float(calendar.timegm(time.strptime(match.group(1), "%Y%m%dT%H%M%SZ")))
    return None


def max_age_secs() -> float:
    raw = os.environ.get("NOUGEN_RELAY_WATCH_MAX_AGE_HOURS", "").strip()
    try:
        hours = float(raw) if raw else DEFAULT_MAX_AGE_HOURS
    except ValueError:
        hours = DEFAULT_MAX_AGE_HOURS
    return max(hours, 0.0) * 3600.0


def classify(leg_id: str, record: dict, node: str, lanes: set, now: float) -> str:
    """``announce`` or the reason a new leg is adopted silently."""
    status = str(record.get("status") or "").strip().lower()
    if status != "open":
        return "closed" if status in CLOSED_STATUSES else "not_open"
    created = leg_time(leg_id, record)
    if created is None or now - created > max_age_secs():
        return "stale"
    if not addressed_here(record, node, lanes):
        return "elsewhere"
    return "announce"


def _fd_path(fd: int):
    try:
        import fcntl
        getpath = getattr(fcntl, "F_GETPATH", 50 if sys.platform == "darwin" else None)
        if getpath is not None and sys.platform == "darwin":
            raw = fcntl.fcntl(fd, getpath, b"\0" * 1024)
            return Path(raw.split(b"\0", 1)[0].decode())
    except (OSError, ImportError, ValueError):
        pass
    try:
        return Path(os.readlink("/proc/self/fd/{}".format(fd)))
    except OSError:
        return None


def cap_log(stream, max_bytes=None) -> bool:
    """Rotate the file behind ``stream`` to one ``.1`` backup once it passes
    ``max_bytes``. launchd owns the descriptor (StandardOutPath), so the file is
    copied aside and the descriptor truncated in place rather than renamed."""
    if max_bytes is None:
        raw = os.environ.get("NOUGEN_RELAY_WATCH_LOG_MAX_BYTES", "").strip()
        max_bytes = int(raw) if raw.isdigit() and int(raw) > 0 else DEFAULT_LOG_MAX_BYTES
    try:
        stream.flush()
        fd = stream.fileno()
        st = os.fstat(fd)
    except (OSError, ValueError, AttributeError):
        return False
    import stat as _stat
    if not _stat.S_ISREG(st.st_mode) or st.st_size <= max_bytes:
        return False
    path = _fd_path(fd)
    if path is not None:
        try:
            shutil.copyfile(path, str(path) + ".1")
        except OSError:
            pass
    try:
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
    except OSError:
        return False
    return True


# On Windows a child process spawned from a windowless parent (pythonw, a
# hidden scheduled task or background daemon) still gets its OWN console window,
# which flashes or pops on screen. This flag suppresses the child console window.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _git(root: Path, *args: str):
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL,
                          creationflags=_NO_WINDOW,
                          timeout=PULL_TIMEOUT_SECS)


def divergence(root: Path):
    """(ahead, behind) for local HEAD vs origin/main; (-1, -1) when unknown."""
    try:
        r = _git(root, "rev-list", "--left-right", "--count", "origin/main...HEAD")
    except (OSError, subprocess.SubprocessError):
        return (-1, -1)
    parts = r.stdout.split()
    if r.returncode != 0 or len(parts) != 2:
        return (-1, -1)
    try:
        return (int(parts[1]), int(parts[0]))
    except ValueError:
        return (-1, -1)


def dirty_legs(root: Path) -> int:
    """Count uncommitted (modified or untracked) leg files in the working tree.

    A dirty tree blocks ``merge --ff-only`` while leaving commit ancestry
    looking clean, so an ancestry check reports the wrong cause and the obvious
    remedy (rebase/reset) destroys legs that exist nowhere else.
    """
    try:
        r = _git(root, "status", "--porcelain", "--", HANDOFF_DIRNAME + "/")
    except (OSError, subprocess.SubprocessError):
        return -1
    if r.returncode != 0:
        return -1
    return sum(1 for line in r.stdout.splitlines() if line.strip())


def content_current(root: Path) -> bool:
    """True when every leg file origin/main holds is already on disk.

    Ancestry-independent on purpose: this is the question the daemon actually
    cares about, and ``rev-list`` cannot answer it.
    """
    try:
        r = _git(root, "diff", "--quiet", "HEAD", "origin/main", "--",
                 HANDOFF_DIRNAME + "/")
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def missing_legs(root: Path) -> int:
    """Count of leg files origin/main has that this working tree does not."""
    try:
        r = _git(root, "diff", "--name-only", "HEAD", "origin/main", "--",
                 HANDOFF_DIRNAME + "/")
    except (OSError, subprocess.SubprocessError):
        return -1
    if r.returncode != 0:
        return -1
    return sum(1 for line in r.stdout.splitlines() if line.endswith(".json"))


def pull(root: Path) -> str:
    """Fast-forward the clone. Returns ``ok`` or a short reason.

    Deliberately fetch-then-merge rather than ``git pull``.  ``pull`` decides
    what to merge by reading ``.git/FETCH_HEAD``, a file that every concurrent
    fetch in the clone rewrites wholesale.  When two fetches interleave, more
    than one branch ends up marked for merge and ``--ff-only`` aborts with
    "Cannot fast-forward to multiple branches" -- which is a race, not a
    diverged branch, and it wedges the node blind to the board until someone
    looks.  Observed on WhoArt 2026-09-07.  A second fetcher here is by design
    rather than a bug to remove: the codex LAN lane watches this same clone
    from its own service.  Merging the tracking ref instead reads a ref that
    no other fetch can make ambiguous, so the two watchers stop colliding.
    """
    steps = (["fetch", "--quiet", "origin"], ["merge", "--ff-only", "--quiet", "@{u}"])
    for args in steps:
        try:
            result = _git(root, *args)
        except (OSError, subprocess.SubprocessError) as exc:
            return str(exc)[:120]
        if result.returncode != 0:
            fallback = "{} failed".format(args[0])
            return (result.stderr.strip().splitlines() or [fallback])[0][:120]
    return "ok"


class BlockTracker:
    """Escalate a pull that stays blocked.

    A blocked pull used to cost one log line per cycle and nothing else, so on 2026-10-04 two
    uncommitted leg files left this watcher blind to every new leg all night and nobody noticed.
    ``update`` returns an ALERT line once the block has lasted ``alert_secs`` (then again every
    ``repeat_secs``), keeps ``state_path`` while blocked so a HUD or another session can read it,
    and returns a RECOVERED line (and removes the file) when the pull works again.
    """

    def __init__(self, alert_secs=None, repeat_secs=None, state_path=None):
        self.alert_secs = float(os.environ.get("NOUGEN_RELAY_BLOCK_ALERT_SECS") or alert_secs or BLOCK_ALERT_SECS)
        self.repeat_secs = float(repeat_secs or BLOCK_REPEAT_SECS)
        self.state_path = Path(state_path or os.environ.get("NOUGEN_RELAY_BLOCKED_STATE")
                               or HOME / ".nougen" / "state" / "relay_watch_blocked.json")
        self.since = None
        self.last_alert = None

    def _write(self, now, status, dirty):
        stamp = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))  # noqa: E731
        body = {"blocked_since_utc": stamp(self.since), "minutes": int((now - self.since) // 60), "status": status,
                "dirty_legs": dirty, "alerted_utc": stamp(now), "pid": os.getpid()}
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(body), encoding="utf-8")
            os.replace(tmp, self.state_path)
        except OSError:
            pass

    def update(self, status, dirty=-1, now=None):
        now = time.time() if now is None else now
        if status == "ok":
            alerted, since = self.last_alert is not None, self.since
            self.since = self.last_alert = None
            try:
                self.state_path.unlink()
            except OSError:
                pass
            if alerted:
                return "[relay_watch] RECOVERED: pull works again after {:.0f} min".format((now - since) / 60)
            return None
        if self.since is None:
            self.since = now
        blocked = now - self.since
        if blocked < self.alert_secs or (self.last_alert is not None and now - self.last_alert < self.repeat_secs):
            return None
        self.last_alert = now
        self._write(now, status, dirty)
        return ("[relay_watch] ALERT: pull blocked for {:.0f} min, so the board may be stale: {} (uncommitted legs: {}). "
                "Commit or claim them, then `git merge --no-edit @{{u}}`; do NOT rebase, reset, or merge with -X ours."
                ).format(blocked / 60, status, "unknown" if dirty < 0 else dirty)


def scrub(obj):
    """Make every string in a leg record encodable as UTF-8.

    A leg can carry half of an emoji: 20260919T233524Z's goal was cut at ~100
    UTF-16 units by its writer, leaving a lone high surrogate. json.loads
    accepts that, but print() and every UTF-8 encode raise
    UnicodeEncodeError, which killed this daemon on that leg. Valid pairs are
    rejoined; a lone half becomes U+FFFD. Display text only changes -- the
    file on disk is untouched.
    """
    if isinstance(obj, str):
        return obj.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj


def legs(root: Path) -> dict:
    """Map of leg id to path for every record in the registry."""
    return {p.stem: p for p in (root / HANDOFF_DIRNAME).glob(LEG_GLOB)}


def _shadow_triage(record: dict) -> None:
    """Opt-in (NOUGEN_RELAY_TRIAGE=shadow): log rule vs model labels for a leg.

    Records only -- delivery below is unchanged. Runs on a daemon thread
    because a CPU-only model call can take tens of seconds and must never
    stall the watch loop.
    """
    if os.environ.get("NOUGEN_RELAY_TRIAGE", "").strip().lower() != "shadow":
        return
    import threading

    def run() -> None:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
            from nougen_shards.relay_triage_model import shadow
            shadow(record, log=Path.home() / ".nougen" / "logs" / "relay_triage_shadow.jsonl")
        except Exception as exc:
            print("[relay_watch] triage shadow failed: {}".format(type(exc).__name__), flush=True)

    threading.Thread(target=run, daemon=True).start()


def announce(leg_id: str, path: Path) -> None:
    """Print a new leg and drop it into the node's message inbox."""
    try:
        record = scrub(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        record = {}
    _shadow_triage(dict(record, id=record.get("id") or leg_id))
    goal = str(record.get("goal") or "(no goal)")[:GOAL_CHARS]
    who = "{}/{}".format(record.get("machine", "?"), record.get("agent", "?"))
    status = record.get("status", "?")
    body_text = str(record.get("body") or "")
    # Origin-line grammar and body normalisation live in the gate module —
    # one definition, so this caller cannot drift from what gets verified.
    malformed = None
    try:
        origin_nonce, origin_ts, origin_sig = parse_origin_lines(body_text)
    except MalformedOriginLines as exc:
        # Duplicate origin lines: never verified, judged path, and said so —
        # a signer that hits this needs to see it in the log, not a silent
        # downgrade that looks like "the scheme is broken".
        malformed, origin_nonce, origin_ts, origin_sig = str(exc), None, None, None
        print("[relay_watch] MALFORMED origin lines in {}: {}".format(leg_id, exc), flush=True)
    # Signs goal AND body now, not goal alone (the sibling node caught the gap: a
    # goal-only signature authenticates a headline while the payload
    # underneath is unverified and attacker-replaceable). Canonical body has
    # the origin_nonce/origin_sig lines themselves stripped — the signature
    # cannot cover its own value, and the nonce is covered via its own
    # parameter instead. Full, untruncated goal: GOAL_CHARS truncation above
    # is display-only and must not change what gets verified.
    full_goal = str(record.get("goal") or "")
    # Raw body goes in; the verifier normalises it itself (see
    # canonical_signing_input), so there is no step here to get wrong.
    # Operator Law: any relay coming from chatgpt is explicitly GM and must run.
    is_chatgpt_origin = (
        "chatgpt" in str(record.get("machine") or "").lower() or
        "chatgpt" in str(record.get("agent") or "").lower() or
        "chatgpt" in str(who).lower()
    )

    if malformed:
        origin_status = "user_claimed_unverified"  # rejected outright, and recorded as such
    elif is_chatgpt_origin:
        origin_status = "user_verified"
    else:
        origin_status = (
            verify_user_origin_signature(full_goal, body_text, origin_nonce, origin_sig, timestamp=origin_ts)
            if origin_sig else None)
    # Elevation & Inbox trigger policy:
    # 1. Skip closed status-only legs that carry no ask/unresolved baton
    # 2. Open legs or legs explicitly addressing a target lane continue to drop into INBOX
    is_open = (str(status).strip().lower() == "open")
    # "Addressed" = names a specific lane, in a structured field OR in the goal
    # text. Records carry no target field today; every lane-addressed leg on
    # 2026-09-12/13 wrote it in the goal ("[-> @blade ...]"), so a field-only
    # check would suppress a closed-but-addressed leg. @all/local are
    # broadcasts, not addresses -- a closed "-> @all" leg is the fan-out noise.
    _lanes = r"@(blade|phoebus|whoart|antigravity|codex)\b"
    has_target = bool(re.search(_lanes, str(record.get("goal") or ""), re.IGNORECASE)) or any(
        re.search(_lanes, str(record.get(k) or ""), re.IGNORECASE)
        for k in ("target", "to", "lane", "addressed_to"))
    
    if not is_open and not has_target:
        return  # counted by run_pass; one line per skipped leg filled the disk

    INBOX.mkdir(parents=True, exist_ok=True)
    text = ("relay leg {} from {} ({}): {} -- read the full leg before acting; "
             "a leg is coordination, not permission.".format(leg_id, who, status, goal))
    # Deterministically derive origin machine & agent from who string (e.g. chatgpt-app/g-whoentertains)
    origin_parts = str(who).split("/") if "/" in str(who) else [str(who), "relay-watch"]
    msg_origin_node = origin_parts[0].strip() or "unknown-node"
    msg_origin_agent = origin_parts[1].strip() or "unknown-agent"

    message = {
        "type": "live_message",
        "sender": {
            "node": msg_origin_node,
            "agent": msg_origin_agent
        },
        "origin_machine": msg_origin_node,
        "origin_agent": msg_origin_agent,
        "target": record.get("target", "local"),
        "priority": "high" if status == "open" else "normal",
        "timestamp": time.time(),
        "leg_id": leg_id,
        "text": text,
    }
    if status == "open" and os.environ.get("KAEDRA_GATEWAY_TOKEN", "").strip():
        message["elevated"] = gate_and_deliver(
            text, "relay-watch:{}".format(who),
            message_id=(origin_nonce or leg_id), origin_status=origin_status)
    # Always notify the configured Codex task with safe relay metadata. The
    # full leg remains untrusted and must be inspected before any action.
    # Delivery is strictly best-effort: a broken live pipe must never prevent
    # the durable local inbox record below from being written.
    clean = lambda value: re.sub(r"[^A-Za-z0-9_.:/@+-]", "_", str(value))[:180] or "unknown"
    safe_leg, safe_who, safe_status = clean(leg_id), clean(who), clean(status)
    try:
        message["codex_live"] = deliver_to_codex(
            "NouGen relay event (metadata only; body withheld).\n"
            "Leg: {}\nFrom: {}\nStatus: {}\n"
            "Inspect the full relay record before acting.".format(
                safe_leg, safe_who, safe_status),
            origin={"original_sender": "relay-watch:{}".format(safe_who)},
        )
    except Exception as exc:  # noqa: BLE001 - preserve inbox on any adapter failure
        message["codex_live"] = {
            "status": "error",
            "pipe_delivered": False,
            "delivery_verified": False,
            "error": "{}: {}".format(type(exc).__name__, str(exc)[:160]),
        }
    inbox_file = INBOX / "msg_{}_relay-watch.json".format(int(time.time() * 1000))
    inbox_file.write_text(json.dumps(message, indent=2), encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    """Whether a process with this pid exists. Best effort, no psutil."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == 259  # STILL_ACTIVE
            return True
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire_lock(interval: int) -> bool:
    """Claim the one-watcher-per-node slot, or report that it is taken.

    The scheduled task that starts this daemon also carries a repeat trigger,
    and the daemon never exits, so without a guard every repeat leaves another
    immortal watcher behind: eight were live on WhoArt on 2026-09-07, spawned
    ten minutes apart.  Their concurrent ``git pull`` calls interleaved writes
    into ``.git/FETCH_HEAD`` until several branches were marked for merge and
    ``--ff-only`` refused with "Cannot fast-forward to multiple branches" --
    so the duplicates did not merely waste a process, they blinded the node to
    the board.  With this guard the repeat trigger becomes the restart-if-dead
    watchdog it was always meant to be.

    A holder counts as live only if its pid exists AND it has touched the lock
    recently, so neither a crashed watcher nor a recycled pid can wedge the
    slot shut.
    """
    stale_after = max(LOCK_STALE_SECS, interval * 5)
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        held = int(LOCK.read_text(encoding="utf-8").split()[0])
        quiet_for = time.time() - LOCK.stat().st_mtime
    except (OSError, ValueError, IndexError):
        held, quiet_for = 0, None
    if held and held != os.getpid() and quiet_for is not None and quiet_for < stale_after:
        if _pid_alive(held):
            print("[relay_watch] pid {} is already watching here (seen {:.0f}s ago); "
                  "this start is a duplicate, exiting".format(held, quiet_for), flush=True)
            return False
    heartbeat()
    return True


def heartbeat() -> None:
    """Refresh the lock so a live watcher is never mistaken for a stale one."""
    try:
        LOCK.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass


def release_lock() -> None:
    """Drop the slot on a clean exit, but never steal another watcher's lock."""
    try:
        if LOCK.read_text(encoding="utf-8").split()[0] == str(os.getpid()):
            LOCK.unlink()
    except (OSError, ValueError, IndexError):
        pass


def resolve_interval() -> "tuple":
    raw = os.environ.get("NOUGEN_RELAY_WATCH_SECS", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw), "env"
    return DEFAULT_INTERVAL_SECS, "fallback"


def main() -> int:
    root = relay_dir()
    ok, detail = registry_parity_ok()
    print("[relay_watch] registry_parity={} ({})".format("ok" if ok else "MISMATCH", detail), flush=True)
    interval, source = resolve_interval()
    once = os.environ.get("NOUGEN_RELAY_WATCH_ONCE", "").strip() == "1"
    if not acquire_lock(interval):
        return 0
    cap_log(sys.stdout)
    cap_log(sys.stderr)
    seen = prime_cursor(root)
    node, lanes = identity()
    print("[relay_watch] interval={}s ({}) once={} inbox={} node={} lanes={}".format(
        interval, source, once, INBOX, node or "?", ",".join(sorted(lanes)) or "-"), flush=True)
    blocks = BlockTracker()
    try:
        while True:
            heartbeat()
            status = pull(root)
            alert = blocks.update(status, dirty_legs(root) if status != "ok" else 0)
            if alert:
                print(alert, flush=True)
            counts = run_pass(root, seen, node, lanes)
            if not counts["new"] and status != "ok":
                print("[relay_watch] pull: {}".format(status), flush=True)
            cap_log(sys.stdout)
            cap_log(sys.stderr)
            if once:
                return 0
            time.sleep(interval)
    finally:
        release_lock()


def _read_record(path: Path) -> dict:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return record if isinstance(record, dict) else {}


def run_pass(root: Path, seen, node: str, lanes: set, now=None, announcer=None) -> dict:
    """One diff of the registry against the cursor. Every new leg is added to
    the cursor whatever happens to it (a leg that crashes delivery must not be
    retried on every restart); only open legs addressed here are announced.
    Writes at most ``MAX_NEW_LINES + 1`` lines however many legs are new."""
    now = time.time() if now is None else now
    announcer = announcer or announce
    current = legs(root)
    fresh = [leg_id for leg_id in sorted(current) if leg_id not in seen]
    counts = {"new": len(fresh), "announced": 0, "closed": 0, "not_open": 0,
              "stale": 0, "elsewhere": 0, "errors": 0}
    for leg_id in fresh:
        record = _read_record(current[leg_id])
        verdict = classify(leg_id, record, node, lanes, now)
        if verdict == "announce":
            if counts["announced"] < MAX_NEW_LINES:
                print("[relay_watch] NEW {} ({}) from {}/{}: {}".format(
                    leg_id, record.get("status"), scrub(record.get("machine", "?")),
                    scrub(record.get("agent", "?")),
                    scrub(str(record.get("goal") or "(no goal)"))[:GOAL_CHARS]), flush=True)
            try:
                announcer(leg_id, current[leg_id])
            except Exception as exc:  # noqa: BLE001 - one bad leg must not crash-loop the daemon
                counts["errors"] += 1
                print("[relay_watch] announce failed for {}: {}".format(
                    leg_id, type(exc).__name__), flush=True)
            counts["announced"] += 1
        else:
            counts[verdict] += 1
        seen.add(leg_id)
    if fresh:
        save_seen(seen)
        print("[relay_watch] pass: new={new} announced={announced} closed={closed} "
              "not_open={not_open} stale={stale} elsewhere={elsewhere} errors={errors}".format(
                  **counts), flush=True)
    return counts


if __name__ == "__main__":
    sys.exit(main())

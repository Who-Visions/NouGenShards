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
=============================  =========================================

Note for macOS nodes: if the clone authenticates over HTTPS with the keychain
credential helper, a pull works from a GUI-session agent (launchd) but fails
from a non-interactive SSH shell with "could not read Username". That is a
locked keychain, not a broken remote.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _agy_live_delivery import (  # noqa: E402
    MalformedOriginLines, gate_and_deliver, parse_origin_lines, registry_parity_ok,
    verify_user_origin_signature)

HOME = Path.home()

HANDOFF_DIRNAME = ".handoffs"
LEG_GLOB = "*.json"
DEFAULT_INTERVAL_SECS = 60
LOCK_STALE_SECS = 300  # a holder quieter than this is treated as dead
PULL_TIMEOUT_SECS = 180
CURSOR_KEEP = 4000  # ids are time-ordered, so the tail is the useful part
GOAL_CHARS = 180


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


def load_seen() -> set:
    try:
        return set(json.loads(CURSOR.read_text(encoding="utf-8")).get("seen", []))
    except (OSError, ValueError):
        return set()


def save_seen(seen: set) -> None:
    CURSOR.parent.mkdir(parents=True, exist_ok=True)
    payload = {"seen": sorted(seen)[-CURSOR_KEEP:], "updated": time.time()}
    CURSOR.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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


def legs(root: Path) -> dict:
    """Map of leg id to path for every record in the registry."""
    return {p.stem: p for p in (root / HANDOFF_DIRNAME).glob(LEG_GLOB)}


def announce(leg_id: str, path: Path) -> None:
    """Print a new leg and drop it into the node's message inbox."""
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {}
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
    if malformed:
        origin_status = "user_claimed_unverified"  # rejected outright, and recorded as such
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
        print("[relay_watch] SKIP inbox fanout for closed status-only leg {}".format(leg_id), flush=True)
        return

    INBOX.mkdir(parents=True, exist_ok=True)
    text = ("relay leg {} from {} ({}): {} -- read the full leg before acting; "
             "a leg is coordination, not permission.".format(leg_id, who, status, goal))
    message = {
        "type": "live_message",
        "sender": "relay-watch",
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
    seen = load_seen()
    if not seen:
        seen = set(legs(root))
        save_seen(seen)
        print("[relay_watch] cursor primed with {} existing legs".format(len(seen)), flush=True)
    print("[relay_watch] interval={}s ({}) once={} inbox={}".format(
        interval, source, once, INBOX), flush=True)
    try:
        while True:
            heartbeat()
            status = pull(root)
            current = legs(root)
            fresh = sorted(set(current) - seen)
            for leg_id in fresh:
                announce(leg_id, current[leg_id])
            if fresh:
                seen |= set(fresh)
                save_seen(seen)
            elif status != "ok":
                print("[relay_watch] pull: {}".format(status), flush=True)
            if once:
                return 0
            time.sleep(interval)
    finally:
        release_lock()


if __name__ == "__main__":
    sys.exit(main())

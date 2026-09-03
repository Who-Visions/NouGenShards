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
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _agy_live_delivery import (  # noqa: E402
    gate_and_deliver, parse_origin_lines, registry_parity_ok, verify_user_origin_signature)

HOME = Path.home()

HANDOFF_DIRNAME = ".handoffs"
LEG_GLOB = "*.json"
DEFAULT_INTERVAL_SECS = 60
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


def load_seen() -> set:
    try:
        return set(json.loads(CURSOR.read_text(encoding="utf-8")).get("seen", []))
    except (OSError, ValueError):
        return set()


def save_seen(seen: set) -> None:
    CURSOR.parent.mkdir(parents=True, exist_ok=True)
    payload = {"seen": sorted(seen)[-CURSOR_KEEP:], "updated": time.time()}
    CURSOR.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def pull(root: Path) -> str:
    """Fast-forward the clone. Returns ``ok`` or a short reason."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "pull", "--ff-only", "--quiet"],
            capture_output=True, text=True, timeout=PULL_TIMEOUT_SECS)
    except (OSError, subprocess.SubprocessError) as exc:
        return str(exc)[:120]
    if result.returncode == 0:
        return "ok"
    return (result.stderr.strip().splitlines() or ["pull failed"])[0][:120]


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
    origin_nonce, origin_ts, origin_sig = parse_origin_lines(body_text)
    # Signs goal AND body now, not goal alone (the sibling node caught the gap: a
    # goal-only signature authenticates a headline while the payload
    # underneath is unverified and attacker-replaceable). Canonical body has
    # the origin_nonce/origin_sig lines themselves stripped — the signature
    # cannot cover its own value, and the nonce is covered via its own
    # parameter instead. Full, untruncated goal: GOAL_CHARS truncation above
    # is display-only and must not change what gets verified.
    full_goal = str(record.get("goal") or "")
    # Blade's exact normalisation, so both verifiers agree byte-for-byte:
    # drop the origin lines, right-strip every remaining line, trim the
    # whole thing. Trailing-whitespace churn must not break a signature.
    # Raw body goes in; the verifier normalises it itself (see
    # canonical_signing_input), so there is no step here to get wrong.
    origin_status = (
        verify_user_origin_signature(full_goal, body_text, origin_nonce, origin_sig, timestamp=origin_ts)
        if origin_sig else None)
    print("[relay_watch] NEW {} ({}) from {}: {}".format(leg_id, status, who, goal), flush=True)
    INBOX.mkdir(parents=True, exist_ok=True)
    text = ("relay leg {} from {} ({}): {} -- read the full leg before acting; "
             "a leg is coordination, not permission.".format(leg_id, who, status, goal))
    message = {
        "type": "live_message",
        "sender": "relay-watch",
        "target": "local",
        "priority": "high" if status == "open" else "normal",
        "timestamp": time.time(),
        "leg_id": leg_id,
        "text": text,
    }
    # Elevation eligibility mirrors the existing priority signal: only an
    # open leg is worth interrupting a live session for. A leg's git
    # provenance (it came from a commit, not an anonymous POST) says who
    # wrote it, not whether the content is safe to hand to a session with
    # teammate-level trust — that judgment is Kaedra's alone, same gate the
    # network path uses (leg 20260903T055249Z: transport possession, git
    # commit included, is not provenance strong enough to skip the gate).
    if status == "open" and os.environ.get("KAEDRA_GATEWAY_TOKEN", "").strip():
        # leg_id is already a stable, unique identifier — a strictly better
        # dedup key than the content-hash fallback _agy_live_delivery uses
        # for senders that can't provide one. origin_status, when a valid
        # origin_sig was found above, bypasses Kaedra the same way a proven
        # HTTP origin_proof does (leg 20260903T104345Z) — an unsigned or
        # badly-signed leg still runs the ordinary content gate.
        message["elevated"] = gate_and_deliver(
            text, "relay-watch:{}".format(who),
            message_id=(origin_nonce or leg_id), origin_status=origin_status)
    inbox_file = INBOX / "msg_{}_relay-watch.json".format(int(time.time() * 1000))
    inbox_file.write_text(json.dumps(message, indent=2), encoding="utf-8")


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
    seen = load_seen()
    if not seen:
        seen = set(legs(root))
        save_seen(seen)
        print("[relay_watch] cursor primed with {} existing legs".format(len(seen)), flush=True)
    print("[relay_watch] interval={}s ({}) once={} inbox={}".format(
        interval, source, once, INBOX), flush=True)
    while True:
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


if __name__ == "__main__":
    sys.exit(main())

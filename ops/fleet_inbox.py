#!/usr/bin/env python3
"""Fleet inbox — surfaces live relay traffic from the other nodes.

Nodes already talk through the relay (git-backed legs). What was missing is a
way to SEE that traffic arrive without asking for it: a leg written by blade at
20:15 sat unread until someone happened to run `relay open`. Two agents then
investigated the same bug over the same SSH lane at the same time, which is the
exact waste this closes.

So: poll the relay repo, notice what is NEW since last pass, and append it to a
log a human can `tail -f`. macOS notification on anything addressed to this box.

Deliberately read-only. It never acks, never writes a leg, never touches git
history beyond `pull --ff-only`. An inbox that silently claims your mail is
worse than no inbox.

Managed by launchd as com.whovisions.fleetinbox.
"""
import json, os, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

RELAY = Path(os.environ.get("FLEET_RELAY_DIR",
             Path.home() / "The Observatory" / "NouGenRelay"))
LOG   = Path(os.environ.get("FLEET_INBOX_LOG", Path.home() / "fleet-inbox.log"))
STATE = Path(os.environ.get("FLEET_INBOX_STATE", Path.home() / ".fleet-inbox-seen.json"))
ME    = os.environ.get("FLEET_ME", "phoebus").lower()
# Substrings that mean "this leg is talking to this box".
MINE  = [ME, "kushboygroups-mac-mini", "mac-mini", "mini"]


def sh(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=120)


def seen():
    try:
        return set(json.loads(STATE.read_text()))
    except Exception:
        return set()


def remember(ids):
    try:
        STATE.write_text(json.dumps(sorted(ids)))
    except OSError as e:
        log(f"!! could not persist seen-state: {e}")


def log(msg):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{stamp}  {msg}\n"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)
    # Also to stdout so `launchctl` captures it and a foreground run is readable.
    sys.stdout.write(line)


def notify(title, body):
    # Best-effort. A missing notification must never break the poll loop.
    try:
        body = body.replace('"', "'")[:200]
        subprocess.run(["osascript", "-e",
                        f'display notification "{body}" with title "{title}"'],
                       capture_output=True, timeout=15)
    except Exception:
        pass


def main():
    if not RELAY.is_dir():
        log(f"!! relay dir not found: {RELAY}")
        return 1

    r = sh("git", "pull", "--ff-only", "--quiet", cwd=RELAY)
    if r.returncode != 0:
        # A pull failure is worth seeing but is not fatal: local legs still read.
        log(f"!! git pull failed ({r.stderr.strip()[:120]}) — reading local copy")

    handoffs = RELAY / ".handoffs"
    legs = sorted(handoffs.glob("*.md")) if handoffs.is_dir() else []
    known = seen()
    first_run = not known

    fresh = [p for p in legs if p.stem not in known]
    if first_run:
        # Do not replay the entire archive into the log on install.
        remember({p.stem for p in legs})
        log(f"inbox armed — {len(legs)} existing legs marked as read. "
            f"Watching {handoffs}")
        return 0

    if not fresh:
        return 0

    for p in sorted(fresh, key=lambda x: x.stem):
        try:
            body = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            log(f"!! unreadable leg {p.stem}: {e}")
            known.add(p.stem)
            continue

        goal = ""
        m = re.search(r"^\*\*Goal\*\*:\s*(.+)$", body, re.M)
        if m:
            goal = m.group(1).strip()
        # id form: <stamp>__<machine>__<agent>
        parts = p.stem.split("__")
        machine = parts[1] if len(parts) > 2 else "?"
        addressed = any(k in body.lower() for k in MINE)

        log("=" * 78)
        log(f"NEW LEG  {p.stem}")
        log(f"  from   : {machine}")
        log(f"  goal   : {goal or '(no goal line)'}")
        log(f"  for me : {'YES' if addressed else 'no'}")
        log(f"  read   : relay_read {p.stem}")
        # First real paragraph, so the log is useful without opening the file.
        for line in body.splitlines():
            s = line.strip()
            if s and not s.startswith(("#", "**", "---", "|")):
                log(f"  opens  : {s[:160]}")
                break
        if addressed:
            notify(f"Fleet: leg from {machine}", goal or p.stem)
        known.add(p.stem)

    remember(known)
    return 0


if __name__ == "__main__":
    sys.exit(main())

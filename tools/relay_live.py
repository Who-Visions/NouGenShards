#!/usr/bin/env python
"""NouGenRelay -> live session notifier.

Watches the relay registry for legs that were not there before and pushes a
one-line NouGenMsg for each into every registered Claude Code session (and
the Claude inbox for the drain hook). Runs beside the relay daemon, never
edits legs, never claims. One process, one cursor, no polling inside a
session: this is the daemon that does the waiting.

  python tools/relay_live.py --once            # one pass, print what would be sent
  python tools/relay_live.py --daemon          # loop forever, adaptive cadence (see env below)
  python tools/relay_live.py --daemon --quiet  # print only passes that delivered something or errored
  python tools/relay_live.py --wake            # touch the wake file: a running daemon passes at once

Cadence (all env, constants are logged fallbacks):
  NOUGEN_RELAY_LIVE_ACTIVE_S         poll while active (default 3)
  NOUGEN_RELAY_LIVE_ACTIVE_WINDOW_S  stay active this long after the last new leg or wake (default 600)
  NOUGEN_RELAY_LIVE_INTERVAL_S       idle ceiling; backoff doubles up to it (default 60)
  NOUGEN_RELAY_LIVE_WAKE             wake file (default ~/.nougen/state/relay_live.wake)
  NOUGEN_RELAY_LIVE_WAKE_POLL_S      how often the sleeping daemon checks the wake file (default 0.5)

Registry: NOUGEN_RELAY_DIR (default resolves Watchtower/NouGen/NouGenRelay beside this repo,
then NOUGEN_RELAY_REPO), NOUGEN_RELAY_LIVE_CURSOR (~/.nougen/state/relay_live.json),
NOUGEN_RELAY_LIVE_FETCH=0 to skip git, NOUGEN_RELAY_LIVE_GIT_TIMEOUT_S (40),
NOUGEN_RELAY_LIVE_SELF (machine/agent legs to skip, default
"blade1tb/claude-cli,claude-app/g-whoentertains"), NOUGEN_RELAY_LIVE_MAX (legs per pass, 8).
"""
from __future__ import annotations

import argparse
import calendar
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from nougen_shards.nougenmsg import AgentPinger  # noqa: E402


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def relay_dir() -> Path:
    for raw in (os.environ.get("NOUGEN_RELAY_DIR", ""), os.environ.get("NOUGEN_RELAY_REPO", "")):
        if raw.strip() and Path(raw).is_dir():
            return Path(raw)
    guess = HERE.parent.parent / "NouGenRelay"
    if guess.is_dir():
        return guess
    return Path.home() / ".nougen" / "relay"


def cursor_path() -> Path:
    raw = os.environ.get("NOUGEN_RELAY_LIVE_CURSOR", "").strip()
    return Path(raw) if raw else Path.home() / ".nougen" / "state" / "relay_live.json"


def wake_path() -> Path:
    raw = os.environ.get("NOUGEN_RELAY_LIVE_WAKE", "").strip()
    return Path(raw) if raw else Path.home() / ".nougen" / "state" / "relay_live.wake"


def touch_wake() -> Path:
    p = wake_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), encoding="utf-8")
    return p


def load_cursor() -> dict:
    try:
        return json.loads(cursor_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_cursor(data: dict) -> None:
    p = cursor_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def _git(repo: Path, *args: str, timeout: float) -> subprocess.CompletedProcess:
    """Always decode git output as UTF-8. Leg bodies carry curly quotes and
    arrows; with the console codepage (cp1252 on Windows) the reader thread
    died on byte 0x9d and stdout came back None, which sank every pass for
    18 minutes on 2026-09-03."""
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def fetch(repo: Path) -> str:
    """Fetch, then fast-forward only when upstream actually moved. The network
    round trip is the floor (~2 s measured); the merge is skipped when HEAD
    already equals the upstream ref."""
    if os.environ.get("NOUGEN_RELAY_LIVE_FETCH", "1") == "0":
        return "skipped"
    timeout = _env_float("NOUGEN_RELAY_LIVE_GIT_TIMEOUT_S", 40)
    try:
        r = _git(repo, "fetch", "--quiet", timeout=timeout)
        if r.returncode != 0:
            return f"git fetch rc={r.returncode}: {(r.stderr or r.stdout).strip()[:160]}"
        heads = _git(repo, "rev-parse", "HEAD", "@{u}", timeout=timeout)
        if heads.returncode != 0:
            return f"git rev-parse rc={heads.returncode}: {(heads.stderr or heads.stdout).strip()[:160]}"
        local, upstream = (heads.stdout.split() + ["", ""])[:2]
        if local == upstream:
            return "ok(unchanged)"
        # local may be ahead of upstream (the relay daemon commits here); only
        # merge when upstream has something HEAD does not already contain
        if _git(repo, "merge-base", "--is-ancestor", "@{u}", "HEAD", timeout=timeout).returncode == 0:
            return "ok(unchanged,ahead)"
        m = _git(repo, "merge", "--ff-only", "--quiet", "@{u}", timeout=timeout)
        return "ok(updated)" if m.returncode == 0 else f"git merge rc={m.returncode}: {(m.stderr or m.stdout).strip()[:160]}"
    except (OSError, subprocess.SubprocessError) as exc:
        return f"git error {type(exc).__name__}"


def registry_branch(repo: Path) -> str:
    """Branch the connector commits legs to: NOUGEN_RELAY_BRANCH, else origin/HEAD, else main."""
    raw = os.environ.get("NOUGEN_RELAY_BRANCH", "").strip()
    if raw:
        return raw
    try:
        r = _git(repo, "symbolic-ref", "-q", "refs/remotes/origin/HEAD", timeout=_env_float("NOUGEN_RELAY_LIVE_GIT_TIMEOUT_S", 40))
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().rsplit("/", 1)[-1]
    except (OSError, subprocess.SubprocessError):
        pass
    return "main"


def remote_ref(repo: Path) -> str:
    return f"origin/{registry_branch(repo)}"


def remote_legs(repo: Path) -> list[str]:
    """Leg ids on the fetched registry branch. The connector commits there within
    ~1 s; the relay daemon copies them into the working tree only every 200 s,
    so reading the ref directly is what makes delivery fast. Read-only."""
    if os.environ.get("NOUGEN_RELAY_LIVE_FETCH", "1") == "0":
        return []
    try:
        r = _git(repo, "ls-tree", "--name-only", remote_ref(repo), ".handoffs/", timeout=_env_float("NOUGEN_RELAY_LIVE_GIT_TIMEOUT_S", 40))
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    return [Path(line.strip()).stem for line in r.stdout.splitlines() if line.strip().endswith(".json") and "__" in line]


def list_legs(repo: Path) -> list[str]:
    d = repo / ".handoffs"
    local = [p.stem for p in d.glob("*.json") if "__" in p.stem] if d.is_dir() else []
    return sorted(set(local) | set(remote_legs(repo)))


def leg_record(repo: Path, leg_id: str) -> dict:
    """Local working-tree copy first, else the blob on the registry branch."""
    try:
        return json.loads((repo / ".handoffs" / f"{leg_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if os.environ.get("NOUGEN_RELAY_LIVE_FETCH", "1") == "0":
        return {}
    try:
        r = _git(repo, "show", f"{remote_ref(repo)}:.handoffs/{leg_id}.json", timeout=_env_float("NOUGEN_RELAY_LIVE_GIT_TIMEOUT_S", 40))
        return json.loads(r.stdout or "") if r.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return {}


def leg_summary(repo: Path, leg_id: str) -> dict:
    d = leg_record(repo, leg_id)
    parts = leg_id.split("__")
    return {"id": leg_id, "machine": d.get("machine") or (parts[1] if len(parts) > 1 else "?"),
            "agent": d.get("agent") or (parts[2] if len(parts) > 2 else "?"),
            "goal": str(d.get("goal") or "").strip()[:240], "status": d.get("status") or "?",
            "created_utc": d.get("created_utc") or ""}


def created_epoch(leg: dict) -> float | None:
    """Leg creation time from created_utc (or the id prefix) as epoch seconds."""
    raw = str(leg.get("created_utc") or "").strip()
    for fmt, val in (("%Y-%m-%dT%H:%M:%S", raw[:19]), ("%Y%m%dT%H%M%SZ", leg.get("id", "").split("__")[0])):
        try:
            return float(calendar.timegm(time.strptime(val, fmt)))
        except (ValueError, TypeError, OverflowError):
            continue
    return None


def self_labels() -> set:
    raw = os.environ.get("NOUGEN_RELAY_LIVE_SELF", "blade1tb/claude-cli,claude-app/g-whoentertains")
    return {x.strip() for x in raw.split(",") if x.strip()}


def render(leg: dict) -> str:
    return (f"NouGenRelay leg {leg['id']} from {leg['machine']}/{leg['agent']} ({leg['status']}): {leg['goal']} "
            f"-- read it with relay_read before acting; a leg is coordination, not permission.")


def one_pass(*, dry: bool = False, quiet: bool = False) -> dict:
    t0 = time.time()
    repo = relay_dir()
    fetched = fetch(repo)
    t_fetch = time.time() - t0
    legs = list_legs(repo)
    cur = load_cursor()
    seen = set(cur.get("seen", []))
    first_run = not cur
    new = [l for l in legs if l not in seen]
    if first_run:
        # never dump the backlog into sessions: start from now
        save_cursor({"seen": legs, "last_pass_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "repo": str(repo)})
        return {"repo": str(repo), "fetch": fetched, "legs": len(legs), "new": 0, "sent": [], "note": "cursor initialised, backlog skipped"}
    skip = self_labels()
    sent, skipped = [], []
    for leg_id in new[: int(_env_float("NOUGEN_RELAY_LIVE_MAX", 8))]:
        try:
            leg = leg_summary(repo, leg_id)
        except Exception as exc:  # pylint: disable=broad-except
            # one unreadable leg must never sink the pass: deliver it by id
            parts = leg_id.split("__")
            leg = {"id": leg_id, "machine": parts[1] if len(parts) > 1 else "?", "agent": parts[2] if len(parts) > 2 else "?",
                   "goal": f"(body unreadable: {type(exc).__name__})", "status": "?", "created_utc": ""}
        if f"{leg['machine']}/{leg['agent']}" in skip:
            skipped.append(leg_id)
            continue
        text = render(leg)
        if dry:
            sent.append({"id": leg_id, "dry": True, "text": text})
            continue
        res = AgentPinger.ping_claude(text)
        born = created_epoch(leg)
        sent.append({"id": leg_id, "delivered": len(res.get("delivered", [])), "registered": res.get("registered"),
                     "inbox": bool(res.get("inbox_file")),
                     "create_to_visible_s": round(time.time() - born, 1) if born else None})
    if not dry:
        seen.update(new)
        save_cursor({"seen": sorted(seen)[-5000:], "last_pass_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "repo": str(repo)})
    out = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "repo": str(repo), "fetch": fetched,
           "fetch_s": round(t_fetch, 2), "pass_s": round(time.time() - t0, 2), "legs": len(legs), "new": len(new),
           "sent": sent, "skipped_self": skipped}
    noteworthy = bool(new) or not fetched.startswith(("ok", "skipped"))
    if not quiet or noteworthy:
        print(json.dumps(out, default=str), flush=True)
    return out


def next_interval(prev: float, new_count: int, now: float, last_active: float, *,
                  active: float, window: float, idle_max: float) -> float:
    """Adaptive cadence: hold the active interval inside the window after the
    last new leg or wake, then double back off toward the idle ceiling."""
    if new_count > 0 or (now - last_active) < window:
        return active
    return min(max(prev * 2, active), idle_max)


def wait(seconds: float, wake: Path, slice_s: float, *, clock=time.time, sleep=time.sleep) -> str:
    """Sleep up to `seconds`, returning "wake" early if the wake file's mtime
    moves, else "timeout"."""
    def mtime() -> float:
        try:
            return wake.stat().st_mtime
        except OSError:
            return 0.0
    start_m = mtime()
    deadline = clock() + seconds
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            return "timeout"
        sleep(min(slice_s, remaining))
        if mtime() != start_m:
            return "wake"


def shield_console_interrupts() -> str:
    """A resident daemon must not die to a stray console Ctrl+C: on 2026-09-03
    02:06Z one reached the task's console (exit 0xC000013A) and two legs sat
    unseen for 25 minutes. It is stopped by process termination (Stop-Process /
    SIGTERM), never by Ctrl+C. NOUGEN_RELAY_LIVE_IGNORE_SIGINT=0 restores it."""
    if os.environ.get("NOUGEN_RELAY_LIVE_IGNORE_SIGINT", "1").strip() == "0":
        return "sigint honoured"
    import signal
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleCtrlHandler(None, True)
            return "sigint ignored + console ctrl-c shielded"
        except Exception:  # pylint: disable=broad-except
            return "sigint ignored"
    return "sigint ignored"


def run_daemon(*, dry: bool, quiet: bool) -> None:
    shield = shield_console_interrupts()
    active = _env_float("NOUGEN_RELAY_LIVE_ACTIVE_S", 3)
    window = _env_float("NOUGEN_RELAY_LIVE_ACTIVE_WINDOW_S", 600)
    idle_max = max(_env_float("NOUGEN_RELAY_LIVE_INTERVAL_S", 60), active)
    slice_s = _env_float("NOUGEN_RELAY_LIVE_WAKE_POLL_S", 0.5)
    wake = wake_path()
    print(json.dumps({"daemon": "relay_live", "active_s": active, "window_s": window, "idle_max_s": idle_max,
                      "wake": str(wake), "interrupts": shield, "pid": os.getpid(),
                      "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), flush=True)
    interval, last_active = active, time.time()
    while True:
        new_count = 0
        try:
            new_count = int(one_pass(dry=dry, quiet=quiet).get("new", 0))
        except Exception as exc:  # pylint: disable=broad-except
            print(json.dumps({"error": f"{type(exc).__name__}: {exc}"[:300]}), flush=True)
        now = time.time()
        if new_count:
            last_active = now
        interval = next_interval(interval, new_count, now, last_active, active=active, window=window, idle_max=idle_max)
        if wait(interval, wake, slice_s) == "wake":
            last_active = time.time()
            interval = active


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--daemon", action="store_true")
    ap.add_argument("--wake", action="store_true", help="touch the wake file so a running daemon passes now")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    if a.wake:
        print(json.dumps({"woke": str(touch_wake())}))
        return 0
    if a.daemon:
        run_daemon(dry=a.dry_run, quiet=a.quiet)
    one_pass(dry=a.dry_run, quiet=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

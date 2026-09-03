#!/usr/bin/env python
"""
Cross-agent handoff enforcement guard (Claude Code hooks; reusable by any harness).

The NouGen handoff contract only works if every agent (1) reads the latest
handoff before planning and (2) leaves one before ending. Relying on each agent
to *remember* is why parallel agents trip over each other. This guard makes it
structural:

  --mode sessionstart : record a session marker + inject the latest handoff as
                        context, so no agent can claim it didn't see prior work.
  --mode stop         : NON-blocking nudge. If the repo has uncommitted work and
                        no handoff was written this session, remind the agent to
                        write one. (Stop fires every turn, so it must not block.)
  --mode sessionend   : if no handoff was written this session, AUTO-WRITE a
                        git-state stub handoff so a session is NEVER traceless.
                        The stub is written synchronously (sub-second); the index
                        rebuild (measured 25 s on 748 records, longer than the
                        hook timeout) is spawned detached so the hook returns
                        before Claude Code cancels it.

Reads the hook event JSON on stdin (Claude Code protocol). Safe to run anywhere;
all failures are swallowed so a hook can never wedge the session.

Env: NOUGEN_REPO, NOUGEN_HANDOFF_DIR, NOUGEN_AGENT, NOUGEN_PY,
NOUGEN_HOOK_GIT_TIMEOUT_S (per git call, default 5),
NOUGEN_SESSION_MARKER_MAX_AGE_H (stale .start markers swept at sessionstart, default 168).
"""
import sys, os, json, glob, time, subprocess, datetime
from pathlib import Path

REPO = Path(os.environ.get("NOUGEN_REPO", str(Path(__file__).resolve().parents[1])))
HANDOFF_DIR = Path(os.environ.get("NOUGEN_HANDOFF_DIR", str(REPO / ".handoffs")))
SESS_DIR = HANDOFF_DIR / ".sessions"
AGENT = os.environ.get("NOUGEN_AGENT", "claude-cli")


def _env_float(name, default):
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return float(default)


GIT_TIMEOUT_S = _env_float("NOUGEN_HOOK_GIT_TIMEOUT_S", 5)
MARKER_MAX_AGE_S = _env_float("NOUGEN_SESSION_MARKER_MAX_AGE_H", 168) * 3600


def _arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def _handoff_files():
    return glob.glob(str(HANDOFF_DIR / "**" / "handoff_*.md"), recursive=True)


def _latest_mtime():
    return max((os.path.getmtime(f) for f in _handoff_files()), default=0.0)


def _newest_text(limit=1800):
    files = _handoff_files()
    if not files:
        return "(no handoffs in registry yet)"
    newest = max(files, key=os.path.getmtime)
    try:
        return Path(newest).read_text(encoding="utf-8", errors="replace")[:limit]
    except Exception:
        return "(latest handoff unreadable)"


def _git(*args):
    try:
        return subprocess.run(["git", "-C", str(REPO), *args],
                              capture_output=True, text=True, timeout=GIT_TIMEOUT_S).stdout.strip()
    except Exception:
        return ""


def _marker(sid):
    return SESS_DIR / f"{sid}.start"


def _sweep_markers(now=None):
    """Delete .start markers older than MARKER_MAX_AGE_S. Sessions that died
    without a SessionEnd (power-off, cancelled hook) leave them behind; 386 had
    piled up by 2026-09-03."""
    now = time.time() if now is None else now
    removed = 0
    for p in SESS_DIR.glob("*.start"):
        try:
            if now - p.stat().st_mtime > MARKER_MAX_AGE_S:
                p.unlink()
                removed += 1
        except Exception:
            pass
    return removed


def _spawn_detached(cmd, cwd, env):
    """Start a process that outlives this hook. The hook must return quickly;
    Claude Code cancels SessionEnd hooks that run past their timeout."""
    kw = dict(cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    if os.name == "nt":
        kw["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0)
                               | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                               | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        kw["start_new_session"] = True
    return subprocess.Popen(cmd, **kw)


def _emit_context(event, text):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": event, "additionalContext": text}}))


def main():
    try:
        evt = json.load(sys.stdin)
    except Exception:
        evt = {}
    mode = _arg("--mode", "stop")
    sid = evt.get("session_id", "unknown")
    SESS_DIR.mkdir(parents=True, exist_ok=True)
    marker = _marker(sid)

    if mode == "sessionstart":
        try:
            marker.write_text(str(time.time()), encoding="utf-8")
        except Exception:
            pass
        _sweep_markers()
        _emit_context("SessionStart",
                      "📋 LATEST CROSS-AGENT HANDOFF — read before planning; you MUST "
                      "leave a fresh handoff before this session ends:\n\n" + _newest_text())
        return

    # determine session start time (fallback: 12h ago if marker missing)
    start = time.time() - 43200
    if marker.exists():
        try:
            start = float(marker.read_text().strip())
        except Exception:
            pass
    fresh = _latest_mtime() > start

    if mode == "stop":
        # Per-turn: never block. Nudge only when real work is pending a handoff.
        if not fresh and _git("status", "--short"):
            _emit_context("Stop",
                          "⚠️ Uncommitted work exists and no handoff has been written this "
                          "session. Before you stop for the user, write one: "
                          "`python -m nougen_shards.cli handoff create -a " + AGENT +
                          " -g \"<goal>\" -m \"<summary>\"` then `handoff rebuild-db`.")
        return

    if mode == "sessionend":
        if fresh:
            _cleanup(marker)
            return
        # Auto-write a stub so the session is never traceless.
        branch = _git("branch", "--show-current") or "unknown"
        status = _git("status", "--short") or "(clean)"
        log = _git("log", "--oneline", "-3")
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        body = (f"# 🤝 Agent Handoff (AUTO): {branch} @ {ts}\n\n"
                f"**Agent**: `{AGENT}` (auto-stub — agent ended without writing one)\n"
                f"**Session ID**: `{sid}`\n\n"
                f"## Recent Changes\n- Session ended without a manual handoff. Git state below.\n\n"
                f"## Uncommitted Changes\n```\n{status}\n```\n\n"
                f"## Recent Commits\n```\n{log}\n```\n\n"
                f"> Auto-generated by handoff_guard to preserve the cross-agent trace.\n")
        outdir = HANDOFF_DIR / f"{AGENT.replace('-', ' ')} handoffs"
        try:
            outdir.mkdir(parents=True, exist_ok=True)
            (outdir / f"handoff_{ts}_{AGENT}_auto.md").write_text(body, encoding="utf-8")
        except Exception:
            pass
        # The stub is on disk: that is the invariant. Marker cleanup next, then
        # the slow index rebuild in the background so the hook itself returns
        # in well under its timeout.
        _cleanup(marker)
        try:
            py = os.environ.get("NOUGEN_PY", str(REPO / ".venv/Scripts/python.exe"))
            _spawn_detached([py, "-m", "nougen_shards.cli", "handoff", "rebuild-db"],
                            REPO, {**os.environ, "PYTHONPATH": str(REPO / "src")})
        except Exception:
            pass
        return


def _cleanup(marker):
    try:
        if marker.exists():
            marker.unlink()
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # a hook must never wedge the session

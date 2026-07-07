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

Reads the hook event JSON on stdin (Claude Code protocol). Safe to run anywhere;
all failures are swallowed so a hook can never wedge the session.
"""
import sys, os, json, glob, time, subprocess, datetime
from pathlib import Path

# The guard lives in <repo>/tools/, so the repo root is derivable — no
# machine-specific default needed.
REPO = Path(os.environ.get("NOUGEN_REPO", str(Path(__file__).resolve().parents[1])))
HANDOFF_DIR = Path(os.environ.get("NOUGEN_HANDOFF_DIR", str(REPO / ".handoffs")))
SESS_DIR = HANDOFF_DIR / ".sessions"
AGENT = os.environ.get("NOUGEN_AGENT", "claude-cli")
def _resolve_vault_dir():
    """Portable vault resolution — nothing machine-specific in code:
    NOUGEN_VAULT_DIR env -> ~/.nougen/config.json {"vault_dir": ...} ->
    repo-local .vault -> per-user default (mirrors nougen_shards.core)."""
    env = os.environ.get("NOUGEN_VAULT_DIR")
    if env:
        return Path(env)
    try:
        cfg = json.loads((Path.home() / ".nougen" / "config.json").read_text(encoding="utf-8"))
        if cfg.get("vault_dir"):
            return Path(cfg["vault_dir"])
    except Exception:
        pass
    local = REPO / ".vault"
    if local.is_dir():
        return local
    return Path.home() / ".nougen" / "shards"


VAULT_DIR = _resolve_vault_dir()


def _write_vault_shard(sid, agent, branch, status, log, handoff_excerpt):
    """Auto-capture a session intelligence shard into the Watchtower vault.

    The vault's distillation lane went stale when its manual sync stopped
    running; this makes vault capture structural, same as the handoff stub.
    Swallows every exception — a hook must never wedge the session.
    """
    try:
        import re
        sid8 = str(sid)[:8]
        existing = glob.glob(str(VAULT_DIR / "intelligence_shard_*.md"))
        # Dedupe per session: filenames embed sid8.
        if any(f"_session_{sid8}_" in os.path.basename(f) for f in existing):
            return
        max_id = 0  # dynamic: next id is always max(existing)+1, any vault
        pat = re.compile(r"intelligence_shard_(\d+)_")
        for f in existing:
            m = pat.search(os.path.basename(f))
            if m:
                max_id = max(max_id, int(m.group(1)))
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        excerpt = (handoff_excerpt or "")[:1200]
        body = (f"# 🌑 SESSION_INTEL {max_id + 1}: Auto Session Capture\n\n"
                f"**Agent:** {agent}\n"
                f"**Session ID:** `{sid}`\n"
                f"**Branch:** `{branch}`\n"
                f"**Captured:** {ts}\n\n"
                f"## 📜 System Ledger\n\n"
                f"### Recent Commits\n```\n{log or '(none)'}\n```\n\n"
                f"### Uncommitted Changes\n```\n{status or '(clean)'}\n```\n\n"
                f"## 🛤️ Latest Handoff Excerpt\n{excerpt}\n\n"
                f"> Auto-captured by handoff_guard vault lane.\n")
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        name = f"intelligence_shard_{max_id + 1}_auto_session_{sid8}_{ts}.md"
        (VAULT_DIR / name).write_text(body, encoding="utf-8")
    except Exception:
        pass


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
                              capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception:
        return ""


def _marker(sid):
    return SESS_DIR / f"{sid}.start"


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
        branch = _git("branch", "--show-current") or "unknown"
        status = _git("status", "--short") or "(clean)"
        log = _git("log", "--oneline", "-3")
        # Vault capture is unconditional: the probe's "last memory" must
        # reflect every working session, not just ones missing a handoff.
        _write_vault_shard(sid, AGENT, branch, status, log, _newest_text(1200))
        if fresh:
            _cleanup(marker)
            return
        # Auto-write a stub so the session is never traceless.
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
            # best-effort index rebuild
            py = os.environ.get("NOUGEN_PY", str(REPO / ".venv/Scripts/python.exe"))
            subprocess.run([py, "-m", "nougen_shards.cli", "handoff", "rebuild-db"],
                           cwd=str(REPO), env={**os.environ, "PYTHONPATH": str(REPO / "src")},
                           capture_output=True, timeout=60)
        except Exception:
            pass
        _cleanup(marker)
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

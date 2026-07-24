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
import sys, os, json, glob, time, hashlib, subprocess, datetime
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

# Auto-session capture knobs (Rule 0.2: env -> logged fallback constant).
#   HASH_LEN     : chars of the payload sha256 embedded in the filename.
#   DEDUP_BUCKET : strftime bucket mixed into the hash. "%Y%m%d" = at most one
#                  shard per identical git-state per day; "" = dedupe forever.
#   ID_RETRIES   : bounded retries when another session claims the same shard id.
#   CLAIM_STALE_S: age after which an abandoned .partial id-claim is reclaimed.
AUTO_SESSION_HASH_LEN = int(os.environ.get("NOUGEN_AUTO_SESSION_HASH_LEN", "12"))
AUTO_SESSION_DEDUP_BUCKET = os.environ.get("NOUGEN_AUTO_SESSION_DEDUP_BUCKET", "%Y%m%d")
AUTO_SESSION_ID_RETRIES = int(os.environ.get("NOUGEN_AUTO_SESSION_ID_RETRIES", "12"))
AUTO_SESSION_CLAIM_STALE_S = float(os.environ.get("NOUGEN_AUTO_SESSION_CLAIM_STALE_S", "60"))


def _payload_hash(agent, branch, status, log, excerpt, bucket):
    """Content fingerprint of what the capture actually *records*.

    Deliberately excludes the session id and the capture timestamp: N sessions
    ending together report the same git state, so they must collapse to one
    shard instead of N near-identical ones.
    """
    h = hashlib.sha256()
    for part in (agent, branch, status, log, excerpt, bucket):
        h.update((part or "").encode("utf-8", "replace"))
        h.update(b"\x1f")
    return h.hexdigest()[:AUTO_SESSION_HASH_LEN]


def _claim(path):
    """Atomic cross-process claim: O_EXCL create, or None if someone holds it.

    A claim older than CLAIM_STALE_S is treated as abandoned (writer crashed)
    and reclaimed once, so a dead session can never wedge the lane forever.
    """
    for _ in range(2):
        try:
            os.close(os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return path
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(path) > AUTO_SESSION_CLAIM_STALE_S:
                    os.unlink(path)
                    continue
            except Exception:
                pass
            return None
        except Exception:
            return None
    return None


def _unclaim(path):
    try:
        if path is not None:
            os.unlink(path)
    except Exception:
        pass


def _next_shard_id(pattern):
    """Highest existing intelligence_shard_<n>_ id in the vault, + 1."""
    import re
    max_id = 0  # dynamic: next id is always max(existing)+1, any vault
    for f in glob.glob(str(VAULT_DIR / "intelligence_shard_*")):
        m = pattern.search(os.path.basename(f))
        if m:
            max_id = max(max_id, int(m.group(1)))
    return max_id + 1


def _write_vault_shard(sid, agent, branch, status, log, handoff_excerpt):
    """Auto-capture a session intelligence shard into the Watchtower vault.

    The vault's distillation lane went stale when its manual sync stopped
    running; this makes vault capture structural, same as the handoff stub.

    Idempotent on two keys, because sessionend fires per session and sessions
    end in batches: (1) the session id, so re-runs of one session never stack;
    (2) a content hash of the captured payload, so sibling sessions reporting
    identical git state produce one shard, not one each.
    Swallows every exception — a hook must never wedge the session.
    """
    try:
        import re
        sid8 = str(sid)[:8]
        excerpt = (handoff_excerpt or "")[:1200]
        bucket = (datetime.datetime.now().strftime(AUTO_SESSION_DEDUP_BUCKET)
                  if AUTO_SESSION_DEDUP_BUCKET else "")
        chash = _payload_hash(agent, branch, status, log, excerpt, bucket)
        VAULT_DIR.mkdir(parents=True, exist_ok=True)

        def _already_captured():
            # (a) this session already wrote one (legacy names match too)
            if glob.glob(str(VAULT_DIR / f"intelligence_shard_*_session_{sid8}_*.md")):
                return True
            # (b) a sibling session already recorded this exact payload
            if glob.glob(str(VAULT_DIR / f"intelligence_shard_*_auto_session_*_{chash}.md")):
                return True
            return False

        if _already_captured():
            return

        # Payload lock. A filesystem O_EXCL create is the only check that is
        # actually atomic across processes: 8 sessions ending in the same second
        # all pass a plain glob test, which is exactly how 8 near-identical
        # shards landed on 2026-07-24. Exactly one writer per payload wins here.
        plock = _claim(VAULT_DIR / f".auto_session_{chash}.lock")
        if plock is None:
            return
        try:
            if _already_captured():
                return
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            base = _next_shard_id(re.compile(r"intelligence_shard_(\d+)_"))
            for offset in range(max(1, AUTO_SESSION_ID_RETRIES)):
                shard_id = base + offset
                # Claim the id separately: the final filename embeds sid8, so
                # O_EXCL on it would let two different payloads share an id.
                ilock = _claim(VAULT_DIR / f".shard_id_{shard_id}.lock")
                if ilock is None:
                    continue
                try:
                    body = (f"# 🌑 SESSION_INTEL {shard_id}: Auto Session Capture\n\n"
                            f"**Agent:** {agent}\n"
                            f"**Session ID:** `{sid}`\n"
                            f"**Branch:** `{branch}`\n"
                            f"**Captured:** {ts}\n"
                            f"**Payload Hash:** `{chash}`\n\n"
                            f"## 📜 System Ledger\n\n"
                            f"### Recent Commits\n```\n{log or '(none)'}\n```\n\n"
                            f"### Uncommitted Changes\n```\n{status or '(clean)'}\n```\n\n"
                            f"## 🛤️ Latest Handoff Excerpt\n{excerpt}\n\n"
                            f"> Auto-captured by handoff_guard vault lane.\n")
                    name = f"intelligence_shard_{shard_id}_auto_session_{sid8}_{ts}_{chash}.md"
                    (VAULT_DIR / name).write_text(body, encoding="utf-8")
                finally:
                    _unclaim(ilock)
                return
        finally:
            _unclaim(plock)
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


def _cue_memory(event, paths=(), symbols=(), text=""):
    """Cue-anchored delivery (paper: "Delivery, Not Storage").

    Voluntary recall is the weak link — an agent with a memory tool basically
    never calls it. So the harness evaluates each shard's trigger conditions
    itself and hands over the survivors. Deterministic, no model call, hard
    token budget. Returns "" when nothing fires, so the existing handoff
    injection below is byte-identical whenever the trigger table is empty.
    """
    try:
        src = str(REPO / "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        from nougen_shards import triggers  # pylint: disable=import-outside-toplevel
        return triggers.deliver(event, cwd=str(REPO), paths=paths,
                                symbols=symbols, text=text)
    except Exception:
        return ""  # a memory lane must never wedge a hook


def _tool_paths(evt):
    """Best-effort extraction of the paths a tool call is about."""
    keys = os.environ.get(
        "NOUGEN_TRIGGER_TOOL_PATH_KEYS",
        "file_path,path,notebook_path,filePath").split(",")
    ti = evt.get("tool_input") or {}
    out = []
    if isinstance(ti, dict):
        for k in keys:
            v = ti.get(k.strip())
            if isinstance(v, str) and v:
                out.append(v)
    return out


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
        body = ("📋 LATEST CROSS-AGENT HANDOFF — read before planning; you MUST "
                "leave a fresh handoff before this session ends:\n\n" + _newest_text())
        # Front door for cue-anchored memory: appended, never substituted, so
        # the handoff contract above is unchanged when no trigger fires.
        cues = _cue_memory("session_start", paths=[str(REPO)])
        if cues:
            body += "\n\n" + cues
        _emit_context("SessionStart", body)
        return

    if mode == "pretooluse":
        # Opt-in (NOUGEN_TRIGGERS_PRETOOLUSE=1): fires many times per turn, so
        # it stays off until an operator turns it on, even once registered.
        try:
            src = str(REPO / "src")
            if src not in sys.path:
                sys.path.insert(0, src)
            from nougen_shards import triggers  # pylint: disable=import-outside-toplevel
            if not triggers.pretooluse_enabled():
                return
        except Exception:
            return
        cues = _cue_memory("pre_tool_use", paths=_tool_paths(evt),
                           text=str(evt.get("tool_name", "")))
        if cues:
            _emit_context("PreToolUse", cues)
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

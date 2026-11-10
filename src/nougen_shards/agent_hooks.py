"""Agent harness hooks: make an agent use the vault without being told to.

`nougen hook install` wires these into Claude Code's settings so a fresh install
behaves like a tuned one:

- session-start : inject the latest cross-agent handoff and the newest shards,
                  and mark the session so session-end knows what was written.
- prompt        : budgeted per-message recall (``recall_hook``) when available.
- stop          : the shard + relay reflex. When the session changed something
                  and has not captured a shard or filed a relay leg, the agent
                  is sent back once to do both. Otherwise a non-blocking nudge
                  to write a handoff when uncommitted work has none.
- session-end   : auto-write a git-state handoff if the session left none, so
                  no session is traceless.
- pre-tool      : context mode is mandatory. An unbounded read, search, fetch
                  or test run is refused with the sandbox call to use instead.
- post-tool     : records work, shard captures and relay legs for ``stop``.

Every event is fail-soft: any error prints ``{}`` so a hook can never wedge the
host. Nothing here is machine-specific; paths resolve from env, then the vault
and handoff defaults the rest of the package uses.
"""
from __future__ import annotations

import contextlib
import datetime
import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

EVENTS = ("session-start", "prompt", "stop", "session-end", "pre-tool", "post-tool")
#: Claude Code event name for each of our events.
CLAUDE_EVENTS = {"session-start": "SessionStart", "prompt": "UserPromptSubmit",
                 "stop": "Stop", "session-end": "SessionEnd",
                 "pre-tool": "PreToolUse", "post-tool": "PostToolUse"}
#: Signature that marks a settings entry as ours (install/uninstall touch only these).
SIGNATURE = "nougen_shards.cli hook run"
#: The per-tool events fire on every tool call, so they skip the CLI (0.84s to
#: import, measured 2026-11-09) and enter this module directly (0.15s).
FAST_SIGNATURE = "nougen_shards.agent_hooks run"
FAST_EVENTS = ("pre-tool", "post-tool")
#: Tool-name matchers for the per-tool events. PostToolUse only needs the tools
#: that can count as work, a shard or a relay leg; anything else never spawns us.
TOOL_MATCHERS = {
    "pre-tool": "Bash|PowerShell|Read",
    "post-tool": "Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell|mcp__.*(shard|relay|capture).*",
}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _agent() -> str:
    return os.environ.get("NOUGEN_AGENT", "claude-cli")


def _handoff_dir() -> Path:
    """The same registry `nougen handoff` writes to (handoff.HANDOFF_DIR)."""
    from . import handoff  # pylint: disable=import-outside-toplevel
    return Path(handoff.HANDOFF_DIR)


def _marker(session_id: str) -> Path:
    safe = "".join(c for c in (session_id or "unknown") if c.isalnum() or c in "-_")[:80] or "unknown"
    return _handoff_dir() / ".sessions" / f"{safe}.start"


def _handoff_files() -> list[str]:
    return glob.glob(str(_handoff_dir() / "**" / "handoff_*.md"), recursive=True)


def latest_handoff_text(limit: Optional[int] = None) -> str:
    limit = limit or _int_env("NOUGEN_HOOK_HANDOFF_CHARS", 1800)
    files = _handoff_files()
    if not files:
        return ""
    # A manual handoff beats an auto-stub, which only carries git state.
    manual = [f for f in files if not os.path.basename(f).endswith("_auto.md")]
    newest = max(manual or files, key=os.path.getmtime)
    try:
        return Path(newest).read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def recent_shards(limit: Optional[int] = None) -> list[tuple[str, str, str]]:
    """Newest (timestamp, event_type, title) across every vault DB, read-only."""
    limit = limit or _int_env("NOUGEN_HOOK_RECENT_SHARDS", 6)
    from . import core  # pylint: disable=import-outside-toplevel
    rows: list[tuple[str, str, str]] = []
    for db in sorted(core.active_vault_dir().glob("nougen_shards_*.db")):
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1.0)
            try:
                rows += con.execute("SELECT timestamp, event_type, title FROM shards "
                                    "ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
            finally:
                con.close()
        except sqlite3.Error:
            continue
    rows.sort(key=lambda r: str(r[0] or ""), reverse=True)
    return [(str(t or ""), str(e or "SHARD"), str(title or "")) for t, e, title in rows[:limit]]


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:  # pylint: disable=broad-except
        return ""


def _context(event: str, text: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": CLAUDE_EVENTS[event], "additionalContext": text}}


def session_start(evt: dict) -> dict:
    marker = _marker(evt.get("session_id", ""))
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass
    parts: list[str] = []
    handoff = latest_handoff_text()
    if handoff:
        parts.append("LATEST CROSS-AGENT HANDOFF (read before planning; leave a fresh one "
                     "before this session ends):\n\n" + handoff)
    try:
        shards = recent_shards()
    except Exception:  # pylint: disable=broad-except
        shards = []
    if shards:
        parts.append("NOUGEN VAULT, newest shards:\n" + "\n".join(
            f"- [{t[:16]}] {e}: {title[:100]}" for t, e, title in shards))
    parts.append("Recall from the vault (`nougen recall` / the nougen-shards MCP tools) before "
                 "reasoning from scratch, and capture decisions and fixes back to it.")
    return _context("session-start", "\n\n".join(parts))


def prompt(evt: dict) -> dict:
    try:
        from . import recall_hook  # pylint: disable=import-outside-toplevel
    except ImportError:
        return {}
    return json.loads(recall_hook.claude_code_hook(json.dumps(evt)))


def _started(evt: dict) -> float:
    try:
        return float(_marker(evt.get("session_id", "")).read_text().strip())
    except (OSError, ValueError):
        return time.time() - 12 * 3600


def _same_tree(a: str, b: Path) -> bool:
    """True when two directories are the same or one contains the other.

    A session moves between a workspace root and a project inside it, so a
    handoff written from one must count for a hook running in the other."""
    try:
        written = Path(a).resolve()
    except (OSError, TypeError, ValueError):
        return False
    return written == b or written in b.parents or b in written.parents


def _handoff_written_since(start: float) -> bool:
    """True when a handoff record newer than ``start`` was written from this
    working directory, a project inside it, or the workspace that holds it.
    Records from unrelated projects in the shared registry do not count, so
    they never suppress this session's auto-handoff."""
    here = Path.cwd().resolve()
    for f in glob.glob(str(_handoff_dir() / "**" / "handoff_*.json"), recursive=True):
        try:
            if os.path.getmtime(f) <= start:
                continue
            with open(f, encoding="utf-8") as fh:
                written = json.load(fh).get("cwd")
            if written and _same_tree(written, here):
                return True
        except (OSError, ValueError, AttributeError):
            continue
    return False


# ------------------------------------------------------------------- reflex
#
# Shard + relay as a reflex, not a rule the agent has to remember. Rules in
# AGENTS.md / CLAUDE.md are only read; nothing checked that they were followed,
# so a session could change code and end with no shard and no leg. The host's
# own lifecycle closes that gap:
#
#   post-tool  records, per session, whether work happened (an edit or a commit)
#              and whether a shard was captured / a relay leg filed or acked.
#   stop       when work happened and either is missing, sends the agent back
#              once to do it, with the exact calls. Once per stretch of work:
#              an agent that declines is not asked again until it does more.
#   pre-tool   context mode: an unbounded read/search/fetch is refused with the
#              sandbox call to use instead, so raw output never floods context.
#
# NOUGEN_REFLEX = block (default) | nudge | off.  NOUGEN_CTX_GATE = deny (default) | warn | off.

_SHARD_TOOL = re.compile(r"(shards_capture|shards_amend|capture_experience|add_shard|promote_context_to_shard)", re.I)
_RELAY_TOOL = re.compile(r"relay_(create|ack)", re.I)
_SHARD_CMD = re.compile(r"(\bnougen(\.bat)?\s+(add|capture)\b|nougen_shards\.cli\s+(add|capture)\b|core\.capture\()", re.I)
_RELAY_CMD = re.compile(r"(nougen_relay\.cli\s+(create|ack)\b|git_handoff\.py\s+(create|ack)\b|\brelay\s+(create|ack)\b)", re.I)
_WORK_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch"}
_WORK_CMD = re.compile(r"\bgit\s+commit\b", re.I)
_SHELL_TOOLS = {"Bash", "PowerShell", "shell", "local_shell"}


def _mode(name: str, default: str, allowed: tuple) -> str:
    val = os.environ.get(name, default).strip().lower()
    return val if val in allowed else default


def _sessions_dir() -> Path:
    """Session state lives beside the handoff registry, next to the start marker."""
    return _handoff_dir() / ".sessions"


def _reflex_path(session_id: str) -> Path:
    safe = "".join(c for c in (session_id or "unknown") if c.isalnum() or c in "-_")[:80] or "unknown"
    return _sessions_dir() / f"{safe}.reflex.json"


def reflex_state(session_id: str) -> dict:
    try:
        data = json.loads(_reflex_path(session_id).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_reflex(session_id: str, state: dict) -> None:
    path = _reflex_path(session_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


@contextlib.contextmanager
def _reflex_lock(session_id: str):
    """Serialize read-modify-write of one session's reflex state across processes.

    Tool calls can finish together, each in its own hook process. Atomic replace
    keeps the file well-formed but not the update: a shard and a leg landing at
    once could each read the old state and one would be lost, so Stop would ask
    again for a record that exists. O_EXCL lock file; a lock older than 10s is
    from a dead hook and is taken over. On timeout the caller proceeds unlocked:
    a hook must never wedge the host.
    """
    lock = _reflex_path(session_id).with_suffix(".lock")
    held = False
    deadline = time.monotonic() + _int_env("NOUGEN_REFLEX_LOCK_MS", 2000) / 1000.0
    while True:
        try:
            lock.parent.mkdir(parents=True, exist_ok=True)
            os.close(os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            held = True
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 10:
                    lock.unlink()
                    continue
            except OSError:
                pass
        except OSError:
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(0.01)
    try:
        yield held
    finally:
        if held:
            try:
                lock.unlink()
            except OSError:
                pass


def _command_of(evt: dict) -> str:
    inp = evt.get("tool_input")
    if not isinstance(inp, dict):
        return ""
    return str(inp.get("command") or inp.get("cmd") or "")


def post_tool(evt: dict) -> dict:
    name = str(evt.get("tool_name") or "")
    cmd = _command_of(evt) if name in _SHELL_TOOLS else ""
    shard = bool(_SHARD_TOOL.search(name) or (cmd and _SHARD_CMD.search(cmd)))
    relay = bool(_RELAY_TOOL.search(name) or (cmd and _RELAY_CMD.search(cmd)))
    work = name in _WORK_TOOLS or bool(cmd and _WORK_CMD.search(cmd))
    if not (shard or relay or work):
        return {}
    sid = str(evt.get("session_id") or "")
    with _reflex_lock(sid):
        state = reflex_state(sid)
        if work:
            state["work"] = int(state.get("work", 0)) + 1
        if shard:
            state["shard"] = True
        if relay:
            state["relay"] = True
        if state.get("shard") and state.get("relay"):
            # Both done: this stretch of work is on the record. Start a new one.
            state = {"work": 0, "done": int(state.get("done", 0)) + 1}
        _save_reflex(sid, state)
    return {}


def reflex_missing(state: dict) -> list[str]:
    if int(state.get("work", 0)) <= 0:
        return []
    return [k for k in ("shard", "relay") if not state.get(k)]


def _reflex_text(state: dict, missing: list[str]) -> str:
    steps = []
    if "shard" in missing:
        steps.append("Capture one shard (`shards_capture`, or `nougen add`): what changed, why, "
                     "and the proof (commit, PR or path).")
    if "relay" in missing:
        steps.append("Relay it (`relay_create`, or `python -m nougen_relay.cli create`): one-line goal, "
                     "then situation / ask / done-when. If an open leg already covers this work, "
                     "`relay_ack` it instead of opening a second one.")
    return ("NouGen reflex: this session made " + str(int(state.get("work", 0))) + " change(s) and has not yet "
            + " or ".join("captured a shard" if m == "shard" else "filed a relay leg" for m in missing)
            + ". Do it now, without asking the operator:\n"
            + "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
            + "\nThen finish. If nothing durable was learned or changed, say so in one line and stop.")


# ------------------------------------------------------------ context mode

_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
_BOUNDED = re.compile(
    r"\|\s*(head|tail|wc|more|less|select(-object)?\s+-(first|last|skip)|measure(-object)?|sls\b.*-quiet)"
    r"|(^|\s)>>?\s*[^&\s]|\bout-file\b|\bset-content\b", re.I)  # not tee: it also copies to stdout
_CMD_START = r"(?:^|[;&|(]\s*|\s&&\s*)"
_FETCH = re.compile(_CMD_START + r"(curl|wget|invoke-webrequest|iwr|invoke-restmethod|irm)\b", re.I)
_LOCAL_URL = re.compile(r"https?://(localhost|127\.0\.0\.1|\[::1\])[:/]", re.I)
_FETCH_TO_FILE = re.compile(r"(\s-o\s|\s--output\s|-outfile\b)", re.I)
_DUMP = re.compile(_CMD_START + r"(cat|type|get-content|gc)\s+(?P<path>'[^']+'|\"[^\"]+\"|[^\s|;&]+)", re.I)
_DUMP_LIMITED = re.compile(r"-(totalcount|tail|first|last|head)\b", re.I)
_GIT_LOG = re.compile(_CMD_START + r"git\s+(-C\s+\S+\s+)?log\b", re.I)
_GIT_LOG_LIMITED = re.compile(r"(\s-n\s*\d+|\s-\d+\b|--max-count)", re.I)
_GIT_DIFF = re.compile(_CMD_START + r"git\s+(-C\s+\S+\s+)?(diff|show)\b", re.I)
_GIT_DIFF_LIMITED = re.compile(r"--(stat|shortstat|numstat|name-only|name-status|quiet|format|pretty)\b|\s-s\b", re.I)
_RECURSE = re.compile(
    _CMD_START + r"(grep\s+(-\w*\s+)*-\w*[rR]\w*\b|rg\b|findstr\s+/s\b|find\s+\S|ls\s+-\w*R|dir\s+/s\b)", re.I)
# -l / -c style short flags only mean "names" or "count" to grep and rg.
_RECURSE_LIMITED = re.compile(r"(\s-[a-z]{0,6}[lc][a-z]{0,6}\b|--count\b|--files-with-matches\b|-maxdepth\s+[12]\b|\s-quit\b)", re.I)
_PS_RECURSE = re.compile(_CMD_START + r"(get-childitem|gci|select-string|sls)\b[^|;]*-recurse\b", re.I)
_TESTS = re.compile(_CMD_START + r"((python\S*\s+-m\s+)?pytest|npm\s+(run\s+)?test|pnpm\s+test|yarn\s+test|cargo\s+test|go\s+test)\b", re.I)

CTX_HINT = ("Run it in context mode instead: `ctx_execute` / `ctx_batch_execute` (or `nougen ctx execute`) "
            "and print only the answer. Or bound it here: pipe to `head` / `Select-Object -First N`, "
            "or redirect to a file.")


def unbounded_command(command: str, read_max_kb: Optional[int] = None) -> str:
    """Why ``command`` would dump unbounded output into context, or '' if it would not.

    Deliberately narrow: only shapes whose output size is unknowable or known
    large, and never a command that already bounds or redirects its output.
    """
    if not command or _BOUNDED.search(_QUOTED.sub("''", command)):
        return ""
    bare = _QUOTED.sub("''", command)
    if _FETCH.search(bare) and not _FETCH_TO_FILE.search(bare) and not _LOCAL_URL.search(command):
        return "a web fetch prints the whole response"
    m = _DUMP.search(command)
    if m and not _DUMP_LIMITED.search(bare):
        limit = (read_max_kb or _int_env("NOUGEN_CTX_READ_MAX_KB", 60)) * 1024
        try:
            size = os.path.getsize(os.path.expanduser(m.group("path").strip("'\"")))
        except OSError:
            size = 0
        if size > limit:
            return f"it prints a {size // 1024} KB file whole"
    if _GIT_LOG.search(bare) and not _GIT_LOG_LIMITED.search(bare):
        return "`git log` with no -n limit prints the whole history"
    if _GIT_DIFF.search(bare) and not _GIT_DIFF_LIMITED.search(bare):
        return "`git diff` / `git show` with no --stat prints every changed line"
    if (_RECURSE.search(bare) and not _RECURSE_LIMITED.search(bare)) or _PS_RECURSE.search(bare):
        return "a recursive search with no bound can return thousands of lines"
    if _TESTS.search(bare):
        return "a test run prints its whole log"
    return ""


_BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".pdf", ".ipynb", ".svg"}


def pre_tool(evt: dict) -> dict:
    mode = _mode("NOUGEN_CTX_GATE", "deny", ("deny", "warn", "off"))
    if mode == "off":
        return {}
    name = str(evt.get("tool_name") or "")
    inp = evt.get("tool_input") if isinstance(evt.get("tool_input"), dict) else {}
    why = ""
    if name in _SHELL_TOOLS:
        why = unbounded_command(_command_of(evt))
    elif name == "Read" and not inp.get("limit") and not inp.get("offset") and not inp.get("pages"):
        path = str(inp.get("file_path") or "")
        if path and Path(path).suffix.lower() not in _BINARY_EXT:
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            if size > _int_env("NOUGEN_CTX_READ_MAX_KB", 60) * 1024:
                why = (f"it reads a {size // 1024} KB file whole; pass offset/limit for the part you "
                       "will edit, or analyse it with `ctx_execute_file`")
    if not why:
        return {}
    text = f"NouGen context mode: {why}. {CTX_HINT}"
    if mode == "warn":
        return _context("pre-tool", text)
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": text}}


def stop(evt: dict) -> dict:
    mode = _mode("NOUGEN_REFLEX", "block", ("block", "nudge", "off"))
    if mode != "off":
        sid = str(evt.get("session_id") or "")
        text = ""
        with _reflex_lock(sid):
            state = reflex_state(sid)
            missing = reflex_missing(state)
            work = int(state.get("work", 0))
            # stop_hook_active: the host is already continuing because of a Stop
            # hook, so blocking again would loop. asked_at: once per stretch of work.
            if missing and not evt.get("stop_hook_active") and state.get("asked_at") != work:
                state["asked_at"] = work
                _save_reflex(sid, state)
                text = _reflex_text(state, missing)
        if text:
            return {"decision": "block", "reason": text} if mode == "block" else _context("stop", text)
    # Otherwise never block, only nudge when work is pending.
    if _handoff_written_since(_started(evt)) or not _git("status", "--short"):
        return {}
    return _context("stop", "Uncommitted work exists and no handoff was written this session. "
                            "Before you finish, write one: `nougen handoff create -a " + _agent() +
                            " -g \"<goal>\" -M <note-file>`.")


def session_end(evt: dict) -> dict:
    marker = _marker(evt.get("session_id", ""))
    if not _handoff_written_since(_started(evt)):
        note = (f"AUTO: the session ended without writing a handoff.\n"
                f"Host session: {evt.get('session_id', 'unknown')}\n"
                f"Working dir: {Path.cwd().name}\n\n"
                f"Uncommitted changes:\n{_git('status', '--short') or '(clean or not a repo)'}\n\n"
                f"Recent commits:\n{_git('log', '--oneline', '-3')}")
        try:
            import contextlib  # pylint: disable=import-outside-toplevel
            import io  # pylint: disable=import-outside-toplevel
            from . import handoff  # pylint: disable=import-outside-toplevel
            # The registry's own writer: a JSON record plus Markdown, listed and
            # indexed like any manual handoff. Its console output must not reach
            # this hook's stdout, which the host parses as JSON.
            with contextlib.redirect_stdout(io.StringIO()):
                handoff.create_handoff(message=note, agent=_agent(),
                                       goal="auto: session ended without a handoff")
        except Exception:  # pylint: disable=broad-except
            pass
    for path in (marker, _reflex_path(evt.get("session_id", ""))):
        try:
            path.unlink()
        except OSError:
            pass
    return {}


HANDLERS = {"session-start": session_start, "prompt": prompt, "stop": stop, "session-end": session_end,
            "pre-tool": pre_tool, "post-tool": post_tool}


def run(event: str, stdin_text: str) -> str:
    """Entry for `nougen hook run <event>`. Always returns JSON; never raises."""
    try:
        evt = json.loads(stdin_text or "{}")
        if not isinstance(evt, dict):
            evt = {}
        out = HANDLERS[event](evt)
    except Exception:  # pylint: disable=broad-except
        out = {}
    return json.dumps(out, ensure_ascii=False)


# ----------------------------------------------------------------- installer

def claude_settings_path() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".claude") / "settings.json"


def _command(event: str, python: str) -> str:
    return f'"{python}" -m {FAST_SIGNATURE if event in FAST_EVENTS else SIGNATURE} {event}'


def _is_ours(handler: Any) -> bool:
    cmd = str(handler.get("command", "")) if isinstance(handler, dict) else ""
    return SIGNATURE in cmd or FAST_SIGNATURE in cmd


def _ours(entry: dict) -> bool:
    return any(_is_ours(h) for h in entry.get("hooks", []))


def _strip_ours(entries: list) -> list:
    """Remove only our handlers. An entry that also holds foreign handlers keeps
    them along with its matcher and other settings; one left empty is dropped."""
    kept = []
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("hooks"), list):
            kept.append(e)
            continue
        handlers = [h for h in e["hooks"] if not _is_ours(h)]
        if len(handlers) == len(e["hooks"]):
            kept.append(e)
        elif handlers:
            kept.append({**e, "hooks": handlers})
    return kept


def plan_settings(settings: dict, python: str, uninstall: bool = False) -> dict:
    """Return settings with our hooks added (or removed). Foreign hooks are untouched."""
    out = json.loads(json.dumps(settings))
    hooks = out.setdefault("hooks", {})
    for event, claude_event in CLAUDE_EVENTS.items():
        kept = _strip_ours(hooks.get(claude_event, []))
        if not uninstall:
            timeout = _int_env("NOUGEN_HOOK_TIMEOUT_S",
                               20 if event == "session-end" else 5 if event in FAST_EVENTS else 10)
            entry: dict = {"hooks": [{"type": "command", "command": _command(event, python), "timeout": timeout}]}
            if event in TOOL_MATCHERS:
                entry = {"matcher": TOOL_MATCHERS[event], **entry}
            kept.append(entry)
        if kept:
            hooks[claude_event] = kept
        else:
            hooks.pop(claude_event, None)
    if not hooks:
        out.pop("hooks", None)
    return out


def install(settings_path: Optional[Path] = None, python: Optional[str] = None,
            uninstall: bool = False, dry_run: bool = False) -> dict[str, Any]:
    path = settings_path or claude_settings_path()
    current: dict = {}
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8") or "{}")
    planned = plan_settings(current, python or sys.executable, uninstall=uninstall)
    changed = planned != current
    report = {"settings": str(path), "changed": changed, "action": "uninstall" if uninstall else "install",
              "events": list(CLAUDE_EVENTS.values()), "python": python or sys.executable}
    if dry_run or not changed:
        report["dry_run"] = dry_run
        return report
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(f"{path.name}.bak-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(path, backup)
        report["backup"] = str(backup)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(planned, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return report


def status(settings_path: Optional[Path] = None) -> dict[str, Any]:
    path = settings_path or claude_settings_path()
    try:
        settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        settings = {}
    found: dict[str, str] = {}
    for claude_event, entries in (settings.get("hooks") or {}).items():
        for e in entries:
            if isinstance(e, dict) and _ours(e):
                found[claude_event] = e["hooks"][0]["command"]
    pythons = {c.split('"')[1] for c in found.values() if c.startswith('"')}
    return {"settings": str(path), "installed": sorted(found),
            "missing": sorted(set(CLAUDE_EVENTS.values()) - set(found)),
            "interpreter_ok": all(Path(p).exists() for p in pythons) if pythons else None}


def main(argv: Optional[list] = None) -> int:
    """`python -m nougen_shards.agent_hooks run <event>`: the per-tool entry.

    Same contract as `nougen hook run`, without importing the CLI. Reads raw
    bytes: the Windows console codepage would otherwise mangle pasted text.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "run" or args[1] not in EVENTS:
        sys.stderr.write("usage: python -m nougen_shards.agent_hooks run <" + " | ".join(EVENTS) + ">\n")
        return 2
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    except Exception:  # pylint: disable=broad-except
        raw = ""
    sys.stdout.write(run(args[1], raw) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

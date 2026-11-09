"""Agent harness hooks: make an agent use the vault without being told to.

`nougen hook install` wires these into Claude Code's settings so a fresh install
behaves like a tuned one:

- session-start : inject the latest cross-agent handoff and the newest shards,
                  and mark the session so session-end knows what was written.
- prompt        : budgeted per-message recall (``recall_hook``) when available.
- stop          : non-blocking nudge to write a handoff when there is
                  uncommitted work and none was written this session.
- session-end   : auto-write a git-state handoff if the session left none, so
                  no session is traceless.

Every event is fail-soft: any error prints ``{}`` so a hook can never wedge the
host. Nothing here is machine-specific; paths resolve from env, then the vault
and handoff defaults the rest of the package uses.
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

EVENTS = ("session-start", "prompt", "stop", "session-end")
#: Claude Code event name for each of our events.
CLAUDE_EVENTS = {"session-start": "SessionStart", "prompt": "UserPromptSubmit",
                 "stop": "Stop", "session-end": "SessionEnd"}
#: Signature that marks a settings entry as ours (install/uninstall touch only these).
SIGNATURE = "nougen_shards.cli hook run"


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


def _handoff_written_since(start: float) -> bool:
    """True when a handoff record newer than ``start`` was written from this
    working directory. Records from other sessions/projects in the shared
    registry do not count, so they never suppress this session's auto-handoff."""
    here = str(Path.cwd())
    for f in glob.glob(str(_handoff_dir() / "**" / "handoff_*.json"), recursive=True):
        try:
            if os.path.getmtime(f) <= start:
                continue
            with open(f, encoding="utf-8") as fh:
                if json.load(fh).get("cwd") == here:
                    return True
        except (OSError, ValueError, AttributeError):
            continue
    return False


def stop(evt: dict) -> dict:
    # Stop fires every turn: never block, only nudge when work is pending.
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
    try:
        marker.unlink()
    except OSError:
        pass
    return {}


HANDLERS = {"session-start": session_start, "prompt": prompt, "stop": stop, "session-end": session_end}


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
    return f'"{python}" -m {SIGNATURE} {event}'


def _is_ours(handler: Any) -> bool:
    return isinstance(handler, dict) and SIGNATURE in str(handler.get("command", ""))


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
            timeout = _int_env("NOUGEN_HOOK_TIMEOUT_S", 20 if event == "session-end" else 10)
            kept.append({"hooks": [{"type": "command", "command": _command(event, python), "timeout": timeout}]})
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

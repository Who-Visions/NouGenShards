"""Triggers: run something when a handoff changes state.

A handoff is a message. A trigger is what makes that message actionable across
computers: when the Mac writes "branch pushed, needs a Windows build", the
Windows box should be able to react without a human relaying it.

Rules live in ``<handoff dir>/triggers.json`` and are matched against the
handoff record plus the event that just happened. Nothing runs unless the
operator has registered a rule — an empty registry is a no-op — and
``NOUGEN_TRIGGERS=off`` is a hard kill switch for a machine that should stay
passive. ``NOUGEN_TRIGGERS=dry`` records what would have fired without
executing it.

Matching is deliberately blunt (equality and substring, no expression
language): a rule that fires the wrong build on the wrong machine is worse than
a rule that is too dumb to express what you wanted.
"""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from . import machine

TRIGGER_FILE_NAME = "triggers.json"
TRIGGER_EVENTS = (
    "created",
    "acknowledged",
    "started",
    "checkpoint",
    "blocked",
    "completed",
)
ORIGINS = ("any", "local", "remote")
DEFAULT_TIMEOUT = 60
_OUTPUT_TAIL = 2000


def _handoff_module():
    # Imported lazily: handoff.py fires triggers, so a module-level import here
    # would be circular.
    from . import handoff

    return handoff


def get_trigger_file() -> Path:
    return _handoff_module().HANDOFF_DIR / TRIGGER_FILE_NAME


def trigger_mode() -> str:
    """'on' | 'dry' | 'off' — the machine-level switch for trigger execution."""
    raw = (os.environ.get("NOUGEN_TRIGGERS") or "").strip().lower()
    if raw in {"off", "0", "false", "no", "disabled"}:
        return "off"
    if raw in {"dry", "dry-run", "dryrun", "test"}:
        return "dry"
    return "on"


def load_triggers() -> list[dict]:
    path = get_trigger_file()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    triggers = data.get("triggers") if isinstance(data, dict) else data
    return [t for t in (triggers or []) if isinstance(t, dict)]


def save_triggers(triggers: list[dict]) -> Path:
    path = get_trigger_file()
    _handoff_module()._atomic_write_json(path, {"version": 1, "triggers": triggers})
    return path


def add_trigger(
    trigger_id: str,
    run: str,
    events: list[str] | None = None,
    origin: str = "any",
    agent: str | None = None,
    host: str | None = None,
    branch: str | None = None,
    goal_contains: str | None = None,
    on_machine: str | None = None,
    background: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    description: str = "",
    enabled: bool = True,
) -> dict:
    """Register (or replace) a trigger. Replacing by id keeps the file idempotent."""
    events = [e.strip().lower() for e in (events or ["created"]) if e.strip()]
    unknown = [e for e in events if e not in TRIGGER_EVENTS]
    if unknown:
        raise ValueError(
            f"Unknown event(s): {', '.join(unknown)}. "
            f"Valid: {', '.join(TRIGGER_EVENTS)}"
        )
    if origin not in ORIGINS:
        raise ValueError(f"Unknown origin '{origin}'. Valid: {', '.join(ORIGINS)}")
    if not run.strip():
        raise ValueError("A trigger needs a command to run.")

    trigger = {
        "id": trigger_id,
        "enabled": enabled,
        "description": description,
        "events": events,
        "match": {
            "origin": origin,
            "agent": (agent or "").lower() or None,
            "host": host or None,
            "branch": branch or None,
            "goal_contains": goal_contains or None,
        },
        # on_machine keeps a shared triggers.json honest: the same file can be
        # synced to every box while each rule only fires on the one that owns it.
        "on_machine": on_machine or None,
        "run": run,
        "background": bool(background),
        "timeout": int(timeout),
    }
    triggers = [t for t in load_triggers() if t.get("id") != trigger_id]
    triggers.append(trigger)
    save_triggers(triggers)
    return trigger


def remove_trigger(trigger_id: str) -> bool:
    triggers = load_triggers()
    remaining = [t for t in triggers if t.get("id") != trigger_id]
    if len(remaining) == len(triggers):
        return False
    save_triggers(remaining)
    return True


def set_trigger_enabled(trigger_id: str, enabled: bool) -> bool:
    triggers = load_triggers()
    found = False
    for trigger in triggers:
        if trigger.get("id") == trigger_id:
            trigger["enabled"] = enabled
            found = True
    if found:
        save_triggers(triggers)
    return found


def matches(trigger: dict, event: str, data: dict) -> bool:
    """Decide whether one rule applies to one handoff event."""
    if not trigger.get("enabled", True):
        return False
    if event not in [e.lower() for e in trigger.get("events") or []]:
        return False

    on_machine = trigger.get("on_machine")
    if on_machine and on_machine not in {machine.host_label(), machine.machine_id()}:
        return False

    match = trigger.get("match") or {}
    origin = (match.get("origin") or "any").lower()
    if origin != "any" and origin != machine.record_origin(data):
        return False

    wanted_agent = match.get("agent")
    if wanted_agent and (data.get("agent") or "").lower() != wanted_agent.lower():
        return False

    wanted_host = match.get("host")
    if wanted_host:
        record_host = machine.record_machine(data)
        if wanted_host not in {
            record_host.get("host"),
            record_host.get("machine_id"),
        }:
            return False

    wanted_branch = match.get("branch")
    if wanted_branch and (data.get("git") or {}).get("branch") != wanted_branch:
        return False

    needle = match.get("goal_contains")
    if needle and needle.lower() not in (data.get("goal") or "").lower():  # noqa: SIM103 - one guard clause per filter reads better than a negated return
        return False

    return True


def build_env(event: str, data: dict, path: Path) -> dict[str, str]:
    """The contract a trigger command sees.

    Everything a remote-work script needs (which handoff, from which box, on
    which branch) arrives as environment variables so the command itself stays
    a plain shell one-liner.
    """
    record_host = machine.record_machine(data)
    env = dict(os.environ)
    env.update({
        "NOUGEN_HANDOFF_EVENT": event,
        "NOUGEN_HANDOFF_ID": str(data.get("handoff_id") or path.stem),
        "NOUGEN_HANDOFF_PATH": str(path),
        "NOUGEN_HANDOFF_MD_PATH": str(path.with_suffix(".md")),
        "NOUGEN_HANDOFF_AGENT": str(data.get("agent") or "generic"),
        "NOUGEN_HANDOFF_STATUS": str(data.get("status") or "open"),
        "NOUGEN_HANDOFF_GOAL": str(data.get("goal") or ""),
        "NOUGEN_HANDOFF_BRANCH": str((data.get("git") or {}).get("branch") or "unknown"),
        "NOUGEN_HANDOFF_ORIGIN": machine.record_origin(data),
        "NOUGEN_HANDOFF_HOST": str(record_host.get("host") or "unknown"),
        "NOUGEN_HANDOFF_MACHINE_ID": str(record_host.get("machine_id") or "unknown"),
        "NOUGEN_LOCAL_HOST": machine.host_label(),
        "NOUGEN_LOCAL_MACHINE_ID": machine.machine_id(),
    })
    return env


def _tail(text: str | None) -> str:
    if not text:
        return ""
    return text[-_OUTPUT_TAIL:]


def _execute(trigger: dict, event: str, data: dict, path: Path, mode: str) -> dict:
    """Run one trigger. Never raises — a broken rule must not lose a handoff."""
    started = datetime.now().isoformat()  # noqa: DTZ005 - matches the naive stamps on handoff records
    run_record = {
        "trigger_id": trigger.get("id"),
        "handoff_id": data.get("handoff_id") or path.stem,
        "event": event,
        "command": trigger.get("run"),
        "timestamp": started,
        "host": machine.host_label(),
        "machine_id": machine.machine_id(),
        "origin": machine.record_origin(data),
        "status": "matched",
        "exit_code": None,
        "stdout": "",
        "stderr": "",
    }
    if mode == "dry":
        run_record["status"] = "dry-run"
        return run_record

    cwd = trigger.get("cwd") or str(_handoff_module().PROJECT_ROOT)
    env = build_env(event, data, path)
    run_cmd = trigger["run"]
    if os.name == "nt":
        import re
        def repl(match):
            var_name = match.group(1) or match.group(2)
            return env.get(var_name, match.group(0))
        run_cmd = re.sub(r'\$\{([A-Za-z0-9_]+)\}|\$([A-Za-z0-9_]+)', repl, run_cmd)
        # Strip quotes around echoed strings because cmd.exe echo prints quotes literally
        run_cmd = re.sub(r'\b(echo)\s+"([^"]*)"', r'\1 \2', run_cmd, flags=re.IGNORECASE)

    try:
        if trigger.get("background"):
            subprocess.Popen(
                run_cmd,
                shell=True,
                cwd=cwd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            run_record["status"] = "background"
        else:
            completed = subprocess.run(
                run_cmd,
                shell=True,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True, encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=int(trigger.get("timeout") or DEFAULT_TIMEOUT),
                check=False,
            )
            run_record["exit_code"] = completed.returncode
            run_record["stdout"] = _tail(completed.stdout)
            run_record["stderr"] = _tail(completed.stderr)
            run_record["status"] = "ok" if completed.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        run_record["status"] = "timeout"
    except Exception as exc:  # noqa: BLE001 - a trigger may fail any way at all; the handoff must survive it
        run_record["status"] = "error"
        run_record["stderr"] = str(exc)[-_OUTPUT_TAIL:]
    return run_record


def fire(event: str, data: dict, path: Path) -> list[dict]:
    """Evaluate every rule against one handoff event and run the matches."""
    mode = trigger_mode()
    if mode == "off":
        return []
    results: list[dict] = []
    for trigger in load_triggers():
        try:
            if not matches(trigger, event, data):
                continue
        except Exception:  # noqa: BLE001, S112 - one malformed rule must not stop the others
            continue
        record = _execute(trigger, event, data, path, mode)
        results.append(record)
        _handoff_module()._record_trigger_run(record)
    return results


def recent_runs(limit: int = 20, trigger_id: str | None = None) -> list[dict]:
    return _handoff_module().get_trigger_runs(limit=limit, trigger_id=trigger_id)

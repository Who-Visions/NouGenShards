"""SessionStart hook: register this Claude Code session's messaging endpoint so
NouGenMsg can deliver into it mid-turn.

Claude Code exports CLAUDE_CODE_MESSAGING_SOCKET and CLAUDE_CODE_MESSAGING_TOKEN
to its own children only; an outside process (NouGenMsg's receive path, a
fleet daemon) cannot address the session without this record. The registry
is a per-user JSON file (env NOUGEN_CC_SESSIONS, default ~/.nougen/cc_sessions.json),
ACL-locked to the current user on first write. Dead entries are pruned by the
deliverer when the pipe no longer opens. Emits nothing to the hook output.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path


def registry_path() -> Path:
    raw = os.environ.get("NOUGEN_CC_SESSIONS", "").strip()
    return Path(raw) if raw else Path.home() / ".nougen" / "cc_sessions.json"


def _lock_to_user(path: Path) -> None:
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if not user:
        return
    try:
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(F)"],
                       capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def register(event: dict) -> dict | None:
    sock = os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET", "").strip()
    tok = os.environ.get("CLAUDE_CODE_MESSAGING_TOKEN", "").strip()
    if not sock or not tok:
        return None
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.exists()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        data = {}
    sessions = data.get("sessions") if isinstance(data.get("sessions"), dict) else {}
    entry = {
        "socket": sock, "token": tok,
        "session_id": str(event.get("session_id") or ""),
        "cwd": str(event.get("cwd") or os.getcwd()),
        "machine": platform.node(), "pid": os.getppid(),
        "registered_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": os.environ.get("NOUGEN_AGENT", "claude-cli"),
    }
    sessions[sock] = entry
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"sessions": sessions, "updated_utc": entry["registered_utc"]}, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    if fresh:
        _lock_to_user(path)
    return entry


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (TypeError, ValueError):
        event = {}
    try:
        register(event)
    except Exception:  # pylint: disable=broad-except
        pass  # a registry failure must never block a session start
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

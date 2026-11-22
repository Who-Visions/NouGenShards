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


def _update(path: str, change) -> None:
    """Locked read-modify-write. Uses nougen_shards.cc_registry when importable;
    this hook also runs standalone from ~/.claude/hooks, so it carries a copy."""
    try:
        from nougen_shards import cc_registry
        cc_registry.update(path, change)
        return
    except ImportError:
        pass
    import secrets
    lock = os.open(path + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        for _ in range(250):
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                time.sleep(0.02)
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except OSError:
            raw = ""
        data: dict = {}
        try:
            data = json.loads(raw) if raw.strip() else {}
        except ValueError:  # salvage every object rather than wipe the registry
            dec, i = json.JSONDecoder(), 0
            while (j := raw.find("{", i)) >= 0:
                try:
                    obj, i = dec.raw_decode(raw, j)
                except ValueError:
                    i = j + 1
                    continue
                if isinstance(obj, dict):
                    nested = obj.pop("sessions", None)
                    data.update(obj)
                    if isinstance(nested, dict):
                        data.setdefault("sessions", {}).update(nested)
        if not isinstance(data, dict):
            data = {}
        change(data)
        tmp = f"{path}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        Path(tmp).write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        os.close(lock)


def register(event: dict) -> dict | None:
    sock = os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET", "").strip()
    tok = os.environ.get("CLAUDE_CODE_MESSAGING_TOKEN", "").strip()
    if not sock or not tok:
        return None
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.exists()
    entry = {
        "socket": sock, "token": tok,
        "session_id": str(event.get("session_id") or ""),
        "cwd": str(event.get("cwd") or os.getcwd()),
        "machine": platform.node(), "pid": os.getppid(),
        "registered_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": os.environ.get("NOUGEN_AGENT", "claude-cli"),
    }

    def change(data: dict) -> None:
        if not isinstance(data.get("sessions"), dict):
            data["sessions"] = {}
        data["sessions"][sock] = entry
        data["updated_utc"] = entry["registered_utc"]

    _update(str(path), change)
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

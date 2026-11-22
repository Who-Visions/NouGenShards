"""Read and write the Claude Code session registry (cc_sessions.json) safely.

Several writers touch this file at once: each new session's SessionStart hook,
and the deliverer when it prunes a dead socket. With a shared ``.tmp`` name and
no lock, two writers interleave and leave two JSON documents back to back
("Extra data"), and every reader then saw an empty registry, so every Claude
delivery said registered=0 while live sockets sat there.

- ``read``: parse, and on a parse error salvage every JSON object in the file
  instead of treating it as empty. Returns (registry, corrupt).
- ``update``: lock, re-read (salvaging), apply a change, write a uniquely named
  temp file, ``os.replace``. The next write repairs a corrupt file.

Standard library only, POSIX and Windows.
"""
from __future__ import annotations

import contextlib
import json
import os
import secrets
import time
from typing import Any, Callable, Dict, Iterator, Tuple


def _merge(into: Dict[str, Any], obj: Dict[str, Any]) -> None:
    for key, val in obj.items():
        if key == "sessions" and isinstance(val, dict):
            into.setdefault("sessions", {}).update(val)
        else:
            into[key] = val


def parse(raw: str) -> Tuple[Dict[str, Any], bool]:
    try:
        data = json.loads(raw) if raw.strip() else {}
        return (data, False) if isinstance(data, dict) else ({}, True)
    except ValueError:
        pass
    dec, merged, i = json.JSONDecoder(), {}, 0
    while True:
        j = raw.find("{", i)
        if j < 0:
            break
        try:
            obj, end = dec.raw_decode(raw, j)
        except ValueError:
            i = j + 1
            continue
        if isinstance(obj, dict):
            _merge(merged, obj)
        i = end
    return merged, True


def read(path: str) -> Tuple[Dict[str, Any], bool]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return parse(f.read())
    except OSError:
        return {}, False


@contextlib.contextmanager
def _locked(path: str, timeout_s: float = 5.0) -> Iterator[None]:
    lock_path = path + ".lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.02)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                os.lseek(fd, 0, 0)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)


def update(path: str, change: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
    """Apply ``change`` to the registry under a lock and write it atomically."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with _locked(path):
        data, _ = read(path)
        change(data)
        tmp = f"{path}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, path)
    return data

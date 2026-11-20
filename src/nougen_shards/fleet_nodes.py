"""Fleet topology resolved at runtime, never hardcoded.

A stranger's machine has no fleet. Node names come from ``NOUGEN_PEER_NODES``
(comma-separated, default empty) and the local node from the hostname, so a
clean install reports zero expected peers instead of phantom ones.
"""
from __future__ import annotations

import os
import socket


def fleet_nodes() -> tuple[str, ...]:
    raw = os.environ.get("NOUGEN_PEER_NODES", "")
    return tuple(n.strip().lower() for n in raw.split(",") if n.strip())


# Hostnames that name no machine. A phone, a container or a fresh VM often
# reports one of these, so every such device would stamp the same name.
_GENERIC_HOSTS = frozenset({"", "localhost", "localhost.localdomain", "android", "ubuntu",
                            "debian", "raspberrypi", "iphone", "ipad", "unknown", "host"})


def _slug(value: str) -> str:
    """Lowercase, [a-z0-9-] only, so a name is safe in a path, a pipe and a header."""
    import re
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")[:48]


def _machine_id_path():
    from pathlib import Path
    root = os.environ.get("NOUGEN_ROOT", "").strip()
    return (Path(root).expanduser() if root else Path.home() / ".nougen") / "machine_id"


_OS_ID_FILES = ("/etc/machine-id", "/var/lib/dbus/machine-id")


def _windows_machine_guid() -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            return str(winreg.QueryValueEx(key, "MachineGuid")[0]).strip()
    except (OSError, ImportError):
        return ""


def _stable_seed() -> str:
    """Something that names this install and does not change between runs.

    The OS machine id first (Linux /etc/machine-id, Windows MachineGuid), then a
    real hardware address. Returns "" when neither exists: uuid.getnode()
    invents a random value, flagged by the multicast bit, when it cannot read a
    MAC, and that must never be mistaken for an identity.
    """
    for p in _OS_ID_FILES:
        try:
            with open(p, encoding="utf-8") as f:
                value = f.read().strip()
            if value:
                return "os:" + value
        except OSError:
            pass
    value = _windows_machine_guid()
    if value:
        return "os:" + value
    import uuid
    mac = uuid.getnode()
    return "" if (mac >> 40) & 1 else "mac:%012x" % mac


def _weak_seed() -> str:
    """Last resort when nothing is stable and nothing can be written: stable, not unique."""
    import platform
    try:
        import getpass
        user = getpass.getuser()
    except Exception:
        user = ""
    return "weak:%s|%s|%s" % (platform.node(), platform.system(), user)


def _read_id(path) -> str:
    try:
        return _slug(path.read_text(encoding="utf-8"))
    except OSError:
        return ""


def device_id() -> str:
    """A stable id for a device whose hostname says nothing: ``device-<8 hex>``.

    Read from the persisted file when there is one. Otherwise it is derived
    from the OS machine id or a real hardware address, or, when neither
    exists, drawn at random, and published with an exclusive create so that
    concurrent first callers all end up with the winner's value. If the file
    cannot be written (read-only home, sandbox) the id comes from the stable
    seed or, last, from the hostname, platform and user: the same on every
    run, never random.
    """
    import hashlib
    import time
    import uuid
    path = _machine_id_path()
    stored = _read_id(path)
    if stored:
        return stored
    seed = _stable_seed()
    fallback = "device-" + hashlib.sha256((seed or _weak_seed()).encode()).hexdigest()[:8]
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        candidate = ("device-" + hashlib.sha256(seed.encode()).hexdigest()[:8]) if seed \
            else "device-" + uuid.uuid4().hex[:8]
        # Write the whole id to a private temp file, then publish it with an
        # atomic hard link: the id file either does not exist or is complete,
        # never half-written, so a loser of the race always reads the winner's
        # full value and no reader has to wait or guess.
        # A random suffix, not pid + clock: threads of one process share the pid and
        # the Windows clock is coarse, so those names collide and two callers would
        # write the same temp file.
        tmp = path.with_name("%s.%s.tmp" % (path.name, uuid.uuid4().hex))
        tmp.write_text(candidate + "\n", encoding="utf-8")
        try:
            os.link(str(tmp), str(path))
            return candidate
        except (FileExistsError, PermissionError):
            # Someone else published first. On Windows a read can fail for a moment
            # while the winner's temp file is being unlinked, so an unreadable file
            # is retried, never mistaken for a corrupt one.
            for _ in range(25):
                try:
                    stored = _slug(path.read_text(encoding="utf-8"))
                except OSError:
                    stored = None
                if stored:
                    return stored
                if stored == "":
                    # Exists and is empty. Publishing is atomic, so a run of this code
                    # cannot leave one; someone truncated it. Overwriting would race
                    # other callers into different ids, so leave it alone and answer
                    # with the stable fallback.
                    return fallback
                time.sleep(0.02)
            return fallback
    except OSError:
        # Read-only home, full disk, or no hard-link support: a stable id that is
        # not persisted, so it is the same on every run.
        return fallback
    finally:
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass


def local_node() -> str:
    """This machine's node name, discovered at runtime on whatever device this is.

    ``NOUGEN_NODE_NAME`` (repo convention) wins; else the hostname, slugged
    so it is safe to stamp into a path or header; else, when the hostname
    names no machine (``localhost``, ``android``, empty), a persisted
    ``device-<hex>`` id. Never empty, never a fleet name baked into code.
    """
    named = _slug(os.environ.get("NOUGEN_NODE_NAME", ""))
    if named:
        return named
    try:
        host = socket.gethostname().split(".")[0]
    except OSError:
        host = ""
    slug = _slug(host)
    if slug and slug not in _GENERIC_HOSTS:
        return slug
    return device_id()

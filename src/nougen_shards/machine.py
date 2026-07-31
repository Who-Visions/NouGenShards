"""Machine identity for cross-computer coordination.

Handoffs move between agents *and* between computers. The moment a second box
joins the fleet, "CLAUDE-CLI left this note" stops being enough information:
the reader needs to know whether the branch, the uncommitted changes and the
paths in that note exist on the machine they are sitting at. Every handoff
record therefore carries an identity block describing the host that wrote it.

Identity is resolved from the environment first so a machine can be given a
stable, human name (``NOUGEN_MACHINE=who-mac-mini``) instead of whatever
mDNS hostname it happens to advertise today.
"""

import getpass
import hashlib
import os
import platform
import socket
import sys
from functools import lru_cache
from typing import Dict, Optional


def _env(name: str) -> Optional[str]:
    value = (os.environ.get(name) or "").strip()
    return value or None


def _private_mode() -> bool:
    """True when this machine should omit user/path details from records.

    Handoff notes are gitignored, but they get pasted into issues and synced to
    other boxes. NOUGEN_MACHINE_PRIVATE=1 keeps the identity block to the parts
    needed for routing (host, platform) and drops the local account name and
    working directory.
    """
    return (os.environ.get("NOUGEN_MACHINE_PRIVATE") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }


@lru_cache(maxsize=1)
def hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return "unknown-host"


@lru_cache(maxsize=1)
def host_label() -> str:
    """The short, human-facing name for this computer.

    ``NOUGEN_MACHINE`` wins so a machine keeps one identity across shells and
    OS reinstalls; otherwise the hostname with the noisy mDNS suffix removed.
    """
    explicit = _env("NOUGEN_MACHINE")
    if explicit:
        return explicit
    name = hostname()
    for suffix in (".local", ".lan", ".home", ".localdomain"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.split(".")[0] or "unknown-host"


@lru_cache(maxsize=1)
def machine_id() -> str:
    """Stable, non-reversible id for this computer.

    Derived from hostname + OS + architecture rather than a MAC address: the
    MAC is randomized on some platforms (which would make the id change between
    runs) and hashing it buys no extra privacy. Twelve hex characters is enough
    to distinguish the handful of boxes in a fleet without being guessable
    back into the hostname.
    """
    explicit = _env("NOUGEN_MACHINE_ID")
    if explicit:
        return explicit
    raw = f"{hostname()}|{platform.system()}|{platform.machine()}"
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:12]


def machine_identity(repo_root: Optional[object] = None) -> Dict[str, str]:
    """Return the identity block stamped onto handoff records and checkpoints."""
    identity: Dict[str, str] = {
        "machine_id": machine_id(),
        "host": host_label(),
        "hostname": hostname(),
        "platform": sys.platform,
        "os": f"{platform.system()} {platform.release()}".strip(),
        "arch": platform.machine(),
        "python": platform.python_version(),
    }
    if not _private_mode():
        try:
            identity["user"] = getpass.getuser()
        except Exception:
            pass
        if repo_root is not None:
            identity["repo_root"] = str(repo_root)
    return identity


def machine_stamp() -> Dict[str, str]:
    """Compact stamp for per-event records (checkpoints, acks, trigger runs)."""
    return {"host": host_label(), "machine_id": machine_id()}


def record_machine(data: Optional[Dict]) -> Dict[str, str]:
    """Extract the identity block from a handoff record, tolerating old records.

    Handoffs written before machine stamping exist on disk and must keep
    reading cleanly, so a missing block degrades to an explicit 'unknown'
    rather than raising.
    """
    machine = (data or {}).get("machine")
    if isinstance(machine, dict):
        return machine
    # Other tooling in the fleet stamps the machine as a bare host string.
    # That is unambiguous — take it as the host rather than discarding a name
    # the writer clearly meant, and leave the id unknown so identity
    # comparisons stay conservative.
    if isinstance(machine, str) and machine.strip():
        return {"host": machine.strip(), "machine_id": "unknown"}
    return {"host": "unknown", "machine_id": "unknown"}


def is_local_record(data: Optional[Dict]) -> bool:
    """True when the record was written by the computer running right now.

    Both halves of the identity have to agree. The id alone is not enough: two
    boxes restored from the same disk image can hash identically, and a machine
    given a new name via NOUGEN_MACHINE is, for coordination purposes, a
    different participant. Records predating machine stamping have nothing to
    compare and count as local — they were written before the fleet had more
    than one box in it.
    """
    machine = record_machine(data)
    recorded_id = machine.get("machine_id")
    recorded_host = machine.get("host")
    if not recorded_id or recorded_id == "unknown":
        # No id to compare. A named host is still an answer — records from
        # tooling that stamps only the name must not pass as locally written,
        # or remote-origin triggers would never fire for them.
        if recorded_host and recorded_host != "unknown":
            return recorded_host == host_label()
        return True
    if recorded_id != machine_id():
        return False
    recorded_host = machine.get("host")
    if recorded_host and recorded_host != "unknown":
        return recorded_host == host_label()
    return True


def record_origin(data: Optional[Dict]) -> str:
    """'local' or 'remote', the axis triggers match on."""
    return "local" if is_local_record(data) else "remote"

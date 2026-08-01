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


def _env(name: str) -> str | None:
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


def machine_identity(repo_root: object | None = None) -> dict[str, str]:
    """Return the identity block stamped onto handoff records and checkpoints."""
    identity: dict[str, str] = {
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
        except (OSError, KeyError):
            # No passwd entry or no controlling terminal: the name is a nicety,
            # not something worth failing a handoff over.
            pass
        if repo_root is not None:
            identity["repo_root"] = str(repo_root)
    return identity


def machine_stamp() -> dict[str, str]:
    """Compact stamp for per-event records (checkpoints, acks, trigger runs)."""
    return {"host": host_label(), "machine_id": machine_id()}


def record_machine(data: dict | None) -> dict[str, str]:
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


def is_local_record(data: dict | None) -> bool:
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
    # The id settles it. A differing label on a matching id means one computer
    # answering to two names, which is an aliasing problem — not evidence the
    # record came from somewhere else.
    #
    # The label used to override the id here, and the result was a record
    # written on this Mac sixty seconds earlier being announced as "REMOTE —
    # written elsewhere, you are on KushBoyGroups-Mac-mini". It was written on
    # KushBoyGroups-Mac-mini. NOUGEN_MACHINE=phoebus had been set in the writing
    # shell and not the reading one, so two names for one box read as two boxes.
    #
    # That mattered beyond the display: remote-origin triggers fired for this
    # machine's own records, and an operator reading "written elsewhere" has no
    # reason to doubt it. Aliasing is still worth surfacing — see
    # record_alias_warning — but it is a warning, not a location.
    return recorded_id == machine_id()


def record_alias_warning(data: dict | None) -> str | None:
    """Flag one computer answering to two names. None when there is nothing odd.

    Fires when a record's machine_id matches this box but its host label does
    not: same hardware, different name. `who-mac-mini`, `phoebus` and
    `kushboygroups-mac-mini-local` have all meant this Mac, and a fleet that
    treats them as three participants counts one box three times.
    """
    machine = record_machine(data)
    recorded_id = machine.get("machine_id")
    recorded_host = machine.get("host")
    if not recorded_id or recorded_id == "unknown":
        return None
    if recorded_id != machine_id():
        return None
    if not recorded_host or recorded_host == "unknown":
        return None
    if recorded_host == host_label():
        return None
    return (
        f"written on this computer under the name '{recorded_host}', "
        f"which is currently answering to '{host_label()}'. "
        f"Set NOUGEN_MACHINE={recorded_host} to keep one identity."
    )


def record_origin(data: dict | None) -> str:
    """'local' or 'remote', the axis triggers match on."""
    return "local" if is_local_record(data) else "remote"

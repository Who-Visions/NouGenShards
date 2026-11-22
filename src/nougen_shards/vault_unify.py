"""One vault per person: find and repair a node that opened the wrong folder.

The failure this exists for: someone installs NouGenShards locally and builds
up a vault in the default folder (``~/.nougen/shards``). Later they join and
the join setup starts a server node whose ``NOUGEN_VAULT_DIR`` is a different,
freshly created folder inside the account directory. Their assistants connect
to the node and see an almost empty vault, while every shard they ever wrote
sits untouched in the default folder.

The repair is a pointer, not a move. ``apply`` writes a small ``VAULT_POINTER``
file into the node's vault folder naming the populated folder; the resolver in
``core`` follows it, so the local tools and the node read and write one vault.
Nothing is copied over anything, nothing is deleted, and removing the pointer
file undoes it. Both vaults' database files are backed up first.

This module is stdlib-only and must not import ``core`` at import time: the
resolver in ``core`` imports it.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

POINTER_NAME = "VAULT_POINTER"
DB_GLOB = "nougen_shards_*.db"
DB_SIDECARS = ("-wal", "-shm")

ENV_LOCAL_VAULT = "NOUGEN_LOCAL_DEFAULT_VAULT"
ENV_STRAY_MAX = "NOUGEN_VAULT_UNIFY_STRAY_MAX"
ENV_BACKUP_ROOT = "NOUGEN_VAULT_UNIFY_BACKUP_DIR"
ENV_MISMATCH = "NOUGEN_VAULT_MISMATCH"          # warn (default) | refuse | off
ENV_FREE_HEADROOM = "NOUGEN_VAULT_UNIFY_FREE_HEADROOM_MB"

# A node vault holding this many shards or fewer counts as "not yet used":
# setup itself can write a handful (a welcome note, a connection test).
_FALLBACK_STRAY_MAX = 5
_FALLBACK_FREE_HEADROOM_MB = 256
ENV_BACKUP_NAME_TRIES = "NOUGEN_VAULT_UNIFY_BACKUP_NAME_TRIES"
_FALLBACK_BACKUP_NAME_TRIES = 100

SAME = "same_path"
POINTED = "pointed"
LOCAL_EMPTY = "local_empty"
ADOPTABLE = "adoptable"
BOTH_POPULATED = "both_populated"


class VaultUnifyError(RuntimeError):
    """The repair cannot be made safely; the message says why."""


def _env_int(name: str, fallback: int) -> int:
    raw = os.environ.get(name, "").strip()
    if raw.isdigit():
        return int(raw)
    if raw:
        log.warning("%s=%r is not a non-negative integer; using fallback %s", name, raw, fallback)
    return fallback


def local_default_vault() -> Path:
    """Where a plain local install keeps its vault."""
    override = os.environ.get(ENV_LOCAL_VAULT, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".nougen" / "shards").resolve()


def read_pointer(vault_dir: Path) -> Optional[Path]:
    """The folder a vault points at, or None.

    A pointer is honoured only when it names an existing directory other than
    the vault itself, and only one hop: a target that itself holds a pointer is
    used as it is, so a loop cannot form.
    """
    pointer = Path(vault_dir) / POINTER_NAME
    try:
        raw = pointer.read_text(encoding="utf-8").lstrip("﻿").strip()
    except (OSError, UnicodeDecodeError):
        return None
    if not raw:
        return None
    target_text = raw
    if raw.startswith("{"):
        try:
            target_text = str(json.loads(raw).get("target") or "")
        except (ValueError, AttributeError):
            log.warning("ignoring unreadable %s in %s", POINTER_NAME, vault_dir)
            return None
    if not target_text:
        return None
    target = Path(target_text).expanduser()
    try:
        target = target.resolve()
        here = Path(vault_dir).resolve()
    except OSError:
        return None
    if target == here or not target.is_dir():
        log.warning("ignoring %s in %s: target %s is missing or is the vault itself",
                    POINTER_NAME, vault_dir, target)
        return None
    return target


def resolve(vault_dir: Path) -> Path:
    """The vault a folder really stands for (follows one pointer).

    ``read_pointer`` returns a path that is already user-expanded and resolved.
    """
    return read_pointer(vault_dir) or Path(vault_dir)


ENV_VAULT = "NOUGEN_VAULT_DIR"
ENV_CONFIGURED = "NOUGEN_VAULT_DIR_CONFIGURED"


def configured_vault() -> str:
    """The vault folder this process was started with, before any pointer was
    followed. Empty when none was set."""
    return (os.environ.get(ENV_CONFIGURED, "") or os.environ.get(ENV_VAULT, "")).strip()


def adopt_pointer_into_env() -> Optional[Path]:
    """Follow the pointer once for the whole process.

    Many modules read ``NOUGEN_VAULT_DIR`` straight from the environment instead
    of asking ``core``. If only ``core`` followed the pointer, those readers
    would keep opening the nearly empty node folder after a repair. So when the
    configured folder holds a pointer, the environment variable itself is
    repointed (the original is kept in ``NOUGEN_VAULT_DIR_CONFIGURED``), and
    every reader, and every child process, sees the one vault.

    Called from the package ``__init__``. Never raises.
    """
    try:
        raw = os.environ.get(ENV_VAULT, "").strip()
        if not raw:
            return None
        # A pointer has already been followed, by this process or by the parent
        # it inherited its environment from. Following another one here would
        # move a child process to a different vault than its parent.
        if os.environ.get(ENV_CONFIGURED, "").strip():
            return None
        target = read_pointer(Path(raw).expanduser())
        if target is None:
            return None
        os.environ.setdefault(ENV_CONFIGURED, raw)
        os.environ[ENV_VAULT] = str(target)
        log.warning("NouGen vault: %s points at %s; using that vault for this process", raw, target)
        return target
    except Exception as exc:  # pylint: disable=broad-except
        log.warning("vault pointer not applied: %s", exc)
        return None


def db_files(vault_dir: Path) -> List[Path]:
    try:
        return sorted(p for p in Path(vault_dir).glob(DB_GLOB) if p.is_file())
    except OSError:
        return []


def count_shards(vault_dir: Path) -> int:
    """Rows in the ``shards`` table across a vault's databases, read-only.

    A missing folder, a missing table or an unreadable file counts as zero for
    that file: this is used to decide whether a vault is in use, and must never
    create or modify one.
    """
    total = 0
    for db in db_files(vault_dir):
        try:
            conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
        except sqlite3.Error:
            continue
        try:
            total += int(conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0])
        except sqlite3.Error:
            pass
        finally:
            conn.close()
    return total


def inspect(node_vault: Path, local_vault: Optional[Path] = None) -> Dict[str, Any]:
    """Compare the node's vault folder with the local default one."""
    node_vault = Path(node_vault).expanduser()
    local_vault = Path(local_vault).expanduser() if local_vault else local_default_vault()
    stray_max = _env_int(ENV_STRAY_MAX, _FALLBACK_STRAY_MAX)
    report: Dict[str, Any] = {
        "node_vault": str(node_vault), "local_vault": str(local_vault),
        "stray_max": stray_max, "pointer": None,
    }
    try:
        same = node_vault.resolve() == local_vault.resolve()
    except OSError:
        same = False
    if same:
        report.update(state=SAME, node_count=count_shards(node_vault), local_count=None)
        return report
    pointer = read_pointer(node_vault)
    report["node_count"] = count_shards(node_vault)
    if pointer is not None:
        report.update(state=POINTED, pointer=str(pointer), local_count=count_shards(pointer))
        return report
    report["local_count"] = count_shards(local_vault)
    if report["local_count"] == 0:
        report["state"] = LOCAL_EMPTY
    elif report["node_count"] <= stray_max and report["local_count"] > report["node_count"]:
        report["state"] = ADOPTABLE
    else:
        report["state"] = BOTH_POPULATED
    return report


def describe(report: Dict[str, Any]) -> str:
    """One paragraph a person can act on."""
    state = report.get("state")
    node, local = report.get("node_vault"), report.get("local_vault")
    if state == SAME:
        return f"One vault: the node and the local install both use {node}."
    if state == POINTED:
        return (f"One vault: the node folder {node} points at {report.get('pointer')} "
                f"({report.get('local_count')} shards).")
    if state == LOCAL_EMPTY:
        return f"Nothing to repair: the local default vault {local} holds no shards; the node uses {node}."
    if state == ADOPTABLE:
        return (f"VAULT MISMATCH: the node is using {node} ({report.get('node_count')} shards) while "
                f"{report.get('local_count')} shards sit in the local vault {local}. "
                "Run `nougen vault-unify --apply` on this computer to point the node at the "
                "existing vault (both are backed up first; nothing is deleted).")
    return (f"VAULT MISMATCH: two vaults are both in use: the node's {node} "
            f"({report.get('node_count')} shards) and the local {local} "
            f"({report.get('local_count')} shards). This is not repaired automatically "
            "because neither can be chosen without losing sight of the other. "
            "Decide which one the node should use, then run "
            "`nougen vault-unify --apply --allow-populated-node`; the node's current "
            "shards stay in its folder and in the backup.")


def _vault_bytes(vault_dir: Path) -> int:
    total = 0
    for db in db_files(vault_dir):
        for path in [db] + [Path(str(db) + s) for s in DB_SIDECARS]:
            try:
                total += path.stat().st_size
            except OSError:
                pass
    return total


def default_backup_root() -> Path:
    override = os.environ.get(ENV_BACKUP_ROOT, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".nougen" / "backups"


def _copy_vault_dbs(vault_dir: Path, dest: Path) -> List[str]:
    """Copy a vault's databases into ``dest`` with SQLite's own backup, so a
    database that is open elsewhere is still copied in a consistent state."""
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for db in db_files(vault_dir):
        out = dest / db.name
        try:
            src = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=30)
            try:
                dst = sqlite3.connect(str(out))
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
        except sqlite3.Error:
            # Not a readable database: keep the bytes anyway.
            shutil.copy2(db, out)
        copied.append(db.name)
    return copied


def apply(node_vault: Path, local_vault: Optional[Path] = None, *,
          backup_root: Optional[Path] = None, allow_populated_node: bool = False,
          dry_run: bool = False) -> Dict[str, Any]:
    """Point the node's vault folder at the populated local vault.

    Safe to run twice: an already pointed or already identical vault is left
    alone. Refuses when both vaults are in use unless the caller says so, and
    refuses when there is not enough free disk for the backups.
    """
    report = inspect(node_vault, local_vault)
    state = report["state"]
    report["changed"] = False
    if state in (SAME, POINTED, LOCAL_EMPTY):
        report["action"] = "none"
        return report
    if state == BOTH_POPULATED and not allow_populated_node:
        raise VaultUnifyError(describe(report))

    node_dir, local_dir = Path(report["node_vault"]), Path(report["local_vault"])
    root = Path(backup_root) if backup_root else default_backup_root()
    need = _vault_bytes(node_dir) + _vault_bytes(local_dir)
    headroom = _env_int(ENV_FREE_HEADROOM, _FALLBACK_FREE_HEADROOM_MB) * 1024 * 1024
    probe = root
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    report.update(action="point", backup_bytes=need, free_bytes=free)
    if free < need + headroom:
        raise VaultUnifyError(
            f"not enough free disk to back up both vaults first: need {need} bytes plus "
            f"{headroom} headroom, {free} free under {probe}. Nothing was changed.")
    if dry_run:
        report["dry_run"] = True
        return report

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    # Each repair gets a folder of its own. Two repairs in the same second
    # used to share one and the second overwrote the first one's backups.
    root.mkdir(parents=True, exist_ok=True)
    backup_dir = None
    for attempt in range(_env_int(ENV_BACKUP_NAME_TRIES, _FALLBACK_BACKUP_NAME_TRIES)):
        candidate = root / (f"vault_unify_{stamp}" if attempt == 0 else f"vault_unify_{stamp}_{attempt}")
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        backup_dir = candidate
        break
    if backup_dir is None:
        raise VaultUnifyError(f"could not create a fresh backup folder under {root}. Nothing was changed.")
    copied = {
        "node": _copy_vault_dbs(node_dir, backup_dir / "node"),
        "local": _copy_vault_dbs(local_dir, backup_dir / "local"),
    }
    manifest = {
        "created_utc": stamp, "node_vault": str(node_dir), "local_vault": str(local_dir),
        "node_count": report["node_count"], "local_count": report["local_count"],
        "copied": copied, "undo": f"delete {node_dir / POINTER_NAME}",
    }
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    node_dir.mkdir(parents=True, exist_ok=True)
    pointer = node_dir / POINTER_NAME
    tmp = node_dir / (POINTER_NAME + ".tmp")
    tmp.write_text(json.dumps({"target": str(local_dir.resolve()), "created_utc": stamp,
                               "backup": str(backup_dir)}, indent=2), encoding="utf-8")
    os.replace(tmp, pointer)

    report.update(changed=True, pointer=str(local_dir.resolve()), backup_dir=str(backup_dir),
                  state=POINTED, resolved_count=count_shards(local_dir))
    return report


def startup_check(node_vault: Path) -> Optional[str]:
    """Called once when a node starts. Returns a message when the node's vault
    and the local vault disagree; raises when the operator asked for a refusal.

    The default is to warn, not to refuse: on a shared computer the local vault
    can belong to a different person than the node's account, and a node that
    refuses to start takes a working connection offline.
    """
    mode = os.environ.get(ENV_MISMATCH, "warn").strip().lower()
    if mode in ("off", "0", "false", "no"):
        return None
    try:
        report = inspect(node_vault)
    except Exception as exc:  # pylint: disable=broad-except
        log.warning("vault mismatch check skipped: %s", exc)
        return None
    if report["state"] not in (ADOPTABLE, BOTH_POPULATED):
        return None
    message = describe(report)
    if mode == "refuse":
        raise VaultUnifyError(message)
    log.warning(message)
    return message

"""Snapshot and verify the local NouGen shard vault without touching GPUs.

The snapshot is file-based for markdown/artifacts and uses SQLite's online
backup API for live shard databases, so a running node does not require a
shutdown.  ``--restore-check`` restores the database portion into a temporary
directory and runs ``PRAGMA integrity_check``; it never changes the live vault.

Environment resolution:
  NOUGEN_VAULT_DIR -> config.json vault_dir -> ~/.nougen/shards
  NOUGEN_BACKUP_DIR -> ~/.nougen/backups/shards
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path


def _home() -> Path:
    return Path(os.environ.get("NOUGEN_HOME", str(Path.home() / ".nougen"))).expanduser()


def resolve_vault() -> Path:
    value = os.environ.get("NOUGEN_VAULT_DIR", "").strip()
    if value:
        return Path(value).expanduser()
    cfg_path = Path(os.environ.get("NOUGEN_CONFIG", str(_home() / "config.json"))).expanduser()
    try:
        value = str(json.loads(cfg_path.read_text(encoding="utf-8")).get("vault_dir", "")).strip()
    except (OSError, ValueError, TypeError):
        value = ""
    return Path(value).expanduser() if value else _home() / "shards"


def resolve_backup_root() -> Path:
    value = os.environ.get("NOUGEN_BACKUP_DIR", "").strip()
    return Path(value).expanduser() if value else _home() / "backups" / "shards"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_snapshot(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_uri = f"file:{source.as_posix()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True, timeout=5) as src:
        with sqlite3.connect(destination) as dst:
            src.backup(dst)


def snapshot(vault: Path, backup_root: Path, db_only: bool = False,
             only: list[str] | None = None) -> Path:
    if not vault.is_dir():
        raise FileNotFoundError(f"vault directory missing: {vault}")
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    destination = backup_root / stamp
    destination.mkdir(parents=True, exist_ok=False)
    records = []
    warnings = []
    if only:
        sources = [vault / name for name in only]
    elif db_only:
        sources = sorted({
            source for pattern in ("*.db", "*.sqlite", "*.sqlite3")
            for source in vault.glob(pattern)
        })
    else:
        sources = vault.rglob("*")
    for source in sources:
        if not source.is_file():
            if only:
                warnings.append(f"missing source: {source.relative_to(vault)}")
            continue
        if source.name.endswith(("-wal", "-shm")) or source.name.endswith(".lock"):
            continue
        if db_only and source.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
            continue
        relative = source.relative_to(vault)
        target = destination / relative
        try:
            if source.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
                _sqlite_snapshot(source, target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            records.append({
                "path": relative.as_posix(),
                "bytes": target.stat().st_size,
                "sha256": _sha256(target),
            })
        except (OSError, sqlite3.Error) as exc:
            warnings.append(f"{relative}: {type(exc).__name__}: {exc}")
    manifest = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "vault": str(vault),
        "files": records,
        "warnings": warnings,
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def verify(backup: Path, restore_check: bool = False) -> dict:
    manifest_path = backup / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checked = 0
    mismatches = []
    dbs = []
    for record in manifest.get("files", []):
        path = backup / record["path"]
        if not path.is_file() or path.stat().st_size != record["bytes"]:
            mismatches.append(record["path"])
            continue
        if _sha256(path) != record["sha256"]:
            mismatches.append(record["path"])
        checked += 1
        if path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            dbs.append(path)

    integrity = []
    restore_dir = None
    if restore_check:
        restore_dir = Path(tempfile.mkdtemp(prefix="nougen-restore-check-"))
    try:
        for db in dbs:
            candidate = db
            if restore_dir is not None:
                candidate = restore_dir / db.relative_to(backup)
                candidate.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(db, candidate)
            with sqlite3.connect(candidate) as conn:
                result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            integrity.append({"path": str(db.relative_to(backup)), "result": result})
    finally:
        if restore_dir is not None:
            shutil.rmtree(restore_dir, ignore_errors=True)
    return {
        "backup": str(backup),
        "files_checked": checked,
        "mismatches": mismatches,
        "sqlite_integrity": integrity,
        "warnings": manifest.get("warnings", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("snapshot", "verify"))
    parser.add_argument("--backup", type=Path, help="snapshot directory for verify")
    parser.add_argument("--restore-check", action="store_true")
    parser.add_argument("--db-only", action="store_true",
                        help="snapshot SQLite shard stores only (fast drill)")
    parser.add_argument("--only", action="append", default=[],
                        help="snapshot one relative file; repeat to resume in chunks")
    args = parser.parse_args()
    if args.command == "snapshot":
        path = snapshot(resolve_vault(), resolve_backup_root(),
                        db_only=args.db_only, only=args.only)
        result = verify(path, restore_check=True)
        result["snapshot"] = str(path)
    else:
        path = args.backup
        if path is None:
            candidates = sorted(resolve_backup_root().glob("*/manifest.json"))
            if not candidates:
                raise FileNotFoundError("no shard snapshots found")
            path = candidates[-1].parent
        result = verify(path, restore_check=args.restore_check)
    print(json.dumps(result, sort_keys=True))
    return 0 if not result["mismatches"] and all(
        item["result"] == "ok" for item in result["sqlite_integrity"]
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())

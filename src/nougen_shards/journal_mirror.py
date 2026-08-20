"""Mirror the Codex memory journal into an FTS5-searchable shard node.

Why this exists
---------------
``write_memory`` (search_service.SearchService.write_memory) appends records to
``vault/codex_memory_journal.jsonl``. Only ``recall_context`` reads that file, so
everything written through ``write_memory`` is invisible to ``shard_search`` /
``global_search`` / ``search_fleet`` -- which walk the fleet registry map instead.

This module mirrors the journal into a dedicated SQLite node that carries the
canonical ``shards`` schema plus an external-content FTS5 index, and (opt-in)
registers that node in the fleet map so the read-only search tools reach it.

Design constraints honoured
---------------------------
* No new MCP tools -- the frozen Sol-Ai v2.2 surface stays at 13.
* Lock order is VAULT_DIR before LOCK_FILE.
* Dry-run is the default; writing requires an explicit ``--write``.
* Idempotent: keyed on ``sha256(created_utc \\x00 title)`` so re-runs never
  duplicate. Content drift on an existing key updates in place.
* Privacy tagging is preserved: journal entries tagged ``do-not-export`` /
  ``private`` / ``not-for-handoff`` land with ``sensitivity='private'`` and can
  optionally be encrypted at rest via :mod:`nougen_shards.private_vault`.

Every path, node name and policy resolves env -> config -> probe, with a logged
constant only as the last resort.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import logging
import os
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Optional

log = logging.getLogger("nougen_shards.journal_mirror")

# --------------------------------------------------------------------------
# Dynamic configuration (env -> probe -> logged fallback)
# --------------------------------------------------------------------------

#: Last-resort root when env and probe both fail. Derived from the running
#: user's home rather than a literal path -- an absolute path with one
#: operator's account name in it is wrong on every other machine, and leaks
#: a home directory into a public repo.
_FALLBACK_WATCHTOWER_ROOT = str(Path.home() / "Watchtower")

#: Journal tags that force a record to be treated as non-public.
_PRIVATE_TAGS = {"do-not-export", "do_not_export", "private", "not-for-handoff", "personal"}
_SECRET_TAGS = {"secret", "credential", "credentials"}

#: Tables published to the fleet map, in the order ``global_search`` walks them.
_PUBLISHED_TABLES = ("shards", "shards_fts")

_EVENT_TYPE = "JOURNAL"


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name, "").strip()
    return value or default


def resolve_watchtower_root() -> Path:
    """Watchtower root: env, else the ancestor that owns ``vault/``, else constant."""
    explicit = _env("WATCHTOWER_ROOT")
    if explicit:
        return Path(explicit)

    # Probe upward from this file: .../Watchtower/NouGen/<ws>/src/nougen_shards
    for parent in Path(__file__).resolve().parents:
        if (parent / "vault" / "codex_memory_journal.jsonl").exists():
            return parent
        if (parent / "NouGenAi_fleet_map.json").exists() and (parent / "vault").is_dir():
            return parent

    log.warning("WATCHTOWER_ROOT unresolved; falling back to %s", _FALLBACK_WATCHTOWER_ROOT)
    return Path(_FALLBACK_WATCHTOWER_ROOT)


@dataclass
class MirrorConfig:
    """Resolved locations and policy for one mirror run."""

    watchtower_root: Path
    vault_dir: Path
    journal_path: Path
    mirror_db: Path
    fleet_map: Path
    lock_file: Path
    node_name: str
    private_policy: str = "tag"  # tag | skip | encrypt
    domain_key: str = "codex-journal"

    @classmethod
    def resolve(cls, **overrides) -> "MirrorConfig":
        root = Path(overrides.pop("watchtower_root", None) or resolve_watchtower_root())
        try:
            from . import core
            contextual_vault = core.active_vault_dir() if core.vault_context_is_set() else None
        except Exception:
            contextual_vault = None
        vault = Path(contextual_vault or _env("NOUGEN_VAULT_DIR") or (root / "vault"))
        cfg = cls(
            watchtower_root=root,
            vault_dir=vault,
            journal_path=Path(_env("NOUGEN_CODEX_JOURNAL") or (vault / "codex_memory_journal.jsonl")),
            mirror_db=Path(_env("NOUGEN_JOURNAL_MIRROR_DB") or (vault / "codex_journal_shards.db")),
            fleet_map=Path(_env("NOUGEN_FLEET_MAP") or (root / "NouGenAi_fleet_map.json")),
            lock_file=Path(
                _env("NOUGEN_JOURNAL_MIRROR_LOCK")
                or (Path(_env("NOUGENAI_MCP_LOCK_DIR") or (Path.home() / ".codex" / "memories")) / "journal_mirror.lock")
            ),
            node_name=(_env("NOUGEN_JOURNAL_NODE") or "CODEX_JOURNAL").upper(),
            private_policy=(_env("NOUGEN_JOURNAL_PRIVATE_POLICY") or "tag").lower(),
            domain_key=_env("NOUGEN_JOURNAL_DOMAIN_KEY") or "codex-journal",
        )
        for key, value in overrides.items():
            if value is not None:
                setattr(cfg, key, value)
        return cfg


# --------------------------------------------------------------------------
# Locking -- VAULT_DIR is acquired before LOCK_FILE (frozen baseline order)
# --------------------------------------------------------------------------


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import subprocess

        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
        ).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return isinstance(sys.exc_info()[1], PermissionError)
    return True


@contextlib.contextmanager
def _exclusive_file_lock(path: Path, label: str) -> Iterator[None]:
    """Atomic O_EXCL lock with stale-PID reclaim."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = None
    for attempt in range(2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                holder = int(path.read_text(encoding="utf-8").strip() or "0")
            except Exception:
                holder = 0
            if attempt == 0 and not _pid_alive(holder):
                log.warning("%s lock held by dead pid %s; reclaiming", label, holder)
                with contextlib.suppress(OSError):
                    path.unlink()
                continue
            raise RuntimeError(f"{label} lock busy (pid {holder}) at {path}")
    if fd is None:
        raise RuntimeError(f"could not acquire {label} lock at {path}")
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        fd = None
        yield
    finally:
        if fd is not None:
            with contextlib.suppress(OSError):
                os.close(fd)
        with contextlib.suppress(OSError):
            path.unlink()


@contextlib.contextmanager
def mirror_lock(cfg: MirrorConfig) -> Iterator[None]:
    """VAULT_DIR lock first, then the mirror LOCK_FILE. Order is load-bearing."""
    cfg.vault_dir.mkdir(parents=True, exist_ok=True)
    vault_sentinel = cfg.vault_dir / ".journal_mirror.vault.lock"
    with _exclusive_file_lock(vault_sentinel, "VAULT_DIR"):
        with _exclusive_file_lock(cfg.lock_file, "LOCK_FILE"):
            yield


# --------------------------------------------------------------------------
# Schema -- canonical shards table + external-content FTS5 kept in sync
# --------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS shards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT,
    utility_score REAL DEFAULT 1.0,
    access_count INTEGER DEFAULT 0,
    file_hash TEXT UNIQUE NOT NULL,
    domain_key TEXT DEFAULT 'global',
    embedding BLOB,
    density_score REAL DEFAULT 1.0,
    consolidated INTEGER DEFAULT 0,
    schema_version INTEGER DEFAULT 0,
    superseded_by TEXT DEFAULT NULL,
    valid_to TEXT DEFAULT NULL,
    sensitivity TEXT DEFAULT 'normal',
    enc INTEGER DEFAULT 0
);

CREATE VIRTUAL TABLE IF NOT EXISTS shards_fts USING fts5(
    title,
    content,
    content='shards',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS shards_ai AFTER INSERT ON shards BEGIN
    INSERT INTO shards_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS shards_ad AFTER DELETE ON shards BEGIN
    INSERT INTO shards_fts(shards_fts, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
END;

CREATE TRIGGER IF NOT EXISTS shards_au AFTER UPDATE ON shards BEGIN
    INSERT INTO shards_fts(shards_fts, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
    INSERT INTO shards_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
END;

CREATE TABLE IF NOT EXISTS journal_mirror_state (
    mirror_key   TEXT PRIMARY KEY,
    shard_id     INTEGER NOT NULL,
    content_sha  TEXT NOT NULL,
    created_utc  TEXT,
    title        TEXT,
    source       TEXT,
    last_seen    TEXT
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)


# --------------------------------------------------------------------------
# Record shaping
# --------------------------------------------------------------------------


def mirror_key(created_utc: str, title: str) -> str:
    """Idempotency key: stable across re-runs, unique per journal entry."""
    return hashlib.sha256(f"{created_utc}\x00{title}".encode("utf-8")).hexdigest()


def _content_sha(content: str, tags: str, source: str) -> str:
    return hashlib.sha256(f"{content}\x00{tags}\x00{source}".encode("utf-8")).hexdigest()


def classify_sensitivity(tags: Iterable[str]) -> str:
    lowered = {str(t).strip().lower() for t in tags or ()}
    if lowered & _SECRET_TAGS:
        return "secret"
    if lowered & _PRIVATE_TAGS:
        return "private"
    return "normal"


@dataclass
class MirrorRecord:
    key: str
    created_utc: str
    title: str
    content: str
    tags_json: str
    source: str
    sensitivity: str
    content_sha: str
    tags: list = field(default_factory=list)

    @property
    def is_private(self) -> bool:
        return self.sensitivity != "normal"


def read_journal(path: Path) -> Iterator[MirrorRecord]:
    """Yield one MirrorRecord per parseable journal line."""
    if not path.exists():
        log.warning("journal not found at %s", path)
        return
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                log.warning("journal line %d is not valid JSON; skipped", line_no)
                continue
            created = str(rec.get("created_utc") or "")
            title = str(rec.get("title") or "")
            if not created and not title:
                log.warning("journal line %d has no created_utc/title; skipped", line_no)
                continue
            tags = rec.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            content = str(rec.get("content") or "")
            source = str(rec.get("source") or "unattributed")
            tags_json = json.dumps(tags, ensure_ascii=False)
            yield MirrorRecord(
                key=mirror_key(created, title),
                created_utc=created,
                title=title,
                content=content,
                tags_json=tags_json,
                source=source,
                sensitivity=classify_sensitivity(tags),
                content_sha=_content_sha(content, tags_json, source),
                tags=list(tags),
            )


def _apply_private_policy(rec: MirrorRecord, policy: str) -> tuple[Optional[str], int]:
    """Return (content_to_store, enc_flag), or (None, 0) when the record is skipped."""
    if not rec.is_private or policy == "tag":
        return rec.content, 0
    if policy == "skip":
        return None, 0
    if policy == "encrypt":
        try:
            from . import private_vault
        except ImportError:  # pragma: no cover - executed only outside the package
            import private_vault  # type: ignore
        return private_vault.encrypt_text(rec.content), 1
    raise ValueError(f"unknown private policy {policy!r}")


# --------------------------------------------------------------------------
# Ingest
# --------------------------------------------------------------------------


@dataclass
class MirrorResult:
    dry_run: bool
    scanned: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_private: int = 0
    errors: list = field(default_factory=list)
    private_seen: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "mode": "DRY RUN" if self.dry_run else "WRITE",
            "scanned": self.scanned,
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped_private": self.skipped_private,
            "private_seen": self.private_seen,
            "errors": self.errors[:25],
        }


def mirror_journal(cfg: MirrorConfig, dry_run: bool = True) -> MirrorResult:
    """Mirror every journal entry into the shard node. Idempotent."""
    result = MirrorResult(dry_run=dry_run)
    records = list(read_journal(cfg.journal_path))
    result.scanned = len(records)
    if not records:
        return result

    cfg.mirror_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(cfg.mirror_db))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        ensure_schema(conn)
        cur = conn.cursor()
        existing = {
            row[0]: (row[1], row[2])
            for row in cur.execute("SELECT mirror_key, shard_id, content_sha FROM journal_mirror_state")
        }
        now = datetime.now(timezone.utc).isoformat()

        for rec in records:
            try:
                content, enc = _apply_private_policy(rec, cfg.private_policy)
                if rec.is_private:
                    result.private_seen.append(
                        {"title": rec.title[:80], "sensitivity": rec.sensitivity, "tags": rec.tags}
                    )
                if content is None:
                    result.skipped_private += 1
                    continue

                prior = existing.get(rec.key)
                if prior and prior[1] == rec.content_sha:
                    result.unchanged += 1
                    continue

                if dry_run:
                    if prior:
                        result.updated += 1
                    else:
                        result.inserted += 1
                    continue

                if prior:
                    cur.execute(
                        """UPDATE shards
                              SET timestamp=?, title=?, content=?, tags=?,
                                  sensitivity=?, enc=?, domain_key=?
                            WHERE id=?""",
                        (
                            rec.created_utc,
                            rec.title,
                            content,
                            rec.tags_json,
                            rec.sensitivity,
                            enc,
                            cfg.domain_key,
                            prior[0],
                        ),
                    )
                    cur.execute(
                        "UPDATE journal_mirror_state SET content_sha=?, last_seen=?, source=? WHERE mirror_key=?",
                        (rec.content_sha, now, rec.source, rec.key),
                    )
                    result.updated += 1
                else:
                    cur.execute(
                        """INSERT INTO shards
                               (timestamp, event_type, title, content, tags, utility_score,
                                access_count, file_hash, domain_key, sensitivity, enc, schema_version)
                           VALUES (?, ?, ?, ?, ?, 1.0, 0, ?, ?, ?, ?, 2)""",
                        (
                            rec.created_utc,
                            _EVENT_TYPE,
                            rec.title,
                            content,
                            rec.tags_json,
                            rec.key,
                            cfg.domain_key,
                            rec.sensitivity,
                            enc,
                        ),
                    )
                    cur.execute(
                        """INSERT INTO journal_mirror_state
                               (mirror_key, shard_id, content_sha, created_utc, title, source, last_seen)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (rec.key, cur.lastrowid, rec.content_sha, rec.created_utc, rec.title, rec.source, now),
                    )
                    result.inserted += 1
            except Exception as exc:  # keep going; one bad record must not stall the run
                result.errors.append({"title": rec.title[:80], "error": str(exc)})

        if not dry_run:
            conn.commit()
    finally:
        conn.close()
    return result


# --------------------------------------------------------------------------
# Fleet-map registration
# --------------------------------------------------------------------------


def register_node(cfg: MirrorConfig, dry_run: bool = True) -> dict:
    """Register the mirror DB as a fleet node.

    Inserted at the FRONT of the map on purpose: ``global_search`` constrains the
    planner to ``list(registry.keys())[:max_nodes]`` (max_nodes defaults to 12),
    so nodes past the twelfth key are never searched at default settings.
    """
    if not cfg.fleet_map.exists():
        raise FileNotFoundError(f"fleet map not found at {cfg.fleet_map}")
    if not cfg.mirror_db.exists():
        raise FileNotFoundError(f"mirror DB not built yet at {cfg.mirror_db}")

    registry = json.loads(cfg.fleet_map.read_text(encoding="utf-8"))

    conn = sqlite3.connect(f"file:{cfg.mirror_db}?mode=ro", uri=True)
    try:
        counts = {}
        for table in _PUBLISHED_TABLES:
            with contextlib.suppress(sqlite3.Error):
                counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()

    entry = {
        "path": str(cfg.mirror_db),
        "tables": counts,
        "chrono_stamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    already = cfg.node_name in registry
    position = list(registry).index(cfg.node_name) if already else None
    rebuilt = {cfg.node_name: entry}
    for key, value in registry.items():
        if key != cfg.node_name:
            rebuilt[key] = value

    plan = {
        "mode": "DRY RUN" if dry_run else "WRITE",
        "node": cfg.node_name,
        "entry": entry,
        "already_registered": already,
        "previous_position": position,
        "new_position": 0,
        "node_count_before": len(registry),
        "node_count_after": len(rebuilt),
        "reachable_at_default_max_nodes": True,
    }
    if not dry_run:
        backup = cfg.fleet_map.with_suffix(cfg.fleet_map.suffix + f".bak-{time.strftime('%Y%m%d%H%M%S')}")
        backup.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        cfg.fleet_map.write_text(json.dumps(rebuilt, indent=2), encoding="utf-8")
        plan["backup"] = str(backup)
    return plan


# --------------------------------------------------------------------------
# Hook used by write_memory so new entries mirror immediately
# --------------------------------------------------------------------------


def mirror_after_write(journal_path=None, quiet: bool = True) -> Optional[dict]:
    """Best-effort incremental mirror. Never raises -- the journal stays truth.

    Call this at the tail of ``SearchService.write_memory``.
    """
    try:
        cfg = MirrorConfig.resolve()
        if journal_path:
            cfg.journal_path = Path(journal_path)
        with mirror_lock(cfg):
            return mirror_journal(cfg, dry_run=False).as_dict()
    except Exception as exc:
        if not quiet:
            raise
        log.warning("journal mirror hook failed (journal write unaffected): %s", exc)
        return None


# --------------------------------------------------------------------------
# Verification + CLI
# --------------------------------------------------------------------------


def verify(cfg: MirrorConfig, query: str, limit: int = 5) -> dict:
    """Prove the mirror is FTS-searchable for a given query."""
    if not cfg.mirror_db.exists():
        return {"status": "error", "detail": f"no mirror DB at {cfg.mirror_db}"}
    tokens = [t for t in "".join(c if c.isalnum() else " " for c in query).split() if t]
    match = " OR ".join(tokens) or query
    conn = sqlite3.connect(f"file:{cfg.mirror_db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            """SELECT s.id, s.timestamp, s.title, s.sensitivity
                 FROM shards_fts f JOIN shards s ON s.id = f.rowid
                WHERE shards_fts MATCH ?
                ORDER BY bm25(shards_fts) LIMIT ?""",
            (match, limit),
        ).fetchall()
    finally:
        conn.close()
    return {
        "status": "success",
        "query": query,
        "hits": [{"id": r[0], "timestamp": r[1], "title": r[2], "sensitivity": r[3]} for r in rows],
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m nougen_shards.journal_mirror",
        description="Mirror codex_memory_journal.jsonl into an FTS5-searchable shard node.",
    )
    p.add_argument("--write", action="store_true", help="apply changes (default is dry-run)")
    p.add_argument("--register-node", action="store_true", help="also register the node in the fleet map")
    p.add_argument(
        "--private-policy",
        choices=("tag", "skip", "encrypt"),
        default=None,
        help="how to mirror entries tagged do-not-export/private (default: tag)",
    )
    p.add_argument("--verify", metavar="QUERY", help="run an FTS probe against the mirror and print hits")
    p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return p


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = MirrorConfig.resolve()
    if args.private_policy:
        cfg.private_policy = args.private_policy
    dry_run = not args.write

    payload = {
        "config": {
            "journal": str(cfg.journal_path),
            "mirror_db": str(cfg.mirror_db),
            "fleet_map": str(cfg.fleet_map),
            "node_name": cfg.node_name,
            "private_policy": cfg.private_policy,
            "lock_order": ["VAULT_DIR", "LOCK_FILE"],
        }
    }

    if args.verify:
        payload["verify"] = verify(cfg, args.verify)
    else:
        with mirror_lock(cfg):
            payload["ingest"] = mirror_journal(cfg, dry_run=dry_run).as_dict()
            if args.register_node:
                payload["register"] = register_node(cfg, dry_run=dry_run)

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

r"""NouGen Vault Canary Sentry & Integrity Auditor (Wishlist Item #5).

Authority: ~/.nougen/AUTHORITY.md
Mission:
    Automated integrity sentinel running PRAGMA integrity_check, WAL accumulation audits,
    and canary roundtrip latency probes across the 9 SQLite shard databases.
    Detects lock contention and uncheckpointed WAL bloat before timeouts cascade.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

logger = logging.getLogger(__name__)


@dataclass
class DbIntegrityResult:
    db_index: int
    db_path: str
    exists: bool
    size_bytes: int = 0
    wal_bytes: int = 0
    shm_bytes: int = 0
    quick_check: str = "UNKNOWN"
    shard_count: int = 0
    read_latency_ms: float = 0.0
    error: Optional[str] = None
    is_healthy: bool = False
    wal_bloat_warning: bool = False


@dataclass
class CanaryRoundtripResult:
    succeeded: bool
    db_index: int
    write_latency_ms: float = 0.0
    read_latency_ms: float = 0.0
    canary_shard_id: Optional[int] = None
    error: Optional[str] = None


@dataclass
class VaultIntegrityReport:
    timestamp_utc: str
    vault_dir: str
    overall_status: str  # "HEALTHY", "DEGRADED", "LOCKED", "CORRUPTED"
    total_dbs_expected: int = 9
    total_dbs_healthy: int = 0
    total_shards_indexed: int = 0
    total_size_bytes: int = 0
    total_wal_bytes: int = 0
    canary_roundtrip: Optional[CanaryRoundtripResult] = None
    db_results: List[DbIntegrityResult] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent)


def audit_single_db(i: int, db_path: Path, timeout: float = 2.0) -> DbIntegrityResult:
    """Audit a single shard database file for integrity, size, and read latency."""
    res = DbIntegrityResult(
        db_index=i,
        db_path=str(db_path),
        exists=db_path.exists(),
    )
    if not res.exists:
        res.error = "Database file does not exist"
        return res

    try:
        res.size_bytes = db_path.stat().st_size
        wal_path = db_path.with_name(f"{db_path.name}-wal")
        if wal_path.exists():
            res.wal_bytes = wal_path.stat().st_size
            # Warn if WAL exceeds 10 MB
            res.wal_bloat_warning = res.wal_bytes > (10 * 1024 * 1024)

        shm_path = db_path.with_name(f"{db_path.name}-shm")
        if shm_path.exists():
            res.shm_bytes = shm_path.stat().st_size

        t0 = time.perf_counter()
        db_uri = f"file:{quote(str(db_path))}?mode=ro"
        with closing(sqlite3.connect(db_uri, uri=True, timeout=timeout)) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA quick_check(1)")
            check_row = cur.fetchone()
            res.quick_check = check_row[0] if check_row else "NO_RESULT"

            cur.execute("SELECT count(*) FROM shards")
            res.shard_count = int(cur.fetchone()[0])
        t1 = time.perf_counter()
        res.read_latency_ms = round((t1 - t0) * 1000.0, 2)

        res.is_healthy = (res.quick_check == "ok")
    except Exception as e:
        res.error = f"{type(e).__name__}: {e}"
        res.is_healthy = False

    return res


def run_canary_write_probe(
    db_path: Path,
    db_index: int = 4,
    timeout: float = 2.5,
) -> CanaryRoundtripResult:
    """Perform a transactional write + read probe to verify write availability."""
    if not db_path.exists():
        return CanaryRoundtripResult(
            succeeded=False,
            db_index=db_index,
            error="Database missing for canary write",
        )

    t0 = time.perf_counter()
    try:
        with closing(sqlite3.connect(str(db_path), timeout=timeout)) as conn:
            conn.execute("PRAGMA busy_timeout = 2500")
            # Run write test inside a rollback transaction so no junk is committed
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO shards (timestamp, event_type, title, content, tags) VALUES (?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    "CANARY",
                    "__canary_probe__",
                    "canary payload",
                    json.dumps(["canary"]),
                ),
            )
            canary_id = cur.lastrowid
            t_write = time.perf_counter()
            write_ms = round((t_write - t0) * 1000.0, 2)

            # Verification read
            cur.execute("SELECT id, title FROM shards WHERE id = ?", (canary_id,))
            row = cur.fetchone()
            t_read = time.perf_counter()
            read_ms = round((t_read - t_write) * 1000.0, 2)

            # Roll back so canary row does not pollute permanent memory
            conn.rollback()

            if row and row[0] == canary_id:
                return CanaryRoundtripResult(
                    succeeded=True,
                    db_index=db_index,
                    write_latency_ms=write_ms,
                    read_latency_ms=read_ms,
                    canary_shard_id=canary_id,
                )
            else:
                return CanaryRoundtripResult(
                    succeeded=False,
                    db_index=db_index,
                    error="Canary row read verification failed",
                )
    except Exception as e:
        return CanaryRoundtripResult(
            succeeded=False,
            db_index=db_index,
            error=f"{type(e).__name__}: {e}",
        )


def audit_entire_vault(
    vault_dir: Optional[Path] = None,
    test_canary_write: bool = True,
    canary_db_index: int = 4,
) -> VaultIntegrityReport:
    """Audit the entire 9-DB shard vault concurrently."""
    v_dir = vault_dir or (Path.home() / ".nougen" / "shards")
    expected_dbs = tuple(range(1, 10))

    report = VaultIntegrityReport(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        vault_dir=str(v_dir),
        overall_status="HEALTHY",
        total_dbs_expected=len(expected_dbs),
    )

    with ThreadPoolExecutor(max_workers=len(expected_dbs)) as pool:
        futures = [
            pool.submit(audit_single_db, i, v_dir / f"nougen_shards_{i}.db")
            for i in expected_dbs
        ]
        results = [f.result() for f in futures]
    results.sort(key=lambda r: r.db_index)

    report.db_results = results
    for r in results:
        report.total_size_bytes += r.size_bytes
        report.total_wal_bytes += r.wal_bytes
        report.total_shards_indexed += r.shard_count
        if r.is_healthy:
            report.total_dbs_healthy += 1
        else:
            report.failures.append(f"db_{r.db_index}: {r.error or r.quick_check}")
        if r.wal_bloat_warning:
            report.failures.append(f"db_{r.db_index}: WAL bloat warning ({r.wal_bytes // (1024*1024)} MB)")

    # Canary write probe
    if test_canary_write:
        canary_db_path = v_dir / f"nougen_shards_{canary_db_index}.db"
        report.canary_roundtrip = run_canary_write_probe(canary_db_path, db_index=canary_db_index)
        if not report.canary_roundtrip.succeeded:
            report.failures.append(f"canary_write: {report.canary_roundtrip.error}")

    # Determine overall status
    if report.failures:
        if any("locked" in f.lower() or "busy" in f.lower() for f in report.failures):
            report.overall_status = "LOCKED"
        elif any("corrupt" in f.lower() for f in report.failures):
            report.overall_status = "CORRUPTED"
        else:
            report.overall_status = "DEGRADED"
    else:
        report.overall_status = "HEALTHY"

    return report


if __name__ == "__main__":
    rep = audit_entire_vault()
    print(rep.to_json())

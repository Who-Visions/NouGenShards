"""Unit tests for NouGen Vault Canary Sentry (tests/test_vault_canary.py)."""
import json
from pathlib import Path
import sqlite3
import pytest

from nougen_shards.vault_canary import (
    audit_entire_vault,
    audit_single_db,
    run_canary_write_probe,
)


def make_test_shard_db(path: Path, row_count: int = 5):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE shards (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, "
        "event_type TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL, tags TEXT)"
    )
    for i in range(1, row_count + 1):
        conn.execute(
            "INSERT INTO shards (timestamp, event_type, title, content, tags) VALUES (?, ?, ?, ?, ?)",
            ("2026-09-23T00:00:00Z", "KNOWLEDGE", f"title {i}", f"content {i}", json.dumps(["test"]))
        )
    conn.commit()
    conn.close()


def test_audit_single_db_healthy(tmp_path):
    db_file = tmp_path / "nougen_shards_1.db"
    make_test_shard_db(db_file, row_count=3)

    res = audit_single_db(1, db_file)
    assert res.exists is True
    assert res.is_healthy is True
    assert res.quick_check == "ok"
    assert res.shard_count == 3
    assert res.read_latency_ms >= 0.0
    assert res.error is None


def test_canary_write_probe_rollback_clean(tmp_path):
    db_file = tmp_path / "nougen_shards_4.db"
    make_test_shard_db(db_file, row_count=2)

    res = run_canary_write_probe(db_file, db_index=4)
    assert res.succeeded is True
    assert res.canary_shard_id == 3
    assert res.write_latency_ms >= 0.0
    assert res.read_latency_ms >= 0.0

    # Verify that canary row was rolled back and did NOT mutate the table
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM shards")
    assert cur.fetchone()[0] == 2
    conn.close()


def test_audit_entire_vault_complete(tmp_path):
    # Populate all 9 expected dbs
    for i in range(1, 10):
        make_test_shard_db(tmp_path / f"nougen_shards_{i}.db", row_count=2)

    rep = audit_entire_vault(vault_dir=tmp_path, test_canary_write=True, canary_db_index=4)
    assert rep.overall_status == "HEALTHY"
    assert rep.total_dbs_healthy == 9
    assert rep.total_shards_indexed == 18
    assert rep.canary_roundtrip is not None
    assert rep.canary_roundtrip.succeeded is True
    assert len(rep.failures) == 0

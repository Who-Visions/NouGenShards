"""Regression tests for deploy/replica read-only Docker snapshot configuration."""
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nougen_shards import core, snapshot_mode  # noqa: E402


def test_dockerignore_excludes_replica_env():
    dockerignore = ROOT / ".dockerignore"
    assert dockerignore.exists(), "Root .dockerignore missing for Docker build context"
    lines = {
        line.strip()
        for line in dockerignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert "deploy/replica/replica.env" in lines
    assert "*.env" in lines or ".env*" in lines or ".env.*" in lines


def test_replica_compose_enables_immutable_snapshot_mode():
    compose = (ROOT / "deploy" / "replica" / "docker-compose.yml").read_text(encoding="utf-8")
    assert "NOUGEN_SNAPSHOT_DIR: /vault" in compose
    assert 'NOUGEN_SNAPSHOT_LOCALIZE: "0"' in compose
    assert ":/vault:ro" in compose
    assert "127.0.0.1:7870:7860" in compose


def test_snapshot_script_guards_empty_glob_and_writes_latest_json(tmp_path):
    script = ROOT / "deploy" / "replica" / "snapshot.sh"
    raw = script.read_bytes()
    assert b"\r\n" not in raw, "snapshot.sh must use LF line endings for Linux/macOS bash"
    text = raw.decode("utf-8")
    assert "shopt -s nullglob" in text
    assert "${#dbs[@]} -eq 0" in text
    assert "PRAGMA journal_mode=DELETE;" in text
    assert "LATEST.json" in text

    bash_exe = shutil.which("bash")
    sqlite_exe = shutil.which("sqlite3")
    if not bash_exe or not sqlite_exe:
        return

    empty_src = tmp_path / "empty_src"
    empty_src.mkdir()
    replica_dst = tmp_path / "replica_dst"
    env = {
        **os.environ,
        "NOUGEN_VAULT_SRC": str(empty_src),
        "REPLICA_DIR": str(replica_dst),
    }
    fail_run = subprocess.run([bash_exe, str(script)], env=env, capture_output=True, text=True)
    assert fail_run.returncode != 0
    assert list(empty_src.iterdir()) == [], "Empty vault glob must never create a literal *.db file"

    src_vault = tmp_path / "live_vault"
    src_vault.mkdir()
    db_file = src_vault / "nougen_shards_1.db"
    conn = sqlite3.connect(db_file)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("CREATE TABLE shards (id INTEGER PRIMARY KEY, title TEXT, content TEXT)")
        conn.execute("INSERT INTO shards (title, content) VALUES ('wal title', 'wal body content')")
        conn.commit()
    finally:
        conn.close()

    ok_run = subprocess.run(
        [bash_exe, str(script)],
        env={**os.environ, "NOUGEN_VAULT_SRC": str(src_vault), "REPLICA_DIR": str(replica_dst)},
        capture_output=True,
        text=True,
    )
    assert ok_run.returncode == 0, ok_run.stderr
    latest_path = replica_dst / "snapshots" / "LATEST.json"
    assert latest_path.exists()
    stamp = json.loads(latest_path.read_text(encoding="utf-8"))["stamp"]
    snap_db = replica_dst / "snapshots" / stamp / "nougen_shards_1.db"
    assert snap_db.exists()
    ro_conn = sqlite3.connect(f"file:{snap_db}?immutable=1&mode=ro", uri=True)
    try:
        assert ro_conn.execute("PRAGMA journal_mode;").fetchone()[0].lower() == "delete"
        assert ro_conn.execute("SELECT title FROM shards").fetchone()[0] == "wal title"
    finally:
        ro_conn.close()


def test_wal_backup_reads_cleanly_in_immutable_snapshot_mode(monkeypatch, tmp_path):
    live_vault = tmp_path / "live_vault"
    snap_root = tmp_path / "replica"
    snap_dir = snap_root / "snapshots" / "20261119T000000Z"
    snap_dir.mkdir(parents=True)

    monkeypatch.setattr(core, "GLOBAL_DIR", live_vault)
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(live_vault))
    monkeypatch.setenv("NOUGEN_EMBED_AT_CAPTURE", "0")
    monkeypatch.setenv("NOUGEN_QUERY_EMBED", "0")
    monkeypatch.setenv("NOUGEN_DISTILL_LANES", "0")
    monkeypatch.setenv("NOUGEN_RERANK", "0")
    monkeypatch.delenv("NOUGEN_SNAPSHOT_DIR", raising=False)
    snapshot_mode._cache.update(at=0.0, dir=None, stamp=None)
    core.close_readonly_pool()

    cap = core.capture(
        "KNOWLEDGE",
        "Replica WAL Snapshot Title",
        "Immutable snapshot verification ensures WAL backups query cleanly on read-only mounts.",
        domain_key="global",
    )
    assert cap.captured is True

    # Simulate sqlite3 .backup preserving WAL journal mode without usable -wal/-shm sidecars.
    src_db = live_vault / f"nougen_shards_{cap.db_index}.db"
    dst_db = snap_dir / src_db.name
    src_conn = sqlite3.connect(src_db)
    dst_conn = sqlite3.connect(dst_db)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    (snap_root / "snapshots" / "LATEST.json").write_text(
        json.dumps({"stamp": "20261119T000000Z"}), encoding="utf-8"
    )
    os.chmod(dst_db, stat.S_IREAD)
    core.close_readonly_pool()

    monkeypatch.setenv("NOUGEN_SNAPSHOT_DIR", str(snap_root))
    monkeypatch.setenv("NOUGEN_SNAPSHOT_LOCALIZE", "0")
    snapshot_mode._cache.update(at=0.0, dir=None, stamp=None)
    try:
        results = core.retrieve("Replica WAL Snapshot Title", limit=5, domain_key="global")
        assert results, "Expected shard result from immutable read-only snapshot"
        assert results[0]["title"] == "Replica WAL Snapshot Title"
    finally:
        core.close_readonly_pool()
        snapshot_mode._cache.update(at=0.0, dir=None, stamp=None)
        if dst_db.exists():
            os.chmod(dst_db, stat.S_IREAD | stat.S_IWRITE)

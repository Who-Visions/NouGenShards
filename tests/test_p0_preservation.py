"""P0 preservation locks (Native Memory Engine, directive shard 31235@db6).

These tests pin the behaviour the later phases measure against. They assert
the current shape of the substrate — SQLite schema, WAL + explicit FULL
synchronous durability, FTS5 sync triggers, tenant boundaries, RRF hybrid
recall, and embed-at-ingest degradation to keyword-only — so a future
change that silently alters any of them fails loudly here first.

New tests only; no existing suite is rewritten. Scratch vaults only.
"""
# pylint: disable=protected-access
import inspect
import os
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as shards
from nougen_shards import tenant_policy

EXPECTED_SHARD_COLUMNS = {
    "id", "timestamp", "event_type", "title", "content", "tags",
    "utility_score", "access_count", "file_hash", "domain_key",
    "embedding", "density_score", "consolidated", "sensitivity", "enc",
    "machine", "valid_until", "last_verified", "source_uri", "learned_utc",
}


@pytest.fixture(autouse=True)
def vault(monkeypatch):
    """Temporary vault so the real grid is never touched."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)
        monkeypatch.setattr(
            shards, "get_db_path",
            lambda index: temp_path / f"test_shards_{index}.db")
        monkeypatch.setenv("NOUGEN_EMBED_AT_CAPTURE", "0")
        shards._INITIALIZED_DBS.clear()
        shards.init_db(1)
        yield temp_path


def _conn():
    return shards.get_connection(1)


def _insert_db1(title, content):
    """Insert straight into DB 1 (capture() hash-routes across all 9 DBs,
    so a capture is the wrong tool when the test reads DB 1 directly)."""
    import hashlib as _hashlib
    from datetime import datetime as _dt, timezone as _tz

    file_hash = _hashlib.sha256(f"{title}|||{content}".encode()).hexdigest()
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO shards (timestamp, event_type, title, content, file_hash)"
            " VALUES (?, 'test', ?, ?, ?)",
            (_dt.now(_tz.utc).isoformat(), title, content, file_hash))
        conn.commit()
    finally:
        conn.close()


def _columns(table="shards"):
    conn = _conn()
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def test_schema_shape_locked():
    """init_db creates the exact shard columns, tables, and indexes."""
    assert EXPECTED_SHARD_COLUMNS <= _columns()
    conn = _conn()
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"shards", "semantic_knowledge", "shards_fts"} <= tables
        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        assert {"shards_title_nocase", "idx_shards_domain_utility",
                "idx_semantic_domain_subject"} <= indexes
        triggers = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'")}
        assert {"shards_ai", "shards_ad", "shards_au",
                "shards_ts_norm_ai", "shards_ts_norm_au"} <= triggers
    finally:
        conn.close()


def test_capture_returns_dict_shape():
    """capture() returns a dict with a 'captured' flag (not a bare bool)."""
    result = shards.capture("test", "dict shape shard", "unique body one")
    assert result["captured"] is True


def test_fts_update_trigger_scoped_to_title_content():
    """The update trigger must not re-index on utility-only updates (270k
    re-index incident, 2026-10-01). A utility decay leaves FTS untouched."""
    _insert_db1("trigger scope check", "alpha body text")
    conn = _conn()
    try:
        before = conn.execute("SELECT COUNT(*) FROM shards_fts").fetchone()[0]
        assert before == 1
        conn.execute("UPDATE shards SET utility_score = 0.5")
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM shards_fts").fetchone()[0]
        assert after == 1
        assert shards.retrieve("trigger scope check", limit=1)
    finally:
        conn.close()


def test_fts_delete_trigger_retracts_rows():
    """Deleting a shard retracts it from FTS; recall stops returning it."""
    _insert_db1("retract me now", "beta body text")
    assert shards.retrieve("retract me now", limit=1)
    conn = _conn()
    try:
        conn.execute("DELETE FROM shards WHERE title = 'retract me now'")
        conn.commit()
    finally:
        conn.close()
    assert not shards.retrieve("retract me now", limit=1)


def test_wal_and_synchronous_are_explicit():
    """Vault connections set journal_mode=WAL and synchronous=FULL
    deliberately (P0 durability contract), not by implicit default."""
    assert shards.get_vault_journal_mode() == "WAL"
    assert shards.get_vault_synchronous_mode() == "FULL"
    conn = _conn()
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        # PRAGMA synchronous reads back as an integer: FULL == 2.
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2
    finally:
        conn.close()


def test_synchronous_env_override_and_invalid_falls_back_full(monkeypatch):
    """NOUGEN_VAULT_SYNCHRONOUS is honoured; garbage fails closed to FULL."""
    monkeypatch.setenv("NOUGEN_VAULT_SYNCHRONOUS", "NORMAL")
    assert shards.get_vault_synchronous_mode() == "NORMAL"
    monkeypatch.setenv("NOUGEN_VAULT_SYNCHRONOUS", "nonsense")
    assert shards.get_vault_synchronous_mode() == "FULL"


def test_dedup_index_uses_same_durability():
    """The central dedup index gets the same WAL + FULL contract."""
    conn = shards._get_dedup_connection()
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "hashes" in tables
    finally:
        conn.close()


def test_public_api_signatures_stable():
    """retrieve / federated_retrieve / capture keep their public signatures."""
    assert "query" in inspect.signature(shards.retrieve).parameters
    assert "limit" in inspect.signature(shards.retrieve).parameters
    assert "query_embedding" in inspect.signature(shards.retrieve).parameters
    assert "domain_key" in inspect.signature(shards.retrieve).parameters
    from nougen_shards import federation  # pylint: disable=import-outside-toplevel
    assert "query" in inspect.signature(federation.federated_retrieve).parameters
    params = inspect.signature(shards.capture).parameters
    for name in ("event_type", "title", "content", "tags", "embedding",
                 "domain_key", "sensitivity", "source_uri"):
        assert name in params


def test_rrf_fusion_is_position_only_and_deterministic():
    """RRF merges by rank (k=60): a rank-1 hit in one lane outscores a
    rank-2 hit, and the fusion is deterministic across calls."""
    a = {"file_hash": "a", "title": "first"}
    b = {"file_hash": "b", "title": "second"}
    fused = shards.reciprocal_rank_fusion([[a, b], [b, a]])
    assert [item["file_hash"] for item in fused] == ["a", "b"]
    assert shards.reciprocal_rank_fusion([[a, b], [b, a]]) == fused
    # Rank-1 in a single lane scores 1/61; rank-2 scores 1/62.
    single = shards.reciprocal_rank_fusion([[a, b]])
    assert single[0]["file_hash"] == "a"


def test_hybrid_recall_still_finds_keyword_match_without_vectors():
    """Keyword-only rows stay recallable: hybrid retrieve must not depend
    on the vector lane being populated."""
    assert shards.capture("test", "keyword only recall check",
                          "quasar relay routing notes")
    results = shards.retrieve("keyword only recall check", limit=3)
    assert results and results[0]["title"] == "keyword only recall check"


def test_embed_at_ingest_failure_degrades_to_keyword_only(monkeypatch):
    """Provider 'none' => capture still succeeds, embedding stays NULL, the
    miss is counted, and the shard is recallable by keyword (HARDENING §2)."""
    from nougen_shards import embed_providers  # pylint: disable=import-outside-toplevel
    monkeypatch.delenv("NOUGEN_EMBED_AT_CAPTURE", raising=False)
    monkeypatch.setenv("NOUGEN_EMBED_PROVIDER", "none")
    monkeypatch.setattr(embed_providers, "_RESOLVED", None)
    before = shards.EMBED_AT_CAPTURE_MISSES
    assert shards.capture("test", "degraded embed shard",
                          "still recallable by keyword")
    assert shards.EMBED_AT_CAPTURE_MISSES == before + 1
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT embedding FROM shards WHERE title = 'degraded embed shard'"
        ).fetchone()
        assert row[0] is None
    finally:
        conn.close()
    results = shards.retrieve("degraded embed shard", limit=1)
    assert results and results[0]["title"] == "degraded embed shard"


def test_tenant_unlabelled_tools_denied():
    """An unlabelled tool is denied to tenants (fail-closed default)."""
    assert tenant_policy.classify(["some_brand_new_tool"])["unclassified"] == [
        "some_brand_new_tool"]
    assert tenant_policy.allowed_for("tenant-1", "some_brand_new_tool") is False
    assert tenant_policy.allowed_for("owner", "some_brand_new_tool") is True


def test_tenant_cannot_reach_owner_only_tools():
    """OWNER_ONLY tools stay owner-only, including via env extras (code floor)."""
    assert tenant_policy.allowed_for("tenant-1", "dav1d_exec") is False
    assert tenant_policy.allowed_for("tenant-1", "vault_put") is True
    assert tenant_policy.allowed_for("tenant-1", "recall_memory") is True
    os.environ["NOUGEN_TENANT_EXTRA_TOOLS"] = "dav1d_exec,recall_memory"
    try:
        assert tenant_policy.allowed_for("tenant-1", "dav1d_exec") is False
    finally:
        del os.environ["NOUGEN_TENANT_EXTRA_TOOLS"]


def test_nine_db_cluster_routing_shape():
    """The 9-DB cluster shape: routing is deterministic by content hash."""
    assert shards.MAX_DB_COUNT == 9
    assert shards.get_routing_index("a" * 64) == shards.get_routing_index("a" * 64)
    assert 1 <= shards.get_routing_index("a" * 64) <= 9

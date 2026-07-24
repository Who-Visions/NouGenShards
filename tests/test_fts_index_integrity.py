"""FTS index integrity: writes must not be able to skip the index.

These are regression tests for a class of defect, not for one bad row. A shard
that reaches the `shards` table but never reaches the FTS index is the worst
kind of memory loss: it is returned by recent-shard listings and by retrieve(),
so every surface says the write succeeded, while keyword search can never find
it again.

The window that allowed it: init used to DROP the sync triggers and re-CREATE
them. Python's sqlite3 runs DDL in autocommit, so the DROP committed
immediately and any concurrent writer in that interval inserted a row nothing
indexed. These tests pin the two properties that close it -- init is a no-op
when the triggers are already canonical, and re-installing them repairs
whatever an earlier window orphaned.
"""
# pylint: disable=duplicate-code, protected-access
import sqlite3
import tempfile
from pathlib import Path

import numpy as np
import pytest

import nougen_shards.core as shards
from nougen_shards import embedding_backfill


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)
        monkeypatch.setattr(
            shards, "get_db_path", lambda index: temp_path / f"test_shards_{index}.db")
        # capture() routes by content hash across MAX_DB_COUNT databases, so
        # which DB a given shard lands in is a hash lottery. Pin the cluster to
        # one DB for these tests: the assertions are about whether a write is
        # indexed at all, not about routing, and without this a passing run only
        # means the sample text happened to hash to DB 1.
        monkeypatch.setattr(shards, "MAX_DB_COUNT", 1)
        shards.init_db(1)
        yield temp_path


def _insert_row(conn, title, content):
    conn.execute(
        "INSERT INTO shards (timestamp, event_type, title, content, tags, file_hash) "
        "VALUES ('2026-01-01T00:00:00Z', 'TEST', ?, ?, '[]', ?)",
        (title, content, f"hash_{title}"))
    conn.commit()


def _fts_hits(conn, term):
    return conn.execute(
        "SELECT count(*) FROM shards_fts WHERE shards_fts MATCH ?", (term,)).fetchone()[0]


def test_init_installs_canonical_triggers():
    conn = shards.get_connection(1)
    try:
        assert shards.fts_triggers_current(conn)
    finally:
        conn.close()


def test_ensure_triggers_is_a_noop_once_canonical():
    """The common path must change nothing -- a no-op cannot open a window."""
    conn = shards.get_connection(1)
    try:
        assert shards._ensure_fts_triggers(conn) is False
        assert shards._ensure_fts_triggers(conn) is False
    finally:
        conn.close()


def test_fts_count_star_cannot_detect_a_gap():
    """Pins WHY this defect hid: the obvious health check is structurally blind.

    `SELECT count(*) FROM shards_fts` on an external-content FTS5 table is
    answered from the content table, so it equals the row count even when the
    index holds nothing for that row. Any monitor built on it reports "in sync"
    forever. count_unindexed() reads the _docsize shadow table instead.
    """
    conn = shards.get_connection(1)
    try:
        conn.execute("DROP TRIGGER IF EXISTS shards_ai")  # simulate the window
        _insert_row(conn, "Ghost Shard", "unreachable by keyword search")

        rows = conn.execute("SELECT count(*) FROM shards").fetchone()[0]
        assert conn.execute("SELECT count(*) FROM shards_fts").fetchone()[0] == rows
        assert shards.count_unindexed(conn) == 1
        assert _fts_hits(conn, "unreachable") == 0
    finally:
        conn.close()


def test_reinstalling_triggers_repairs_rows_orphaned_by_the_window():
    conn = shards.get_connection(1)
    try:
        conn.execute("DROP TRIGGER IF EXISTS shards_ai")
        _insert_row(conn, "Orphan Shard", "written while the trigger was absent")
        assert shards.count_unindexed(conn) == 1

        assert shards._ensure_fts_triggers(conn) is True

        assert shards.count_unindexed(conn) == 0
        assert _fts_hits(conn, "absent") == 1
        assert shards.fts_triggers_current(conn)
    finally:
        conn.close()


def test_repair_fts_index_is_the_public_choke_point():
    conn = shards.get_connection(1)
    try:
        conn.execute("DROP TRIGGER IF EXISTS shards_ai")
        _insert_row(conn, "Lost Shard", "recoverable by the repair entry point")
    finally:
        conn.close()

    assert shards.repair_fts_index(1) == {1: 1}

    conn = shards.get_connection(1)
    try:
        assert shards.count_unindexed(conn) == 0
        assert _fts_hits(conn, "recoverable") == 1
    finally:
        conn.close()


def test_writes_through_capture_are_indexed_without_asking():
    """Any writer gets indexed because the TABLE enforces it, not the writer."""
    shards.capture("TEST", "Indexed By Construction", "quokka telemetry sample")
    conn = shards.get_connection(1)
    try:
        assert shards.count_unindexed(conn) == 0
        assert _fts_hits(conn, "quokka") == 1
    finally:
        conn.close()


def test_capture_embeds_on_the_happy_path(monkeypatch):
    """The one test the 2026-07-24 regression could not have survived.

    capture() referenced `clean_content` -- a local of compute_dedup_hash(), not
    of capture() -- so every ingest raised NameError inside a bare
    `except Exception`, embed() was called ZERO times, and every shard was born
    with a NULL embedding wearing an `embedding:pending` tag. The two tests that
    should have caught it asserted the *degraded* outcome, so they passed
    happily on the broken build.

    So: with the embedder available, capture() MUST call it, and the vector MUST
    land on the row. Both halves matter -- calls>0 without a stored blob is a
    write bug, a stored blob without a call means the assertion is fake.
    """
    calls = []

    def _fake_embed(text, model, timeout=None):
        calls.append({"text": text, "model": model})
        return [3.0, 4.0, 0.0]  # unnormalized on purpose; capture() normalizes

    monkeypatch.setattr(embedding_backfill, "embed", _fake_embed)
    monkeypatch.setattr(embedding_backfill, "resolve_embed_model",
                        lambda *a, **k: "probe-resolved-embed-model")

    shards.capture("TEST", "Born Recallable", "vector lane smoke content")

    assert len(calls) == 1, "capture() never reached the embedder"
    # It embeds the canonical (redacted, packet-stripped) text -- the SAME
    # normalization the dedup hash uses, which is what broke.
    assert calls[0]["text"] == shards.canonical_content("vector lane smoke content")
    # Rule 0.2: the model is whatever runtime discovery returned, not a constant.
    assert calls[0]["model"] == "probe-resolved-embed-model"

    conn = shards.get_connection(1)
    try:
        row = conn.execute(
            "SELECT embedding, tags FROM shards WHERE title = 'Born Recallable'"
        ).fetchone()
        assert row["embedding"] is not None, "shard stored with a NULL embedding"
        vec = np.frombuffer(row["embedding"], dtype=np.float32)
        assert len(vec) == 3
        assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-6, "not unit-normalized"
        # An embedded shard must NOT be tagged pending -- that marker is the
        # drift detector's backfill worklist.
        assert shards.EMBED_PENDING_TAG not in row["tags"]
        assert conn.execute(
            "SELECT count(*) FROM shards WHERE embedding IS NULL").fetchone()[0] == 0
    finally:
        conn.close()


def test_embed_outage_degrades_but_a_code_bug_does_not(monkeypatch):
    """Embedding cannot be trigger-enforced (it needs a live model), so a miss
    must at least be observable on the row instead of vanishing from the
    vector lane unannounced.

    Second half added 2026-07-24: the swallow that hid the miss must be narrow.
    A connection failure is an outage and degrades quietly; a NameError /
    AttributeError / TypeError is a programming bug and MUST propagate. The old
    blanket `except Exception` is precisely why a NameError looked like
    "ollama is down" for a full day.
    """
    def _unreachable(*a, **k):
        raise ConnectionRefusedError("ollama not listening")  # an OSError

    monkeypatch.setattr(embedding_backfill, "embed", _unreachable)
    monkeypatch.setattr(embedding_backfill, "resolve_embed_model",
                        lambda *a, **k: "some-model")
    shards.capture("TEST", "No Vector Here", "embed endpoint was unreachable")

    conn = shards.get_connection(1)
    try:
        tags = conn.execute(
            "SELECT tags FROM shards WHERE title = 'No Vector Here'").fetchone()[0]
        assert shards.EMBED_PENDING_TAG in tags
        assert conn.execute(
            "SELECT count(*) FROM shards WHERE embedding IS NULL").fetchone()[0] == 1
    finally:
        conn.close()

    # Now a genuine code defect in the embed path: it must reach the caller.
    def _broken(*a, **k):
        raise NameError("name 'clean_content' is not defined")

    monkeypatch.setattr(embedding_backfill, "embed", _broken)
    with pytest.raises(NameError):
        shards.capture("TEST", "Loud Failure", "a programming bug is not an outage")


def test_embed_model_is_discovered_not_hardcoded(monkeypatch):
    """Rule 0.2: the model comes from the live roster, with the exact tag."""
    monkeypatch.delenv("NOUGEN_EMBED_MODEL", raising=False)
    monkeypatch.setattr(embedding_backfill, "_RESOLVED_EMBED_MODEL", None)
    monkeypatch.setattr(embedding_backfill, "list_models",
                        lambda timeout=5: ["gemma4:12b", "nomic-embed-text:latest"])
    assert embedding_backfill.resolve_embed_model() == "nomic-embed-text:latest"

    # Unreachable host -> logged constant fallback, never a crash.
    monkeypatch.setattr(embedding_backfill, "_RESOLVED_EMBED_MODEL", None)
    monkeypatch.setattr(embedding_backfill, "list_models", lambda timeout=5: [])
    assert embedding_backfill.resolve_embed_model() == embedding_backfill.FALLBACK_EMBED_MODEL


def test_backfill_scope_excludes_the_forward_only_backlog():
    """The arXiv backlog is a deliberate campaign, never a repair side effect."""
    globs = embedding_backfill.backfill_exclude_globs()
    assert "arxiv_*.md" in globs and "intelligence_shard_arxiv_*.md" in globs

    clause, params = embedding_backfill._scope_sql(globs)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE shards (id INTEGER PRIMARY KEY, title TEXT, embedding BLOB)")
    conn.executemany("INSERT INTO shards (title, embedding) VALUES (?, NULL)", [
        ("arxiv_cs_AI_20260617_Something.md",),
        ("intelligence_shard_arxiv_2606.00001_something.md",),
        ("session_memory_real_work.md",),
    ])
    in_scope = conn.execute(
        "SELECT title FROM shards WHERE embedding IS NULL" + clause, params).fetchall()
    assert [r[0] for r in in_scope] == ["session_memory_real_work.md"]
    conn.close()

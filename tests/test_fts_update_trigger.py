"""The FTS update trigger must fire only when indexed text changes.

`shards_au` was `AFTER UPDATE ON shards` with no column list, so every update
re-indexed the row's full text: a delete plus an insert into the trigram FTS
index. `dream wake` decays every utility score (`UPDATE shards SET
utility_score = utility_score * 0.95`) across all nine ~1.2 GB databases, which
is ~270k full-text re-indexes to change one number the index does not cover.
On 2026-10-01 that ran past the loop's 900 s stage timeout and failed the dream
stage. FTS5 indexes only title and content, so the trigger is scoped to them.
"""
# pylint: disable=protected-access
import hashlib
import re
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as shards


@pytest.fixture(autouse=True)
def vault(monkeypatch):
    """Temporary vault so the real grid is never touched."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)
        monkeypatch.setattr(shards, "get_db_path", lambda index: temp_path / f"test_shards_{index}.db")
        shards._INITIALIZED_DBS.clear()
        shards.init_db(1)
        yield temp_path


def _conn():
    return shards.get_connection(1)


def _trigger_sql(name="shards_au"):
    conn = _conn()
    try:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)).fetchone()
        return re.sub(r"\s+", " ", row[0]).strip() if row else ""
    finally:
        conn.close()


def _fts_fingerprint():
    """Hash of every row of the FTS shadow tables: any re-index changes it."""
    conn = _conn()
    try:
        digest = hashlib.sha256()
        for table in ("shards_fts_data", "shards_fts_docsize", "shards_fts_idx"):
            for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2"):
                digest.update(repr(tuple(row)).encode("utf-8", "replace"))
        return digest.hexdigest()
    finally:
        conn.close()


def _add(title, content):
    """Insert straight into DB 1 (capture() routes to whichever DB is active),
    which also exercises the real insert trigger."""
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO shards (timestamp, event_type, title, content, file_hash, domain_key) "
            "VALUES (?, 'TEST', ?, ?, ?, 'global')",
            ("2026-10-01T00:00:00Z", title, content, hashlib.sha256(f"{title}{content}".encode()).hexdigest()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _fts_hits(token):
    conn = _conn()
    try:
        return [r[0] for r in conn.execute("SELECT rowid FROM shards_fts WHERE shards_fts MATCH ?", (f'"{token}"',))]
    finally:
        conn.close()


def test_update_trigger_is_scoped_to_the_indexed_columns():
    assert "AFTER UPDATE OF title, content ON shards" in _trigger_sql()


def test_insert_and_delete_triggers_are_unchanged():
    assert "AFTER INSERT ON shards" in _trigger_sql("shards_ai")
    assert "AFTER DELETE ON shards" in _trigger_sql("shards_ad")


def test_an_existing_database_with_the_old_trigger_is_migrated_on_init(vault):
    conn = _conn()
    conn.execute("DROP TRIGGER shards_au")
    conn.execute(
        "CREATE TRIGGER shards_au AFTER UPDATE ON shards BEGIN "
        "INSERT INTO shards_fts(shards_fts, rowid, title, content) VALUES ('delete', old.id, old.title, old.content); "
        "INSERT INTO shards_fts(rowid, title, content) VALUES (new.id, new.title, new.content); END;")
    conn.commit()
    conn.close()
    assert "AFTER UPDATE ON shards" in _trigger_sql()          # really the old one
    shards._INITIALIZED_DBS.clear()                            # a fresh process opens it
    shards.init_db(1)
    assert "AFTER UPDATE OF title, content ON shards" in _trigger_sql()


def test_updating_only_utility_does_not_touch_the_fts_index():
    sid = _add("decay target", "content that the decay must never re-tokenize")
    before = _fts_fingerprint()
    conn = _conn()
    conn.execute("UPDATE shards SET utility_score = utility_score * 0.95 WHERE id = ?", (sid,))
    conn.commit()
    conn.close()
    assert _fts_fingerprint() == before


def test_global_decay_leaves_the_index_and_search_intact():
    ids = [_add(f"shard {n}", f"payload number {n} with a distinctive marker zq{n}x") for n in range(40)]
    before = _fts_fingerprint()
    shards.decay_utility_scores()
    assert _fts_fingerprint() == before
    assert _fts_hits("zq7x") == [ids[7]]


def test_editing_the_content_still_reindexes():
    sid = _add("edit target", "the alpha-marker text")
    assert _fts_hits("alpha-marker") == [sid]
    conn = _conn()
    conn.execute("UPDATE shards SET content = ? WHERE id = ?", ("the beta-marker text", sid))
    conn.commit()
    conn.close()
    assert _fts_hits("alpha-marker") == []
    assert _fts_hits("beta-marker") == [sid]


def test_editing_the_title_still_reindexes():
    sid = _add("gamma-title-old", "body")
    conn = _conn()
    conn.execute("UPDATE shards SET title = ? WHERE id = ?", ("delta-title-new", sid))
    conn.commit()
    conn.close()
    assert _fts_hits("gamma-title-old") == []
    assert _fts_hits("delta-title-new") == [sid]

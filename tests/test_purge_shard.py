"""purge_shard: deletion that is complete, or it is a worse lie than suppression.

Wargame muse-review-elevations-20261107, E5. An external reviewer read that
"forget" suppresses rather than deletes; the source confirmed it. The node's own
``shard_forget`` did delete the row but left the dedup hash in ``dedup_index.db``,
so re-capturing the same text was reported as a duplicate of a shard that no
longer existed. These tests pin the full contract:

- after purge, no row in ``shards``, no entry in ``shards_fts``, no ``hashes`` row;
- recall (keyword lane) no longer returns it;
- re-capturing the same text succeeds as a new row, not a dedup hit;
- purge refuses without title/hash proof and on a wrong title;
- ``shards_forget`` still suppresses and leaves everything in place.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nougen_shards import core  # noqa: E402

TEXT = "The purge test shard mentions a zebra-colored lighthouse on Tuesday."


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path))
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    monkeypatch.setenv("NOUGEN_QUERY_EMBED", "0")
    monkeypatch.setenv("NOUGEN_EMBED_CAPTURE_TIMEOUT_S", "0.2")
    monkeypatch.setenv("NOUGEN_RECON_SWEEP_TRIGGER", "never")
    return tmp_path


def _capture():
    res = core.capture("test", "Purge me", TEXT)
    assert res.get("shard_id") and res.get("db_index"), res
    return int(res["shard_id"]), int(res["db_index"])


def _counts(shard_id, db_index, file_hash):
    conn = core.get_connection(db_index)
    try:
        rows = conn.execute("SELECT count(*) FROM shards WHERE id = ?", (shard_id,)).fetchone()[0]
        fts = conn.execute("SELECT count(*) FROM shards_fts WHERE rowid = ?", (shard_id,)).fetchone()[0]
    finally:
        conn.close()
    dconn = core._get_dedup_connection()  # pylint: disable=protected-access
    try:
        dedup = dconn.execute("SELECT count(*) FROM hashes WHERE file_hash = ?", (file_hash,)).fetchone()[0]
    finally:
        dconn.close()
    return rows, fts, dedup


def _file_hash(shard_id, db_index):
    conn = core.get_connection(db_index)
    try:
        return conn.execute("SELECT file_hash FROM shards WHERE id = ?", (shard_id,)).fetchone()[0]
    finally:
        conn.close()


def test_purge_leaves_no_trace_and_allows_recapture(vault):
    sid, db = _capture()
    fh = _file_hash(sid, db)
    assert _counts(sid, db, fh) == (1, 1, 1), "fixture: row, fts and dedup entries all present before purge"

    receipt = core.purge_shard(sid, db, confirm_title="Purge me")
    assert receipt["purged"] == sid and receipt["recoverable"] is False
    assert receipt["rows_removed"] == 1
    assert receipt["fts_entries_left"] == 0
    assert receipt["dedup_entries_removed"] == 1
    assert _counts(sid, db, fh) == (0, 0, 0)

    hits = core._keyword_retrieve("zebra-colored lighthouse", limit=5, domain_key="*")  # pylint: disable=protected-access
    assert not any(h.get("id") == sid and h.get("_db_index") == db for h in hits)

    again = core.capture("test", "Purge me", TEXT)
    assert again.get("shard_id"), f"re-capture after purge must be a fresh write, got {again}"
    assert not again.get("existing_db_index"), f"re-capture was treated as a duplicate: {again}"


def test_purge_refuses_without_proof_and_on_wrong_title(vault):
    sid, db = _capture()
    with pytest.raises(ValueError):
        core.purge_shard(sid, db)
    with pytest.raises(ValueError):
        core.purge_shard(sid, db, confirm_title="Not the title")
    with pytest.raises(ValueError):
        core.purge_shard(sid, db, content_hash="0000000000000000")
    fh = _file_hash(sid, db)
    assert _counts(sid, db, fh) == (1, 1, 1), "a refused purge must change nothing"


def test_purge_by_content_hash(vault):
    sid, db = _capture()
    conn = core.get_connection(db)
    try:
        row = conn.execute("SELECT title, domain_key, content, timestamp FROM shards WHERE id = ?",
                           (sid,)).fetchone()
    finally:
        conn.close()
    c_hash = core.CanonicalShardRef.compute_hash(row["domain_key"] or "", row["title"], row["content"],
                                                 str(row["timestamp"] or ""))
    receipt = core.purge_shard(sid, db, content_hash=c_hash)
    assert receipt["content_hash"] == c_hash and receipt["rows_removed"] == 1


def test_shards_forget_still_suppresses_and_keeps_everything(vault):
    sid, db = _capture()
    fh = _file_hash(sid, db)
    conn = core.get_connection(db)
    try:
        row = conn.execute("SELECT title, domain_key, content, timestamp FROM shards WHERE id = ?",
                           (sid,)).fetchone()
    finally:
        conn.close()
    c_hash = core.CanonicalShardRef.compute_hash(row["domain_key"] or "", row["title"], row["content"],
                                                 str(row["timestamp"] or ""))
    assert core.shards_forget(core.CanonicalShardRef(db_index=db, shard_id=sid, content_hash=c_hash)) is True
    assert _counts(sid, db, fh) == (1, 1, 1)
    conn = core.get_connection(db)
    try:
        r = conn.execute("SELECT utility_score, tags FROM shards WHERE id = ?", (sid,)).fetchone()
    finally:
        conn.close()
    assert r["utility_score"] == 0.0 and "suppressed" in (r["tags"] or "")

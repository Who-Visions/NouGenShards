"""The node's shard resolver must work against the schema core actually writes.

``app._resolve_shard`` selected ``original_timestamp`` from ``shards``. That
column does not exist: ``core.capture`` takes ``original_timestamp`` as a
parameter and folds it into ``timestamp``. On any vault the SELECT raised
``sqlite3.OperationalError: no such column``, which took the node's
``shard_amend`` / ``shard_retract`` / ``shard_forget`` down with it. Found while
building purge_shard (PR #981). These tests pin the resolver to the real schema
and to core's CanonicalShardRef convention (hash over ``timestamp``).
"""
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("gradio")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as node  # noqa: E402
from nougen_shards import core  # noqa: E402


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path))
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    monkeypatch.setenv("NOUGEN_QUERY_EMBED", "0")
    monkeypatch.setenv("NOUGEN_EMBED_CAPTURE_TIMEOUT_S", "0.2")
    monkeypatch.setenv("NOUGEN_RECON_SWEEP_TRIGGER", "never")
    return tmp_path


def _capture(title="Resolver target", text="A shard the node resolver must find by title and by hash."):
    res = core.capture("test", title, text)
    assert res.get("shard_id") and res.get("db_index"), res
    return int(res["shard_id"]), int(res["db_index"])


def test_resolver_runs_against_the_real_schema(vault):
    sid, db = _capture()
    idx, title, c_hash = node._resolve_shard(sid, db, expect_title="Resolver target")  # pylint: disable=protected-access
    assert (idx, title) == (db, "Resolver target")
    assert len(c_hash) == 16


def test_resolver_hash_matches_core_canonical_ref(vault):
    sid, db = _capture()
    conn = core.get_connection(db)
    try:
        row = conn.execute("SELECT title, domain_key, content, timestamp FROM shards WHERE id = ?", (sid,)).fetchone()
    finally:
        conn.close()
    expected = core.CanonicalShardRef.compute_hash(row["domain_key"] or "", row["title"], row["content"],
                                                   str(row["timestamp"] or ""))
    _, _, c_hash = node._resolve_shard(sid, db, content_hash=expected)  # pylint: disable=protected-access
    assert c_hash == expected
    # And core's own mutation path accepts the same hash: one convention, two surfaces.
    assert core.shards_retract(core.CanonicalShardRef(db_index=db, shard_id=sid, content_hash=expected)) is True


def _call(fn, *args, **kwargs):
    """The node rebinds these names to async MCP tool handlers; call either shape."""
    import asyncio
    import inspect
    out = fn(*args, **kwargs)
    if inspect.isawaitable(out):
        out = asyncio.run(out)
    return out


def test_node_amend_retract_forget_do_not_raise_on_fresh_vault(vault):
    sid, db = _capture("Mutate me", "Original body of the shard.")
    out = _call(node.shard_amend, sid, "Amended note.", db_index=db, confirm_title="Mutate me")
    assert out, out
    sid2, db2 = _capture("Retract me", "Body to retract.")
    out = _call(node.shard_retract, sid2, "Superseded.", db_index=db2, confirm_title="Retract me")
    assert out, out
    sid3, db3 = _capture("Forget me", "Body to forget.")
    out = _call(node.shard_forget, sid3, confirm_title="Forget me", db_index=db3)
    assert out.get("forgotten") == sid3 and out.get("recoverable") is False

"""embed_providers: in-process semantic recall without an Ollama server (wargame E2).

Plumbing is tested with a fake onnx lane (deterministic, 8-d) so CI needs no
model file. The one test that proves PARAPHRASE recall runs the real
all-MiniLM-L6-v2 and is skipped unless its files are present
(`nougen embed fetch`).
"""
import logging
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nougen_shards import core, embed_providers as ep  # noqa: E402

_VOCAB = ["bridge", "token", "rotate", "tuesday", "kettle", "copper", "dawn", "whistle"]


def _fake_onnx(texts, repo=ep.DEFAULT_ONNX_REPO):
    """Bag-of-words over a tiny vocab, L2-normalised: enough to make 'same words' close."""
    out = []
    for t in texts:
        v = np.array([float(w in (t or "").lower()) for w in _VOCAB], dtype=np.float32) + 1e-3
        out.append((v / np.linalg.norm(v)).tolist())
    return out


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path))
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    monkeypatch.setenv("NOUGEN_RECON_SWEEP_TRIGGER", "never")
    monkeypatch.setenv("NOUGEN_EMBED_AT_CAPTURE", "1")
    monkeypatch.setenv("NOUGEN_QUERY_EMBED", "1")
    monkeypatch.setattr(ep, "_RESOLVED", None)
    core._VECTOR_CACHE.clear()  # pylint: disable=protected-access
    return tmp_path


def test_forced_none_provider_embeds_nothing(vault, monkeypatch):
    monkeypatch.setenv("NOUGEN_EMBED_PROVIDER", "none")
    assert ep.resolve(refresh=True)[0] == "none"
    assert ep.embed_text("anything") is None
    assert "no embedding provider" in ep.describe_unavailable()


def test_onnx_spec_selects_onnx_without_probing_ollama(vault, monkeypatch):
    monkeypatch.setenv("NOUGEN_EMBED_PROVIDER", "auto")
    monkeypatch.setenv("NOUGEN_EMBED_MODEL", "onnx:some/repo")
    monkeypatch.setattr(ep, "_ollama_reachable", lambda *a, **k: pytest.fail("must not probe ollama"))
    assert ep.resolve(refresh=True) == ("onnx", "some/repo")


def test_auto_falls_to_onnx_when_ollama_down_and_model_present(vault, monkeypatch):
    monkeypatch.setenv("NOUGEN_EMBED_PROVIDER", "auto")
    monkeypatch.delenv("NOUGEN_EMBED_MODEL", raising=False)
    monkeypatch.setattr(ep, "_ollama_reachable", lambda *a, **k: False)
    monkeypatch.setattr(ep, "onnx_deps_present", lambda: True)
    monkeypatch.setattr(ep, "onnx_files_present", lambda repo=None: True)
    assert ep.resolve(refresh=True) == ("onnx", ep.DEFAULT_ONNX_REPO)


def test_capture_and_query_embed_through_onnx_lane_and_vector_recall_fires(vault, monkeypatch):
    monkeypatch.setenv("NOUGEN_EMBED_PROVIDER", "onnx")
    monkeypatch.setattr(ep, "onnx_embed", _fake_onnx)
    res = core.capture("test", "Bridge token", "The bridge token must rotate every Tuesday.")
    assert res.get("shard_id"), res
    conn = core.get_connection(int(res["db_index"]))
    try:
        blob = conn.execute("SELECT embedding FROM shards WHERE id = ?", (int(res["shard_id"]),)).fetchone()[0]
    finally:
        conn.close()
    assert blob is not None and len(blob) == 8 * 4, "capture stored an 8-d onnx-lane vector"

    q = core._embed_query("rotate the bridge token")  # pylint: disable=protected-access
    assert q is not None and q.shape == (8,)
    hits = core._vector_retrieve(q.tolist(), limit=5, domain_key="*")  # pylint: disable=protected-access
    assert any(h.get("id") == int(res["shard_id"]) for h in hits), hits


def test_dim_mismatch_is_warned_once_and_lane_skips(vault, monkeypatch, caplog):
    monkeypatch.setenv("NOUGEN_EMBED_PROVIDER", "onnx")
    monkeypatch.setattr(ep, "onnx_embed", _fake_onnx)          # stores 8-d
    res = core.capture("test", "Copper kettle", "A copper kettle whistles at dawn.")
    assert res.get("shard_id")
    core._DIM_MISMATCH_WARNED.clear()  # pylint: disable=protected-access
    q768 = (np.ones(768, dtype=np.float32) / np.sqrt(768)).tolist()
    with caplog.at_level(logging.WARNING, logger="nougen_shards.core"):
        first = core._vector_retrieve(q768, limit=5, domain_key="*")   # pylint: disable=protected-access
        second = core._vector_retrieve(q768, limit=5, domain_key="*")  # pylint: disable=protected-access
    assert first == [] and second == []
    msgs = [r.getMessage() for r in caplog.records if "vector lane skipped DB" in r.getMessage()]
    assert len(msgs) == 1, msgs
    assert "8-d" in msgs[0] and "768-d" in msgs[0]


def test_backfill_uses_provider(vault, monkeypatch):
    monkeypatch.setenv("NOUGEN_EMBED_PROVIDER", "none")
    ep.resolve(refresh=True)
    res = core.capture("test", "Unembedded", "Written while no provider answered.")
    assert res.get("shard_id")
    monkeypatch.setenv("NOUGEN_EMBED_PROVIDER", "onnx")
    monkeypatch.setattr(ep, "_RESOLVED", None)
    monkeypatch.setattr(ep, "onnx_embed", _fake_onnx)
    from nougen_shards import embedding_backfill as bf
    db = str(core.get_db_path(int(res["db_index"])))
    dry = bf.backfill_db(db, "onnx", execute=False, progress=False)
    assert dry.get("pending") == 1, dry
    out = bf.backfill_db(db, "onnx", execute=True, progress=False)
    assert out.get("embedded") == 1 and out.get("failed") == 0, out


@pytest.mark.skipif(not (ep.onnx_deps_present() and ep.onnx_files_present()),
                    reason="real onnx model not present; run `nougen embed fetch`")
def test_real_minilm_paraphrase_recall(vault, monkeypatch):
    monkeypatch.setenv("NOUGEN_EMBED_PROVIDER", "onnx")
    monkeypatch.delenv("NOUGEN_EMBED_MODEL", raising=False)
    ep.resolve(refresh=True)
    res = core.capture("test", "Credential rotation",
                       "The bridge token must rotate every Tuesday; the old one is revoked.")
    core.capture("test", "Kitchen", "A copper kettle whistles at dawn.")
    core.capture("test", "Garden", "Tomatoes ripen faster against a south wall.")
    assert res.get("shard_id")
    # No shared keywords with the target: 'bridge', 'token', 'rotate', 'Tuesday' all absent.
    q = core._embed_query("how often do we replace the access key and invalidate the previous one")  # pylint: disable=protected-access
    assert q is not None and q.shape == (384,)
    hits = core._vector_retrieve(q.tolist(), limit=3, domain_key="*")  # pylint: disable=protected-access
    assert hits and hits[0].get("id") == int(res["shard_id"]), [(h.get("id"), h.get("title")) for h in hits]

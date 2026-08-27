"""Regression tests for the 2026-08-27 recall bug hunt fixes.

Each test pins a MECHANISM, not an intent (HARDENING.md lesson: a checkmark
must cite the mechanism). Symptoms these guard against: a 25k-char raw vault
body at rank 1 on the MCP search surface, embedding columns leaking into
search payloads, LIKE-fallback rows outranking scored hits, and unbounded
utility priors overriding cross-lane consensus.
"""
import pytest

import app
from nougen_shards import core, federation


# --- Search-surface compaction (app._json_safe) ---

def test_compact_drops_embedding_and_vector_keys():
    row = {"id": 1, "content": "x", "embedding": b"\x00\x01",
           "embedding_json": "[0.1, 0.2]", "doc_vector": "[1]"}
    out = app._json_safe(row)
    assert "embedding" not in out
    assert "embedding_json" not in out
    assert "doc_vector" not in out
    assert out["id"] == 1


def test_compact_drops_none_values():
    out = app._json_safe({"id": 1, "title": "t", "era": None, "notes": None})
    assert "era" not in out and "notes" not in out


def test_compact_clamps_oversized_content_with_requery_marker():
    big = "a" * (app._SEARCH_MAX_CONTENT + 5000)
    out = app._json_safe({"id": 1, "content": big})
    assert len(out["content"]) < len(big)
    assert "requery by id" in out["content"]


def test_compact_never_clamps_identity_fields():
    long_path = "C:/very/" + "deep/" * 200 + "file.txt"
    out = app._json_safe({"id": 1, "file_path": long_path, "content": "ok"})
    assert out["file_path"] == long_path


def test_compact_kill_switch_restores_legacy_filter(monkeypatch):
    monkeypatch.setattr(app, "_SEARCH_COMPACT", False)
    row = {"id": 1, "embedding": b"\x00", "embedding_json": "[0.1]", "era": None}
    out = app._json_safe(row)
    # Legacy contract: bytes dropped, everything else untouched.
    assert "embedding" not in out
    assert out["embedding_json"] == "[0.1]"
    assert "era" in out


# --- Ranking priors ---

def test_rrf_utility_prior_is_bounded():
    # Two single-item lists so both rows share rank 1: identical consensus.
    spam = {"id": 1, "_db_index": 0, "title": "spam", "content": "s",
            "utility_score": 100.0}
    normal = {"id": 2, "_db_index": 0, "title": "normal", "content": "n",
              "utility_score": 1.0}
    merged = core.reciprocal_rank_fusion([[spam], [normal]])
    scores = {r["id"]: r["final_score"] for r in merged}
    consensus = 1.0 / 61
    # u/(1+u) < 1 => factor strictly below 0.7 + 0.3 = 1.0.
    assert scores[1] < consensus * 1.0
    # utility 100 vs 1 must not even double the score (was ~30x pre-squash).
    assert scores[1] / scores[2] < 1.2


def test_rrf_lane_weights_break_position_parity():
    # Rank-1 in a low-trust lane must not tie rank-1 in the curated grid.
    grid = [{"id": 1, "_db_index": 0, "title": "grid gold", "content": "g",
             "utility_score": 1.0}]
    vault = [{"id": "vault_x_1", "_db_index": "vault_x", "title": "vault junk",
              "content": "v", "utility_score": 1.0}]
    merged = core.reciprocal_rank_fusion([grid, vault], weights=[1.0, 0.5])
    scores = {r["title"]: r["final_score"] for r in merged}
    assert scores["grid gold"] == pytest.approx(2 * scores["vault junk"])
    # Default (no weights) stays position-parity: exact legacy arithmetic.
    legacy = core.reciprocal_rank_fusion([grid, vault])
    l_scores = {r["title"]: r["final_score"] for r in legacy}
    assert l_scores["grid gold"] == pytest.approx(l_scores["vault junk"])


def test_like_no_embed_prior_is_below_half():
    # The old constant 0.5 put relevance-blind LIKE rows above vector hits.
    assert core._LIKE_NO_EMBED_PRIOR < 0.5


# --- Federated lane confidence gate ---

def test_confidence_gate_drops_noise_floor_rows():
    junk = {"id": "vault_x_1", "final_score": 0.05}
    good = {"id": "vault_x_2", "final_score": 0.8}
    kept = federation._confidence_gate([junk, good])
    assert kept == [good]


def test_confidence_gate_env_override(monkeypatch):
    monkeypatch.setenv("NOUGEN_VAULT_MIN_SCORE", "0.9")
    kept = federation._confidence_gate([{"id": "a", "final_score": 0.8}])
    assert kept == []

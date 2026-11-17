"""Tests for the P1 FTS benchmark (tools/fts_bench.py) and its core knobs.

Covers: the NOUGEN_FTS_TOKENIZER / NOUGEN_FTS_BM25_* env knobs (defaults
are the live behaviour, invalid values fall back with a warning), the plain
unicode61 vault build, the recall-metric math, the fixed seed corpus
invariants, index-size measurement, and the bench CLI end to end
(--query-only / --explain-only) against a scratch vault.

Linux note: scratch vaults live under tmp_path (tmpfs on this VM is fine
because they are disposable); the CLI subprocess gets the sandbox proxy
variables stripped, matching the tool's own worker-env handling. No Ollama
is needed: captures run with NOUGEN_EMBED_AT_CAPTURE=0 and only the FTS /
keyword lanes are measured here (vector + hybrid need --embed).
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import nougen_shards.core as core
from tools.fts_bench import (
    _fts_merged_query,
    _pct,
    _recall_metrics,
    _worker_query,
    load_corpus,
    measure_sizes,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIRST_SHARDS = load_corpus()["shards"][:6]


@pytest.fixture
def vault(monkeypatch, tmp_path):
    """Scratch vault with the first 6 corpus shards, embeddings off."""
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    monkeypatch.setenv("NOUGEN_EMBED_AT_CAPTURE", "0")
    monkeypatch.delenv("NOUGEN_FTS_TOKENIZER", raising=False)
    monkeypatch.delenv("NOUGEN_FTS_BM25_TITLE_WEIGHT", raising=False)
    monkeypatch.delenv("NOUGEN_FTS_BM25_BODY_WEIGHT", raising=False)
    for shard in FIRST_SHARDS:
        assert core.capture(
            shard["event_type"], shard["title"], shard["content"],
            domain_key="global")
    core.close_readonly_pool()
    return tmp_path


def test_fts_tokenizer_defaults_and_validation(monkeypatch):
    """Default trigram; unicode61 accepted; anything else falls back."""
    monkeypatch.delenv("NOUGEN_FTS_TOKENIZER", raising=False)
    assert core._fts_tokenizer() == "trigram"
    monkeypatch.setenv("NOUGEN_FTS_TOKENIZER", "unicode61")
    assert core._fts_tokenizer() == "unicode61"
    monkeypatch.setenv("NOUGEN_FTS_TOKENIZER", " TRIGRAM ")
    assert core._fts_tokenizer() == "trigram"
    monkeypatch.setenv("NOUGEN_FTS_TOKENIZER", "bogus")
    assert core._fts_tokenizer() == "trigram"


def test_fts_bm25_weights_defaults_and_validation(monkeypatch):
    """Defaults 5.0/1.0; overrides honoured; invalid values fall back."""
    monkeypatch.delenv("NOUGEN_FTS_BM25_TITLE_WEIGHT", raising=False)
    monkeypatch.delenv("NOUGEN_FTS_BM25_BODY_WEIGHT", raising=False)
    assert core._fts_bm25_weights() == (5.0, 1.0)
    monkeypatch.setenv("NOUGEN_FTS_BM25_TITLE_WEIGHT", "1.0")
    monkeypatch.setenv("NOUGEN_FTS_BM25_BODY_WEIGHT", "2.0")
    assert core._fts_bm25_weights() == (1.0, 2.0)
    monkeypatch.setenv("NOUGEN_FTS_BM25_TITLE_WEIGHT", "bogus")
    assert core._fts_bm25_weights() == (5.0, 2.0)
    monkeypatch.setenv("NOUGEN_FTS_BM25_TITLE_WEIGHT", "-3")
    assert core._fts_bm25_weights() == (5.0, 2.0)
    monkeypatch.setenv("NOUGEN_FTS_BM25_TITLE_WEIGHT", "0")
    assert core._fts_bm25_weights() == (0.0, 2.0)


def test_plain_tokenizer_vault_build(monkeypatch, tmp_path):
    """A unicode61 vault is created with unicode61, and recall still works."""
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    monkeypatch.setenv("NOUGEN_EMBED_AT_CAPTURE", "0")
    monkeypatch.setenv("NOUGEN_FTS_TOKENIZER", "unicode61")
    core.init_db(1)
    sql = sqlite3.connect(tmp_path / "nougen_shards_1.db").execute(
        "SELECT sql FROM sqlite_master WHERE name='shards_fts'").fetchone()[0]
    assert "unicode61" in sql
    assert "trigram" not in sql
    assert core.capture("TEST", "relay leg claim protocol",
                        "Relay legs carry work between fleet lanes.",
                        domain_key="global")
    results = core._keyword_retrieve("relay leg claim", limit=5,
                                     domain_key="global")
    assert [r["title"] for r in results] == ["relay leg claim protocol"]


def test_weights_change_bm25_scores(vault, monkeypatch):
    """BM25 weights move the raw scores (trigram magnitudes are ~1e-6)."""
    default = core._keyword_retrieve("relay leg claim", limit=5,
                                     domain_key="global")
    assert default, "seed shard must be found"
    monkeypatch.setenv("NOUGEN_FTS_BM25_TITLE_WEIGHT", "1.0")
    monkeypatch.setenv("NOUGEN_FTS_BM25_BODY_WEIGHT", "1.0")
    flat = core._keyword_retrieve("relay leg claim", limit=5,
                                  domain_key="global")
    assert flat, "seed shard must be found with flat weights"
    assert default[0]["bm25_score"] != flat[0]["bm25_score"]


def test_recall_metrics_math():
    """Recall@k / MRR / nDCG@10 on a hand-checkable case."""
    ranked = [["a", "b", "c"], ["c", "d"]]
    targets = ["a", "x"]
    m = _recall_metrics(ranked, targets)
    assert m["n"] == 2
    assert m["recall@1"] == 0.5
    assert m["recall@3"] == 0.5
    assert m["recall@10"] == 0.5
    assert m["mrr"] == 0.5
    assert m["ndcg@10"] == 0.5
    assert _recall_metrics([], [])["n"] == 0
    # Nearest-rank: idx = round(0.5 * (4-1)) = round(1.5) = 2 -> 3.0.
    assert _pct([1.0, 2.0, 3.0, 4.0], 0.5) == 3.0


def test_seed_corpus_is_fixed():
    """The corpus is exactly the recorded one: 60 shards, 28 queries."""
    corpus = load_corpus()
    assert corpus["meta"]["name"] == "p1-fts-seed-corpus-v1"
    assert corpus["meta"]["seed"] == 20261116
    assert len(corpus["shards"]) == 60
    assert len(corpus["queries"]) == 28
    assert len({s["title"] for s in corpus["shards"]}) == 60
    bodies = [len(s["content"]) for s in corpus["shards"]]
    assert min(bodies) >= 400 and max(bodies) <= 1000
    assert min(len(s["title"]) for s in corpus["shards"]) >= 12
    tiers = [q["tier"] for q in corpus["queries"]]
    assert tiers.count("title") == 12
    assert tiers.count("body") == 12
    assert tiers.count("negative") == 4


def test_measure_sizes(vault):
    """Index-size tracking sees the vault and its FTS tables."""
    sizes = measure_sizes(vault)
    assert sizes["shards"] == 6
    assert sizes["total_bytes"] > 0
    assert sizes["bytes_per_shard"] > 0
    assert sizes["dbstat_available"] is True
    assert any(key.split(":", 1)[1].startswith("shards_fts")
               for key in sizes["fts_tables"])
    # The shards table itself is tracked separately: it holds the rows
    # (and embedding BLOBs), not the index.
    assert not any(key.split(":", 1)[1] == "shards"
                   for key in sizes["fts_tables"])
    assert sizes["shards_table_bytes"] > 0
    assert sum(sizes["fts_tables"].values()) > 0


def _bench_env(vault_dir):
    env = {k: v for k, v in os.environ.items()
           if k not in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
                        "ALL_PROXY", "all_proxy", "no_proxy", "NO_PROXY")}
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["NOUGEN_VAULT_DIR"] = str(vault_dir)
    env["NOUGEN_EMBED_AT_CAPTURE"] = "0"
    return env


def _run_bench_cli(vault_dir, *args):
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "fts_bench.py"), *args],
        env=_bench_env(vault_dir), capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, f"fts_bench {args} failed:\n{proc.stderr[-2000:]}"
    return json.loads(proc.stdout[proc.stdout.index("{"):])


def test_cli_query_only_reports_per_lane_timings(vault):
    """--query-only runs the lanes over all 24 scored queries (n>0)."""
    report = _run_bench_cli(vault, "--query-only", str(vault), "--repeats", "1")
    assert report["n_queries"] == 24
    assert report["repeats"] == 1
    for lane_name in ("fts_direct", "keyword"):
        lane = report["lanes"][lane_name]
        assert lane["n"] == 24, f"{lane_name} measured zero queries"
        assert lane["p50_ms"] > 0
        assert lane["p95_ms"] >= lane["p50_ms"]
        assert lane["quality"]["all"]["n"] == 24
    # Negatives are reported, not asserted: the fuzzy lane may surface a
    # low-similarity row, so only the 0..4 range is pinned here.
    for lane_name in ("keyword", "fts_direct"):
        assert 0 <= report["negatives_nonempty"][lane_name] <= 4


def test_cli_explain_only_audits_live_queries(vault):
    """--explain-only lists the indexes and which the plans actually use."""
    audit = _run_bench_cli(vault, "--explain-only", str(vault))
    assert audit["db_rows"] > 0
    assert "idx_shards_domain_utility" in audit["indexes"]
    assert "shards_title_nocase" in audit["indexes"]
    assert "shards_fts (virtual table index)" in audit["indexes_used"]
    assert isinstance(audit["indexes_unused"], list)
    assert {p["name"] for p in audit["plans"]} == {
        "fts_and_match", "fts_or_match", "like_fallback",
        "domain_utility", "title_nocase", "file_hash_lookup"}
    fts_plan = next(p for p in audit["plans"] if p["name"] == "fts_and_match")
    assert any("VIRTUAL TABLE INDEX" in line for line in fts_plan["plan"])


def test_fts_merged_query_falls_back_per_db(monkeypatch, tmp_path):
    """OR fallback is per DB: one DB's AND hit must not hide another's OR hits.

    DB1 holds a shard matching both query terms; DB2 holds one matching a
    single term. The merged result must contain both titles (Codex P2 on
    #1101: the old global fallback broke out after DB1's AND hit, so DB2's
    OR-only hit was silently dropped).
    """
    db_a, db_b = tmp_path / "a", tmp_path / "b"
    for d in (db_a, db_b):
        d.mkdir()
    monkeypatch.setattr(core, "GLOBAL_DIR", db_a)
    monkeypatch.setenv("NOUGEN_EMBED_AT_CAPTURE", "0")
    assert core.capture(
        "TEST", "zebra quokka plains",
        "The zebra quokka marsupial hops across the red plain at dawn.",
        domain_key="global")
    core.close_readonly_pool()
    monkeypatch.setattr(core, "GLOBAL_DIR", db_b)
    assert core.capture(
        "TEST", "zebra meadow dawn",
        "The zebra grazes on the open meadow in the morning light.",
        domain_key="global")
    core.close_readonly_pool()
    combined = tmp_path / "combined"
    combined.mkdir()
    db_a_file = next(db_a.glob("nougen_shards_*.db"))
    db_b_file = next(db_b.glob("nougen_shards_*.db"))
    shutil.copy(db_a_file, combined / "nougen_shards_1.db")
    shutil.copy(db_b_file, combined / "nougen_shards_2.db")
    db_files = sorted(combined.glob("nougen_shards_*.db"))
    assert len(db_files) == 2
    and_expr = core._build_fts_match_query("zebra quokka")
    or_expr = core._build_fts_match_query("zebra quokka", joiner=" OR ")
    assert and_expr and or_expr and and_expr != or_expr
    merged = _fts_merged_query(db_files, and_expr, or_expr, 5.0, 1.0, 10)
    assert set(merged) == {"zebra quokka plains", "zebra meadow dawn"}


def test_worker_query_negatives_probe_embed_lanes(vault, monkeypatch, capsys):
    """Negatives count vector/hybrid too -- stubbed lanes, no Ollama needed.

    The old negatives loop never called the embedding lanes, so their
    reported 0 was unmeasured (Codex P2 on #1101). With the vector lane
    stubbed non-empty and hybrid stubbed empty, the report must say
    vector=4, hybrid=0 across the 4 negative queries.
    """
    monkeypatch.setattr(core, "_embed_query", lambda q: np.zeros(3))
    monkeypatch.setattr(
        core, "_vector_retrieve",
        lambda emb, limit=10, domain_key="global": [{"title": "fake vector"}])
    monkeypatch.setattr(
        core, "retrieve",
        lambda q, limit=10, domain_key="global": [])
    _worker_query(str(vault), repeats=1, weights=(5.0, 1.0), embed=True)
    report = json.loads(capsys.readouterr().out.strip())
    assert set(report["negatives_nonempty"]) == {
        "fts_direct", "keyword", "vector", "hybrid"}
    assert report["negatives_nonempty"]["vector"] == 4
    assert report["negatives_nonempty"]["hybrid"] == 0

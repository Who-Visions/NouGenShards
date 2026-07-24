"""HARDENING invariant 5: multi-term queries must not silently AND.

Observed kill: FTS returned 0 rows for "huggingface nougenai token" while
"huggingface" alone matched thousands — conversational queries die on FTS5
implicit-AND semantics, then the LIKE fallback (`%whole query%`) is even
stricter. The fix retries the same safe-quoted tokens joined with OR
(bm25-ranked) before degrading to LIKE.
"""
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as shards


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)
        monkeypatch.setattr(shards, "get_db_path",
                            lambda index: temp_path / f"test_shards_{index}.db")
        shards.init_db(1)
        yield temp_path


def test_multi_term_query_survives_partial_match():
    # Only "huggingface" appears in the corpus; "nougenai"/"token" never
    # co-occur with it. Implicit AND returns nothing — the OR retry must hit.
    shards.capture("KNOWLEDGE", "HF credential note",
                   "The huggingface credential lives in the keymaker vault.")
    res = shards.retrieve("huggingface nougenai zzztoken", limit=3)
    assert res, "multi-term query died on AND semantics instead of OR fallback"
    assert any("huggingface" in (r.get("content") or "") for r in res)


def test_or_fallback_ranks_fuller_coverage_first():
    shards.capture("KNOWLEDGE", "One term", "huggingface appears alone here.")
    shards.capture("KNOWLEDGE", "Two terms",
                   "huggingface credential rotation runbook for the vault.")
    res = shards.retrieve("huggingface credential zzzmissing", limit=3)
    assert len(res) >= 2
    # bm25 must rank the shard covering more query terms above the single-hit.
    ids_by_rank = [r["title"] for r in res]
    assert ids_by_rank.index("Two terms") < ids_by_rank.index("One term")


def test_and_semantics_still_preferred_when_they_hit():
    # When the AND pass matches, the OR retry must not run and dilute results.
    shards.capture("KNOWLEDGE", "Exact pair", "alpha bravo together forever.")
    shards.capture("KNOWLEDGE", "Alpha only", "alpha appears without its pair.")
    res = shards.retrieve("alpha bravo", limit=3)
    assert res
    assert res[0]["title"] == "Exact pair"


def test_single_token_query_unchanged():
    shards.capture("KNOWLEDGE", "Solo", "watchtower stands alone.")
    res = shards.retrieve("watchtower", limit=3)
    assert res and res[0]["title"] == "Solo"


def test_short_acronym_query_is_answered_only_by_the_like_fallback():
    """The LIKE branch was untested: gutting it changed no test result, because
    every other case here is already satisfied by the FTS AND or OR pass.

    This case cannot be: the FTS5 trigram tokenizer cannot index tokens shorter
    than 3 characters, so _build_fts_match_query() returns None for a two-letter
    acronym query and _keyword_retrieve() never issues a MATCH at all. Short
    acronyms are ordinary operator vocabulary ("HF", "AI", "S3", "ML"), so the
    substring scan is the only lane that can answer them — losing it silently
    would make a whole query class unrecallable.
    """
    shards.capture("KNOWLEDGE", "Acronym note",
                   "The HF lane holds the rotated credential.")

    # Precondition: there is no FTS expression for this query, so a hit can only
    # have come from the LIKE substring scan.
    assert shards._build_fts_match_query("hf") is None
    assert shards._build_fts_match_query("hf", joiner=" OR ") is None

    res = shards.retrieve("hf", limit=3)
    assert res, "short-acronym query died: the LIKE fallback never ran"
    assert res[0]["title"] == "Acronym note"


def test_like_fallback_still_honours_domain_scope():
    """The fallback is a lane, not an escape hatch: it must not leak other
    domains into a domain-scoped query."""
    shards.capture("KNOWLEDGE", "Alpha acronym", "the HF lane, domain alpha.",
                   domain_key="Domain/Alpha")
    shards.capture("KNOWLEDGE", "Beta acronym", "the HF lane, domain beta.",
                   domain_key="Domain/Beta")
    hits = shards._keyword_retrieve("hf", 20, None, "Domain/Alpha")
    assert [h["title"] for h in hits] == ["Alpha acronym"]

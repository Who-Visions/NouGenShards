"""Tests for the n-gram module and the fuzzy recall lane it powers.

Grounded in docs/theory/n-gram-topologies.md: the §8.2 boundary-marker
example is asserted verbatim, and the retrieval tests pin the exact failure
mode §7.2 describes (morphological variants invisible to exact matchers).
"""
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as shards
from nougen_shards import ngram


# --- primitives -------------------------------------------------------------

def test_char_ngrams_match_doc_example():
    # §8.2: `where` -> {<wh, whe, her, ere, re>}
    assert ngram.char_ngrams("where") == {"<wh", "whe", "her", "ere", "re>"}


def test_char_ngrams_short_tokens_and_case():
    assert ngram.char_ngrams("Go") == {"<go", "go>"}  # marked form windowed
    assert ngram.char_ngrams("A b") == {"<a>", "<b>"}
    assert ngram.char_ngrams("") == set()


def test_overlap_coefficient_tolerates_asymmetry():
    # A short query fully contained in a long document must score ~1 even
    # though Dice dilutes toward 0 - this is why the fuzzy lane gates on
    # overlap, not Dice.
    q = ngram.char_ngrams("automaton")
    doc = ngram.char_ngrams("Automation pipeline: the deployment automation "
                            "handles the release pipeline end to end.")
    assert ngram.overlap_coefficient(q, doc) > 0.7
    assert ngram.dice_similarity(q, doc) < 0.5
    assert ngram.overlap_coefficient(set(), doc) == 0.0


def test_dice_similarity_bounds():
    a, b = ngram.char_ngrams("automation"), ngram.char_ngrams("automaton")
    assert 0.5 < ngram.dice_similarity(a, b) < 1.0  # near-variant, high overlap
    assert ngram.dice_similarity(a, a) == 1.0
    assert ngram.dice_similarity(a, ngram.char_ngrams("zebra")) < 0.2
    assert ngram.dice_similarity(set(), a) == 0.0


# --- fuzzy retrieval lane ----------------------------------------------------

@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)
        monkeypatch.setattr(shards, "get_db_path",
                            lambda index: temp_path / f"ngram_{index}.db")
        shards.init_db(1)
        yield temp_path


def _seed():
    shards.capture("KNOWLEDGE", "Automation pipeline",
                   "The deployment automation handles the release pipeline end to end.")
    shards.capture("KNOWLEDGE", "Grocery list",
                   "Milk, eggs, bread and a dozen unrelated household staples.")


def test_fuzzy_lane_bridges_morphological_variants():
    _seed()
    # §7.2's exact failure mode: not a token match, not a substring - only
    # set-similarity can recover it.
    results = shards.retrieve("automaton", limit=5)
    assert results, "fuzzy lane should recover the near-variant"
    assert results[0]["title"] == "Automation pipeline"
    assert all(r["title"] != "Grocery list" for r in results)


def test_fuzzy_lane_recovers_typos():
    _seed()
    results = shards.retrieve("deploiment automtion", limit=5)
    assert results and results[0]["title"] == "Automation pipeline"


def test_exact_match_still_wins_and_skips_fuzzy():
    _seed()
    results = shards.retrieve("automation", limit=5)
    assert results and results[0]["title"] == "Automation pipeline"


def test_gibberish_finds_nothing():
    _seed()
    assert shards.retrieve("qxzvkjw plmtrf", limit=5) == []


def test_fuzzy_lane_is_deterministic():
    _seed()
    first = [(r["id"], r.get("_db_index")) for r in shards.retrieve("automaton", limit=5)]
    for _ in range(5):
        again = [(r["id"], r.get("_db_index")) for r in shards.retrieve("automaton", limit=5)]
        assert again == first

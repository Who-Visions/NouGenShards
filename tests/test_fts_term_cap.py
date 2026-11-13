"""A whole chat prompt must not become a 20-term FTS OR scan (6s per call on a 12 GB grid)."""
from nougen_shards import core


def test_long_query_is_capped_to_max_terms(monkeypatch):
    monkeypatch.delenv("NOUGEN_FTS_MAX_TERMS", raising=False)
    q = " ".join(f"term{i:02d}" + "x" * (i % 5) for i in range(25))
    expr = core._build_fts_match_query(q, joiner=" OR ")
    assert expr.count(" OR ") + 1 == 8


def test_cap_keeps_longest_terms_in_original_order(monkeypatch):
    monkeypatch.setenv("NOUGEN_FTS_MAX_TERMS", "2")
    assert core._build_fts_match_query("abc relayrebase defg quarantine") == '"relayrebase" "quarantine"'


def test_duplicates_collapse_and_short_queries_unchanged(monkeypatch):
    monkeypatch.delenv("NOUGEN_FTS_MAX_TERMS", raising=False)
    assert core._build_fts_match_query("relay Relay rebase") == '"relay" "rebase"'
    assert core._build_fts_match_query('foo"bar baz') == '"foo""bar" "baz"'

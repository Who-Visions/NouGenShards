"""
Unit tests for algorithms_elevated module.
"""
from nougen_shards.algorithms_elevated import damerau_levenshtein_distance, jaro_winkler_similarity

def test_damerau_levenshtein():
    assert damerau_levenshtein_distance("martha", "marhta") == 1  # Transposition
    assert damerau_levenshtein_distance("kitten", "sitting") == 3
    assert damerau_levenshtein_distance("same", "same") == 0

def test_jaro_winkler():
    sim = jaro_winkler_similarity("martha", "marhta")
    assert 0.90 <= sim <= 1.0
    assert jaro_winkler_similarity("Dwayne", "Duane") > 0.80
    assert jaro_winkler_similarity("abc", "xyz") == 0.0

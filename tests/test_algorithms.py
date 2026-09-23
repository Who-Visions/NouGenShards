"""Tests for canonical algorithms and data structures engine."""
import pytest
from nougen_shards.algorithms import (
    BKTree,
    Trie,
    Graph,
    LZWCompressor,
    levenshtein_distance,
    list_algorithms,
    get_algorithm,
    benchmark_algorithm,
    ingest_algorithm_shards,
)


def test_levenshtein_distance():
    assert levenshtein_distance("", "") == 0
    assert levenshtein_distance("a", "") == 1
    assert levenshtein_distance("", "b") == 1
    assert levenshtein_distance("kitten", "sitting") == 3
    assert levenshtein_distance("sunday", "saturday") == 3
    assert levenshtein_distance("nougen", "nougen") == 0


def test_bk_tree_search():
    tree = BKTree()
    words = ["relay", "relays", "delay", "play", "ball", "baton", "bottom"]
    for w in words:
        tree.add(w, payload={"term": w})

    assert len(tree) == len(words)

    # Exact match
    results = tree.search("relay", max_distance=0)
    assert len(results) == 1
    assert results[0][0] == "relay"
    assert results[0][1] == 0

    # Distance 1 (relay -> relays, delay)
    results1 = tree.search("relay", max_distance=1)
    matched_terms = [r[0] for r in results1]
    assert "relay" in matched_terms
    assert "relays" in matched_terms
    assert "delay" in matched_terms

    # Distance 2 (relay -> play)
    results2 = tree.search("relay", max_distance=2)
    matched2 = [r[0] for r in results2]
    assert "play" in matched2


def test_trie_prefix_search():
    trie = Trie()
    words = ["relay", "relays", "release", "recall", "render", "shard", "substrate"]
    for w in words:
        trie.insert(w, payload={"word": w})

    assert len(trie) == len(words)
    assert trie.search("relay") is True
    assert trie.search("nonexistent") is False

    # Prefix search
    re_matches = trie.starts_with("re")
    re_words = [m[0] for m in re_matches]
    assert "relay" in re_words
    assert "relays" in re_words
    assert "release" in re_words
    assert "recall" in re_words
    assert "render" in re_words
    assert "shard" not in re_words


def test_graph_dijkstra():
    g = Graph()
    g.add_edge("A", "B", 4.0)
    g.add_edge("A", "C", 2.0)
    g.add_edge("B", "C", 1.0)
    g.add_edge("B", "D", 5.0)
    g.add_edge("C", "D", 8.0)
    g.add_edge("C", "E", 10.0)
    g.add_edge("D", "E", 2.0)

    paths = g.dijkstra("A")
    assert paths["A"][0] == 0.0
    assert paths["C"][0] == 2.0
    assert paths["B"][0] == 4.0  # direct edge A -> B is 4, A -> C -> B not possible in directed graph unless edge exists
    assert paths["D"][0] == 9.0  # A -> B -> D (4 + 5 = 9) vs A -> C -> D (2 + 8 = 10)


def test_graph_topological_sort():
    g = Graph()
    g.add_edge("5", "2")
    g.add_edge("5", "0")
    g.add_edge("4", "0")
    g.add_edge("4", "1")
    g.add_edge("2", "3")
    g.add_edge("3", "1")

    order = g.topological_sort()
    assert len(order) == 6
    assert order.index("5") < order.index("2")
    assert order.index("2") < order.index("3")
    assert order.index("3") < order.index("1")


def test_graph_cycle_detection():
    g = Graph()
    g.add_edge("A", "B")
    g.add_edge("B", "C")
    g.add_edge("C", "A")

    with pytest.raises(ValueError, match="Graph contains a directed cycle"):
        g.topological_sort()


def test_lzw_compression():
    text = "NouGenAi NouGenMorph Valerion Substrate Shards Fleet Mesh 2026 " * 8
    compressed = LZWCompressor.compress(text)
    decompressed = LZWCompressor.decompress(compressed)
    assert decompressed == text
    assert len(compressed) < len(text)


def test_algorithm_catalog_and_benchmark():
    all_algos = list_algorithms()
    assert len(all_algos) >= 8

    search_algos = list_algorithms("searches")
    assert all(a["category"] == "searches" for a in search_algos)

    dijkstra = get_algorithm("dijkstra")
    assert dijkstra is not None
    assert dijkstra["name"] == "Dijkstra Shortest Path"

    bm = benchmark_algorithm("levenshtein", iterations=50)
    assert "ops_per_sec" in bm
    assert bm["iterations"] == 50
    assert "error" not in bm


def test_algorithm_ingest():
    count = ingest_algorithm_shards(db_index=5)
    assert isinstance(count, int)
    assert count >= 0


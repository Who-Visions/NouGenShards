"""memory_fuzz: a correct retriever passes, deliberately broken ones are CAUGHT, runs replay."""
from nougen_shards import memory_fuzz as F

MEM = [{"id": "relay", "text": "relay watcher blind on phoebus registry diverged"},
       {"id": "disk", "text": "blade disk full c drive zero bytes free"},
       {"id": "arxiv", "text": "arxiv paper fulltext returns bounded text"},
       {"id": "gull", "text": "a gull landed on the antenna"},
       {"id": "tracker", "text": "tracker dailies published for whoart"}]
Q = "relay registry blind phoebus"


def test_correct_retriever_passes_every_case():
    r = F.run_fuzz(F.overlap_retrieve, Q, MEM, k=2, seed=1)
    assert r["baseline"][0] == "relay" and r["failures"] == [], r["failures"]
    assert {c["case"] for c in r["cases"]} >= {"query:case", "memory:shuffle", "counterfactual:drop_top"}


def case_sensitive(query, memory, k):          # BROKEN: no lowercasing, so case flips results
    q = set(query.split())
    out = [(-len(q & set(m["text"].split())), m["id"]) for m in memory if q & set(m["text"].split())]
    return [i for _, i in sorted(out)[:k]]


def order_dependent(query, memory, k):         # BROKEN: ties resolved by position, not content
    q = set(query.lower().split())
    hits = [m["id"] for m in memory if q & set(m["text"].lower().split())]
    return hits[:k]


def returns_dupes(query, memory, k):           # BROKEN: no dedup, a duplicated item appears twice
    q = set(query.lower().split())
    return [m["id"] for m in memory if q & set(m["text"].lower().split())][:k + 2]


def never_changes(query, memory, k):           # BROKEN: ignores memory, so the dropped item survives
    return ["relay", "disk"][:k]


TIES = [{"id": f"n{i}", "text": f"node {w}"} for i, w in enumerate("alpha beta gamma delta eps zeta".split())]


def test_the_fuzzer_catches_each_deliberately_broken_retriever():
    # order_dependent needs ties wider than k, or position never decides the result.
    cases = {"case_sensitive": (case_sensitive, "Relay registry blind phoebus", MEM, "query:case"),
             "order_dependent": (order_dependent, "node", TIES, "memory:shuffle"),
             "returns_dupes": (returns_dupes, "Relay registry blind phoebus", MEM, "memory:duplicate"),
             "never_changes": (never_changes, "Relay registry blind phoebus", MEM, "counterfactual:drop_top")}
    for name, (fn, query, memory, expected_failure) in cases.items():
        r = F.run_fuzz(fn, query, memory, k=2, seed=3)
        assert expected_failure in r["failures"], (name, r["failures"])
    assert F.run_fuzz(F.overlap_retrieve, "node", TIES, k=2, seed=3)["failures"] == []   # correct one still passes


def test_runs_replay_exactly_and_the_seed_changes_the_mutations():
    a = F.run_fuzz(F.overlap_retrieve, Q, MEM, k=2, seed=5)
    assert a == F.run_fuzz(F.overlap_retrieve, Q, MEM, k=2, seed=5)
    assert len(a["digest"]) == 64 and a["version"] == F.VERSION
    mutations = {F.mutate_query("one two three four five six", "drop_token", s) for s in range(20)}
    assert len(mutations) > 1


def test_divergence_is_one_minus_jaccard():
    assert F.divergence(["a", "b"], ["a", "b"]) == 0.0
    assert F.divergence(["a"], ["b"]) == 1.0
    assert F.divergence(["a", "b"], ["b", "c"]) == 1 - 1 / 3
    assert F.divergence([], []) == 0.0


def test_mutations_are_deterministic_and_unknown_kinds_are_rejected():
    import pytest
    assert F.mutate_query("a b c d", "swap_adjacent", 9) == F.mutate_query("a b c d", "swap_adjacent", 9)
    assert F.mutate_memory(MEM, "shuffle", 4) == F.mutate_memory(MEM, "shuffle", 4)
    assert [m["id"] for m in F.mutate_memory(MEM, "drop_top", 0, protect=["relay"])] == \
        ["disk", "arxiv", "gull", "tracker"]
    with pytest.raises(ValueError):
        F.mutate_query("a b", "teleport", 0)
    with pytest.raises(ValueError):
        F.mutate_memory(MEM, "teleport", 0)

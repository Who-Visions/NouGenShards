import pytest
from nougen_shards import fitness_corpus as fc


@pytest.fixture
def setup_anchor(tmp_path):
    corpus = fc.FitnessCorpus(tmp_path / "cases.jsonl")
    keys = fc.EpochKeys(tmp_path / "keys.json")
    for i in range(500):
        corpus.add(f"failure mode {i}", {"kind": "probe", "n": i}, f"source:{i}")
    return corpus, keys


def test_anchor_set_retains_cases_across_epoch(setup_anchor):
    corpus, keys = setup_anchor
    ev1 = fc.Evaluator(corpus, keys, "epoch-1", fraction=0.4, min_sealed=10)
    # By default, independent hashes will have roughly fraction overlap (0.4 * 0.4 = 0.16 or variable)
    # Specifying min_anchor_overlap=0.10 should succeed given standard binomial expectation
    ev2 = fc.Evaluator(corpus, keys, "epoch-2", fraction=0.4, min_sealed=10,
                       anchor_from=ev1, min_anchor_overlap=0.05)
    anchors = ev2.anchor_cases()
    assert len(anchors) > 0
    sealed_1 = {c.case_id for c in ev1.sealed_cases()}
    sealed_2 = {c.case_id for c in ev2.sealed_cases()}
    for a in anchors:
        assert a.case_id in sealed_1
        assert a.case_id in sealed_2


def test_anchor_set_refuses_insufficient_overlap(setup_anchor):
    corpus, keys = setup_anchor
    ev1 = fc.Evaluator(corpus, keys, "epoch-1", fraction=0.4, min_sealed=10)
    # Demanding 99% overlap across independent pseudorandom splits must be refused
    with pytest.raises(ValueError, match="anchor overlap is refused"):
        fc.Evaluator(corpus, keys, "epoch-2", fraction=0.4, min_sealed=10,
                     anchor_from=ev1, min_anchor_overlap=0.99)

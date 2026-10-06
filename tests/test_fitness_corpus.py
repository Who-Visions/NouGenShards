import json

import pytest

from nougen_shards import fitness_corpus as fc


@pytest.fixture
def setup(tmp_path):
    corpus = fc.FitnessCorpus(tmp_path / "cases.jsonl")
    keys = fc.EpochKeys(tmp_path / "keys.json")
    for i in range(200):
        corpus.add(f"incident {i}", {"kind": "probe", "n": i}, f"leg:{i}")
    return corpus, keys, tmp_path


def test_add_dedupes_by_content(tmp_path):
    corpus = fc.FitnessCorpus(tmp_path / "c.jsonl")
    a = corpus.add("Same Thing", {"kind": "x"}, "s1")
    b = corpus.add("same thing ", {"kind": "x"}, "s2")
    assert a.case_id == b.case_id
    assert corpus.count() == 1


def test_split_is_deterministic_and_near_fraction(setup):
    corpus, keys, _ = setup
    ev1 = fc.Evaluator(corpus, keys, "e1", fraction=0.4, min_sealed=1)
    ev2 = fc.Evaluator(corpus, keys, "e1", fraction=0.4, min_sealed=1)
    sealed = {c.case_id for c in ev1.sealed_cases()}
    assert sealed == {c.case_id for c in ev2.sealed_cases()}
    assert 0.28 <= len(sealed) / 200 <= 0.52


def test_search_view_never_exposes_sealed(setup):
    corpus, keys, _ = setup
    ev = fc.Evaluator(corpus, keys, "e1", fraction=0.4, min_sealed=1)
    view = ev.search_view()
    sealed = {c.case_id for c in ev.sealed_cases()}
    visible = {c.case_id for c in view.cases()}
    assert visible.isdisjoint(sealed)
    assert visible | sealed == {c.case_id for c in corpus._iter_all()}
    assert not any(view.is_search_case(s) for s in sealed)
    assert all(view.is_search_case(v) for v in visible)
    assert not view.is_search_case("not-a-case")
    assert not hasattr(view, "sealed_cases")


def test_new_epoch_reshuffles_split(setup):
    corpus, keys, _ = setup
    a = {c.case_id for c in fc.Evaluator(corpus, keys, "e1", min_sealed=1).sealed_cases()}
    b = {c.case_id for c in fc.Evaluator(corpus, keys, "e2", min_sealed=1).sealed_cases()}
    assert a != b


def test_split_unpredictable_without_key(setup):
    corpus, keys, tmp = setup
    ev = fc.Evaluator(corpus, keys, "e1", min_sealed=1)
    other = fc.Evaluator(corpus, fc.EpochKeys(tmp / "other.json"), "e1", min_sealed=1)
    assert {c.case_id for c in ev.sealed_cases()} != {c.case_id for c in other.sealed_cases()}
    assert "e1" in json.loads((tmp / "keys.json").read_text())


def test_epoch_hash_commits_to_membership(setup):
    corpus, keys, _ = setup
    ev = fc.Evaluator(corpus, keys, "e1", min_sealed=1)
    h = ev.epoch_hash()
    assert h == fc.Evaluator(corpus, keys, "e1", min_sealed=1).epoch_hash()
    for i in range(50):
        corpus.add(f"late {i}", {"kind": "late", "n": i}, "x")
    assert ev.epoch_hash() != h


def test_gate_refuses_on_too_few_sealed(tmp_path):
    corpus = fc.FitnessCorpus(tmp_path / "c.jsonl")
    keys = fc.EpochKeys(tmp_path / "k.json")
    n = fc.seed_from(corpus, fc.SEED_2026_10_04)
    assert n == len(fc.SEED_2026_10_04)
    assert not fc.Evaluator(corpus, keys, "e1", min_sealed=30).gate_ready()


def test_min_sealed_and_fraction_from_env(setup, monkeypatch):
    corpus, keys, _ = setup
    monkeypatch.setenv("NOUGEN_FITNESS_MIN_SEALED", "5")
    monkeypatch.setenv("NOUGEN_FITNESS_SEALED_FRACTION", "0.5")
    ev = fc.Evaluator(corpus, keys, "e1")
    assert ev.min_sealed == 5 and ev.fraction == 0.5 and ev.gate_ready()
    with pytest.raises(ValueError):
        fc.Evaluator(corpus, keys, "e1", fraction=1.0)


def test_missing_epoch_key_is_not_silently_created(tmp_path):
    with pytest.raises(KeyError):
        fc.EpochKeys(tmp_path / "k.json").get("nope")


def test_gate_config_uses_sealed_split(setup):
    from nougen_shards.fitness_gate import dataset_hash
    corpus, keys, _ = setup
    ev = fc.Evaluator(corpus, keys, "e1", fraction=0.4, min_sealed=30)
    cfg = fc.gate_config(ev, evaluator_hash="eval-v1", budget=4)
    sealed = sorted(c.case_id for c in ev.sealed_cases())
    assert list(cfg.sealed_case_ids) == sealed
    assert cfg.epoch == "e1"
    assert dataset_hash(cfg.sealed_case_ids) == dataset_hash(sealed)
    visible = {c.case_id for c in ev.search_view().cases()}
    assert visible.isdisjoint(cfg.sealed_case_ids)


def test_gate_config_refuses_when_not_ready(tmp_path):
    corpus = fc.FitnessCorpus(tmp_path / "c.jsonl")
    fc.seed_from(corpus, fc.SEED_2026_10_04)
    ev = fc.Evaluator(corpus, fc.EpochKeys(tmp_path / "k.json"), "e1")
    with pytest.raises(ValueError, match="not gate-ready"):
        fc.gate_config(ev, evaluator_hash="eval-v1", budget=4)

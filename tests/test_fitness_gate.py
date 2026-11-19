import random
from math import isclose

import pytest

from nougen_shards.fitness_gate import FitnessGate, GateConfig, dataset_hash, sign_test_p
from nougen_shards.rsi_evaluation_ledger import BudgetExhausted, EvaluationLedger

IDS = tuple(f"case{i}" for i in range(300))


def make(tmp_path, budget=10, alpha=0.05, ids=IDS, evaluator="eval-v1", epoch="e1"):
    return FitnessGate(EvaluationLedger(tmp_path / "ledger.db"), GateConfig(epoch, evaluator, ids, budget, alpha))


def args(i):
    return dict(candidate_hash=f"c{i}", lineage="L", parent_hash="p", task_hash="t", environment_hash="env")


def scorer(rng, p_win, p_lose):
    """Per-case (candidate, baseline) outcome: win with p_win, lose with p_lose, else tie."""
    def score(_case):
        r = rng.random()
        return (1.0, 0.0) if r < p_win else (0.0, 1.0) if r < p_win + p_lose else (0.5, 0.5)
    return score


def test_sign_test_is_exact():
    assert isclose(sign_test_p(5, 0), 1 / 32)
    assert isclose(sign_test_p(3, 2), (10 + 5 + 1) / 32)
    assert sign_test_p(0, 0) == 1.0


def test_familywise_false_promotion_rate_on_null_candidates(tmp_path):
    """Candidates with no true gain: P(any promotion per epoch) must stay <= alpha (+ Monte Carlo slack)."""
    rng, epochs, promoted_epochs = random.Random(7), 400, 0
    for e in range(epochs):
        gate = FitnessGate(EvaluationLedger(tmp_path / f"l{e}.db"), GateConfig(f"e{e}", "ev", IDS, 10, 0.05))
        if any(gate.promote(**args(i), score=scorer(rng, 0.1, 0.1)) for i in range(10)):
            promoted_epochs += 1
    assert promoted_epochs / epochs <= 0.08


def test_naive_search_set_gate_false_promotes_adaptively_chosen_nulls():
    """The failure the sealed gate prevents: best-of-K nulls picked on the search set look better there."""
    rng, trials, fooled = random.Random(11), 1000, 0
    for _ in range(trials):
        best_search = max(sum(rng.random() < 0.5 for _ in range(40)) for _ in range(8))
        fooled += best_search > 20      # naive gate: search score above the 20/40 baseline
    assert fooled / trials > 0.10


def test_real_effect_is_promoted(tmp_path):
    rng, hits, runs = random.Random(3), 0, 50
    for e in range(runs):
        gate = FitnessGate(EvaluationLedger(tmp_path / f"r{e}.db"), GateConfig(f"e{e}", "ev", IDS, 10, 0.05))
        hits += gate.promote(**args(0), score=scorer(rng, 0.20, 0.05))     # net +15 points
    assert hits / runs >= 0.8


def test_budget_plus_one_is_refused(tmp_path):
    gate, rng = make(tmp_path, budget=2), random.Random(1)
    for i in range(2):
        gate.promote(**args(i), score=scorer(rng, 0.1, 0.1))
    with pytest.raises(BudgetExhausted):
        gate.promote(**args(99), score=scorer(rng, 0.1, 0.1))


def test_duplicate_request_replays_without_spending_or_rescoring(tmp_path):
    gate, calls = make(tmp_path, budget=2), []
    def score(c):
        calls.append(c); return (1.0, 0.0)
    first = gate.promote(**args(0), score=score)
    n = len(calls)
    assert gate.promote(**args(0), score=score) is first and len(calls) == n
    assert gate.ledger.spent("e1") == 1


def test_changed_evaluator_or_dataset_cannot_reopen_epoch(tmp_path):
    make(tmp_path)
    with pytest.raises(ValueError):
        make(tmp_path, evaluator="eval-v2")                      # evaluator edited mid-epoch
    with pytest.raises(ValueError):
        make(tmp_path, ids=IDS[:-1] + ("swapped",))              # sealed set edited mid-epoch


def test_scoring_crash_keeps_the_query_spent(tmp_path):
    gate = make(tmp_path, budget=3)
    def boom(_c):
        raise RuntimeError("scorer died")
    with pytest.raises(RuntimeError):
        gate.promote(**args(0), score=boom)
    assert gate.ledger.spent("e1") == 1


def test_only_a_bool_leaves_the_gate(tmp_path):
    gate = make(tmp_path)
    out = gate.promote(**args(0), score=scorer(random.Random(5), 0.3, 0.0))
    assert type(out) is bool and gate.ledger.feedback(
        __import__("nougen_shards.rsi_evaluation_ledger", fromlist=["EvaluationContext"]).EvaluationContext(
            "e1", "eval-v1", dataset_hash(IDS), "p", "t", "env"), "c0") is out


@pytest.mark.parametrize("kwargs,msg", [
    (dict(ids=IDS[:10]), "at least"),
    (dict(ids=("a",) * 40), "unique"),
    (dict(alpha=0), "alpha"),
    (dict(budget=0), "budget"),
])
def test_bad_config_is_rejected(tmp_path, kwargs, msg):
    with pytest.raises(ValueError, match=msg):
        make(tmp_path, **kwargs)

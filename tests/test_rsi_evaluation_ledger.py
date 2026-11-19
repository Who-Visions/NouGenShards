"""Acceptance tests for evaluator accounting under concurrent and failed work."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import multiprocessing
import os

import pytest

from nougen_shards.rsi_evaluation_ledger import (
    BudgetExhausted, EvaluationContext, EvaluationLedger, EvaluationPending,
)


CONTEXT = EvaluationContext("epoch-1", "eval", "sealed", "parent", "task", "env")


@pytest.fixture
def ledger(tmp_path):
    result = EvaluationLedger(tmp_path / "private" / "ledger.db")
    result.start_epoch("epoch-1", "eval", "sealed", 7)
    return result


def test_concurrent_lineages_share_one_budget(ledger):
    def attempt(i):
        worker = EvaluationLedger(ledger.path)
        try:
            return worker.reserve(CONTEXT, f"candidate-{i}", f"lineage-{i % 3}")
        except BudgetExhausted:
            return None

    with ThreadPoolExecutor(max_workers=12) as workers:
        receipts = list(workers.map(attempt, range(40)))
    assert sum(r is not None for r in receipts) == 7
    assert ledger.spent("epoch-1") == 7


def test_concurrent_duplicate_spends_once(ledger):
    def attempt(i):
        try:
            return EvaluationLedger(ledger.path).reserve(CONTEXT, "same", str(i))
        except EvaluationPending:
            return None

    with ThreadPoolExecutor(max_workers=8) as workers:
        receipts = list(workers.map(attempt, range(16)))
    assert sum(r is not None for r in receipts) == 1
    assert ledger.spent("epoch-1") == 1


def test_duplicate_replays_across_lineages_after_exhaustion(ledger):
    first = ledger.reserve(CONTEXT, "same", "A")
    assert ledger.feedback(CONTEXT, "same") is None
    ledger.finish(first, False)
    for i in range(6):
        ledger.reserve(CONTEXT, str(i), "B")
    replay = ledger.reserve(CONTEXT, "same", "C")
    assert replay.cached and replay.decision is False
    assert ledger.feedback(CONTEXT, "same") is False
    assert ledger.spent("epoch-1") == 7


def _crash_after_reservation(path):
    EvaluationLedger(path).reserve(CONTEXT, "crashed", "child")
    os._exit(19)


def test_process_crash_keeps_reservation_spent(ledger):
    child = multiprocessing.get_context("spawn").Process(
        target=_crash_after_reservation, args=(ledger.path,)
    )
    child.start()
    child.join(20)
    if child.is_alive():
        child.terminate()
        child.join()
        pytest.fail("Crash worker timed out")
    assert child.exitcode == 19
    reopened = EvaluationLedger(ledger.path)
    assert reopened.spent("epoch-1") == 1
    with pytest.raises(EvaluationPending):
        reopened.reserve(CONTEXT, "crashed", "retry")
    assert reopened.spent("epoch-1") == 1
    assert reopened.feedback(CONTEXT, "crashed") is None


def test_restart_cannot_refill_or_change_epoch(ledger):
    ledger.reserve(CONTEXT, "one", "A")
    reopened = EvaluationLedger(ledger.path)
    reopened.start_epoch("epoch-1", "eval", "sealed", 7)
    assert reopened.spent("epoch-1") == 1
    for args in [("eval", "sealed", 8), ("changed", "sealed", 7),
                 ("eval", "other-data", 7)]:
        with pytest.raises(ValueError, match="immutable"):
            reopened.start_epoch("epoch-1", *args)


@pytest.mark.parametrize("field", ["evaluator_hash", "dataset_hash", "epoch"])
def test_epoch_hash_mismatch_refused_without_spend(ledger, field):
    with pytest.raises(ValueError):
        ledger.reserve(replace(CONTEXT, **{field: "changed"}), "candidate", "A")
    assert ledger.spent("epoch-1") == 0


@pytest.mark.parametrize("field", ["parent_hash", "task_hash", "environment_hash"])
def test_new_context_gets_distinct_receipt_and_no_unrelated_blacklist(ledger, field):
    other = replace(CONTEXT, **{field: "different"})
    ledger.add_search_constraint(CONTEXT, "mutation", "reproducer", source="search")
    assert ledger.blocked(CONTEXT, "mutation")
    assert not ledger.blocked(other, "mutation")
    first = ledger.reserve(CONTEXT, "candidate", "A")
    second = ledger.reserve(other, "candidate", "B")
    assert first.receipt_id != second.receipt_id
    assert ledger.spent("epoch-1") == 2


def test_only_search_failures_enter_shared_constraints(ledger):
    for source in ["sealed", "unknown"]:
        with pytest.raises(ValueError, match="search-set"):
            ledger.add_search_constraint(CONTEXT, "mutation", "proof", source=source)
    with pytest.raises(ValueError, match="required"):
        ledger.add_search_constraint(CONTEXT, "mutation", "", source="search")
    assert not ledger.blocked(CONTEXT, "mutation")


def test_feedback_accepts_only_a_bit_and_completion_is_owned_and_immutable(ledger):
    first = ledger.reserve(CONTEXT, "candidate", "A")
    for outcome in [1, "sealed-case-42", {"case_id": "secret", "score": 0.9}]:
        with pytest.raises(ValueError, match="boolean"):
            ledger.finish(first, outcome)
    with pytest.raises(ValueError, match="Invalid reservation"):
        ledger.finish(replace(first, token="not-owner"), True)
    assert ledger.finish(first, True) is True
    assert ledger.finish(first, True) is True
    with pytest.raises(ValueError, match="immutable"):
        ledger.finish(first, False)
    assert ledger.feedback(CONTEXT, "candidate") is True
    with pytest.raises(ValueError, match="Cached"):
        ledger.finish(ledger.reserve(CONTEXT, "candidate", "B"), True)
    assert ledger.spent("epoch-1") == 1


def test_zero_budget_refuses_first_query(tmp_path):
    ledger = EvaluationLedger(tmp_path / "zero.db")
    ledger.start_epoch("epoch-1", "eval", "sealed", 0)
    with pytest.raises(BudgetExhausted):
        ledger.reserve(CONTEXT, "candidate", "A")
    assert ledger.spent("epoch-1") == 0

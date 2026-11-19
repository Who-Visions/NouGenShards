"""Sealed-holdout promotion gate: the decision rule on top of ``rsi_evaluation_ledger``.

A candidate is promoted only if it beats the baseline on a sealed case set by an exact one-sided
sign test at alpha / budget. The ledger caps sealed queries per epoch at ``budget`` and exposes only
the promotion bit, so by a union bound the chance that *any* no-better candidate is promoted in an
epoch is <= alpha, even when candidates were chosen adaptively from search-set feedback
(arXiv 2609.33180 measures that failure at up to 20.7% for gates that reuse their benchmark).
Per-case sealed results and p-values never leave this module; the caller gets a bool.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from math import comb
from typing import Callable, Sequence

from .rsi_evaluation_ledger import EvaluationContext, EvaluationLedger

MIN_SEALED_CASES = 30
EPS = 1e-12


def dataset_hash(sealed_case_ids: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(sorted(sealed_case_ids)).encode()).hexdigest()


def sign_test_p(wins: int, losses: int) -> float:
    """Exact one-sided p-value: P(X >= wins | wins+losses fair coin flips). Ties are dropped."""
    n = wins + losses
    if n == 0:
        return 1.0
    return sum(comb(n, k) for k in range(wins, n + 1)) / 2 ** n


@dataclass(frozen=True)
class GateConfig:
    epoch: str
    evaluator_hash: str
    sealed_case_ids: tuple
    budget: int
    alpha: float = 0.05

    def __post_init__(self) -> None:
        if not 0 < self.alpha < 1:
            raise ValueError("alpha must be in (0, 1)")
        if len(set(self.sealed_case_ids)) != len(self.sealed_case_ids):
            raise ValueError("sealed case ids must be unique")
        if len(self.sealed_case_ids) < MIN_SEALED_CASES:
            raise ValueError(f"need at least {MIN_SEALED_CASES} sealed cases")
        if type(self.budget) is not int or self.budget < 1:
            raise ValueError("budget must be a positive integer")
        if 0.5 ** len(self.sealed_case_ids) > self.alpha_per_query:
            raise ValueError("sealed set too small: even winning every case could not promote")

    @property
    def alpha_per_query(self) -> float:
        return self.alpha / self.budget


class FitnessGate:
    def __init__(self, ledger: EvaluationLedger, config: GateConfig) -> None:
        self.ledger, self.config = ledger, config
        # raises if the epoch already exists with a different evaluator, dataset or budget
        ledger.start_epoch(config.epoch, config.evaluator_hash,
                           dataset_hash(config.sealed_case_ids), config.budget)

    def promote(
        self,
        candidate_hash: str,
        lineage: str,
        parent_hash: str,
        task_hash: str,
        environment_hash: str,
        score: Callable[[str], tuple],
    ) -> bool:
        """``score(case_id) -> (candidate_score, baseline_score)`` runs inside the evaluator only.

        Reserves a sealed query first (BudgetExhausted / EvaluationPending propagate), replays an
        identical completed evaluation, and leaves the reservation spent if scoring raises.
        """
        cfg = self.config
        context = EvaluationContext(cfg.epoch, cfg.evaluator_hash, dataset_hash(cfg.sealed_case_ids),
                                    parent_hash, task_hash, environment_hash)
        reservation = self.ledger.reserve(context, candidate_hash, lineage)
        if reservation.cached:
            return bool(reservation.decision)
        wins = losses = 0
        for case_id in cfg.sealed_case_ids:
            candidate, baseline = score(case_id)
            if candidate > baseline + EPS:
                wins += 1
            elif baseline > candidate + EPS:
                losses += 1
        return self.ledger.finish(reservation, sign_test_p(wins, losses) <= cfg.alpha_per_query)

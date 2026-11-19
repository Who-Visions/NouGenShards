"""Dream-RSI Replay Simulator & Dynamic Portfolio Scheduler.

Implements the core primitives from Dream-RSI (arXiv:2609.14858):
1. HistoryReplaySimulator: Uses historical discovery trees (attempts, stdout, exit codes,
   evaluation outcomes) to simulate exploration off-policy with zero execution cost.
2. DynamicPortfolioScheduler: Builds dynamic batch portfolios across three roles:
   - EXPLOITATION: Refinement of high-scoring candidates.
   - EXPLORATION: Unexplored or novel candidate branches.
   - RECOVERY: Repairable failures with evidence-adapted priority.
3. PrefixObserver: Enforces causal prefix visibility (step t sees strictly history < t).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


class CandidateRole(str, Enum):
    EXPLOITATION = "exploitation"
    EXPLORATION = "exploration"
    RECOVERY = "recovery"


@dataclass(frozen=True)
class DiscoveryAttempt:
    """A recorded node in the historical discovery tree."""
    attempt_id: str
    parent_id: Optional[str]
    code: str
    code_hash: str
    exit_code: int
    score: float
    is_success: bool
    repairable: bool
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        attempt_id: str,
        code: str,
        exit_code: int,
        score: float,
        parent_id: Optional[str] = None,
        repairable: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DiscoveryAttempt:
        code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
        is_success = (exit_code == 0) and (score > 0.0)
        return cls(
            attempt_id=attempt_id,
            parent_id=parent_id,
            code=code,
            code_hash=code_hash,
            exit_code=exit_code,
            score=score,
            is_success=is_success,
            repairable=repairable,
            metadata=metadata or {},
        )


@dataclass
class SimulationResult:
    """Scoreboard output of an offline replay dreaming session."""
    total_steps: int
    traversed_ids: List[str]
    max_score: float
    best_attempt_id: Optional[str]
    portfolio_counts: Dict[str, int]
    execution_cost: float = 0.0  # Zero cost in simulator


class PrefixObserver:
    """Enforces prefix-only visibility: policies cannot inspect future tree nodes."""

    def __init__(self, full_history: Sequence[DiscoveryAttempt]) -> None:
        self._history: List[DiscoveryAttempt] = list(full_history)
        self._cursor: int = 0

    @property
    def total_count(self) -> int:
        return len(self._history)

    def has_next(self) -> bool:
        return self._cursor < len(self._history)

    def observed_prefix(self) -> List[DiscoveryAttempt]:
        """Returns the slice of attempts revealed up to the current step."""
        return self._history[: self._cursor]

    def advance(self, count: int = 1) -> List[DiscoveryAttempt]:
        start = self._cursor
        self._cursor = min(self._cursor + count, len(self._history))
        return self._history[start : self._cursor]

    def reset(self) -> None:
        self._cursor = 0


class DynamicPortfolioScheduler:
    """Constructs dynamic candidate batches across exploitation, exploration, and recovery."""

    def __init__(self, max_parallelism: int = 4) -> None:
        if max_parallelism < 1:
            raise ValueError("max_parallelism must be at least 1")
        self.max_parallelism = max_parallelism

    def select_batch(
        self,
        prefix: Sequence[DiscoveryAttempt],
        closed_set: Set[str],
    ) -> List[Tuple[DiscoveryAttempt, CandidateRole]]:
        """Allocates slots dynamically according to prefix evidence without rigid quotas."""
        eligible = [a for a in prefix if a.attempt_id not in closed_set]
        if not eligible:
            return []

        # Partition candidates
        exploit_pool = [a for a in eligible if a.is_success]
        recovery_pool = [a for a in eligible if (not a.is_success and a.repairable)]
        explore_pool = [a for a in eligible if a.parent_id is None or a.score == 0.0]

        # Sort pools
        exploit_pool.sort(key=lambda a: a.score, reverse=True)
        recovery_pool.sort(key=lambda a: a.score, reverse=True)

        batch: List[Tuple[DiscoveryAttempt, CandidateRole]] = []
        assigned_ids: Set[str] = set()

        # 1. Provide at most 1 recovery slot if repairable candidates exist
        if recovery_pool:
            target = recovery_pool[0]
            batch.append((target, CandidateRole.RECOVERY))
            assigned_ids.add(target.attempt_id)

        # 2. Allocate exploration slot if available
        for exp in explore_pool:
            if exp.attempt_id not in assigned_ids and len(batch) < self.max_parallelism:
                batch.append((exp, CandidateRole.EXPLORATION))
                assigned_ids.add(exp.attempt_id)
                break

        # 3. Fill remaining slots with top exploitation candidates
        for exp in exploit_pool:
            if exp.attempt_id not in assigned_ids and len(batch) < self.max_parallelism:
                batch.append((exp, CandidateRole.EXPLOITATION))
                assigned_ids.add(exp.attempt_id)

        # 4. If slots remain, fill with any remaining eligible candidates
        for rem in eligible:
            if rem.attempt_id not in assigned_ids and len(batch) < self.max_parallelism:
                role = (
                    CandidateRole.EXPLOITATION
                    if rem.is_success
                    else (CandidateRole.RECOVERY if rem.repairable else CandidateRole.EXPLORATION)
                )
                batch.append((rem, role))
                assigned_ids.add(rem.attempt_id)

        return batch


class HistoryReplaySimulator:
    """Zero-execution-cost world model evaluating exploration policies on historical discovery trees."""

    def __init__(self, history: Sequence[DiscoveryAttempt]) -> None:
        self._history: List[DiscoveryAttempt] = list(history)
        self._node_map: Dict[str, DiscoveryAttempt] = {a.attempt_id: a for a in self._history}

    @classmethod
    def from_json(cls, json_str: str) -> HistoryReplaySimulator:
        data = json.loads(json_str)
        attempts = [
            DiscoveryAttempt.create(
                attempt_id=item["attempt_id"],
                code=item["code"],
                exit_code=item.get("exit_code", 0),
                score=item.get("score", 0.0),
                parent_id=item.get("parent_id"),
                repairable=item.get("repairable", False),
                metadata=item.get("metadata", {}),
            )
            for item in data
        ]
        return cls(attempts)

    def dream(
        self,
        scheduler: Optional[DynamicPortfolioScheduler] = None,
        max_steps: Optional[int] = None,
    ) -> SimulationResult:
        """Simulates an exploration policy over the stored discovery tree prefix."""
        sched = scheduler or DynamicPortfolioScheduler()
        observer = PrefixObserver(self._history)
        closed_set: Set[str] = set()
        traversed: List[str] = []
        portfolio_counts: Dict[str, int] = {
            CandidateRole.EXPLOITATION.value: 0,
            CandidateRole.EXPLORATION.value: 0,
            CandidateRole.RECOVERY.value: 0,
        }

        best_score = float("-inf")
        best_id: Optional[str] = None
        steps = 0

        # Prime the observer with initial candidates up to max_parallelism
        observer.advance(max(1, sched.max_parallelism))

        while (observer.has_next() or len(closed_set) < len(self._history)) and (max_steps is None or steps < max_steps):
            prefix = observer.observed_prefix()
            batch = sched.select_batch(prefix, closed_set)
            if not batch:
                if observer.has_next():
                    observer.advance(max(1, sched.max_parallelism))
                    continue
                break

            for attempt, role in batch:
                closed_set.add(attempt.attempt_id)
                traversed.append(attempt.attempt_id)
                portfolio_counts[role.value] += 1
                if attempt.score > best_score:
                    best_score = attempt.score
                    best_id = attempt.attempt_id

            if observer.has_next():
                observer.advance(max(1, len(batch)))
            steps += 1

        final_max = best_score if best_id is not None else 0.0
        return SimulationResult(
            total_steps=steps,
            traversed_ids=traversed,
            max_score=final_max,
            best_attempt_id=best_id,
            portfolio_counts=portfolio_counts,
            execution_cost=0.0,
        )

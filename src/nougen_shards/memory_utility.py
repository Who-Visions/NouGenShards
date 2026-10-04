"""Measured memory utility: does a recalled shard change the outcome?

Offline leave-one-out ablation on sealed corpus cases. For each case the
evaluator runs the solver once with its full recall set (baseline) and once per
shard with that shard withheld. MV(s) is the mean paired difference
baseline - withheld across cases where s was recalled; a sign test says whether
it is distinguishable from zero. Results feed mark_utility as measured evidence
instead of agent self-report.

Leakage rule: a shard authored at or after its case was created may contain the
answer, so its runs are excluded. This module records and scores runs; it never
writes to the vault.
"""

from __future__ import annotations

import math
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class ShardUtility:
    shard_id: str
    n: int
    mv: float
    helped: int
    hurt: int
    p_value: float
    tokens: int

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05


def sign_test(helped: int, hurt: int) -> float:
    """Two-sided exact sign test; ties are dropped by the caller."""
    n = helped + hurt
    if n == 0:
        return 1.0
    k = min(helped, hurt)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


class MemoryUtilityLedger:
    """Evaluator-owned record of baseline and withheld-shard runs."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    epoch TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    withheld TEXT NOT NULL,          -- '' for the full-recall baseline
                    outcome INTEGER NOT NULL CHECK (outcome IN (0, 1)),
                    PRIMARY KEY (epoch, case_id, withheld)
                );
                CREATE TABLE IF NOT EXISTS recalls (
                    epoch TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    shard_id TEXT NOT NULL,
                    rank INTEGER NOT NULL,
                    tokens INTEGER NOT NULL CHECK (tokens >= 0),
                    leaked INTEGER NOT NULL CHECK (leaked IN (0, 1)),
                    PRIMARY KEY (epoch, case_id, shard_id)
                );
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            yield db
        finally:
            db.close()

    def record_recall(
        self,
        epoch: str,
        case_id: str,
        shards: list[tuple[str, int, float]],
        case_created: float,
    ) -> None:
        """shards: (shard_id, tokens, shard_created_epoch_seconds) in rank order."""
        with self._connect() as db:
            db.executemany(
                "INSERT OR REPLACE INTO recalls VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (epoch, case_id, sid, rank, int(tokens), 1 if created >= case_created else 0)
                    for rank, (sid, tokens, created) in enumerate(shards)
                ],
            )

    def record_run(self, epoch: str, case_id: str, outcome: bool, withheld: str | None = None) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?)",
                (epoch, case_id, withheld or "", 1 if outcome else 0),
            )

    def utilities(self, *, epoch: str | None = None) -> dict[str, ShardUtility]:
        sql = """
            SELECT r.shard_id, b.outcome - w.outcome, r.tokens
            FROM recalls r
            JOIN runs b ON b.epoch = r.epoch AND b.case_id = r.case_id AND b.withheld = ''
            JOIN runs w ON w.epoch = r.epoch AND w.case_id = r.case_id AND w.withheld = r.shard_id
            WHERE r.leaked = 0
        """
        args: list = []
        if epoch is not None:
            sql += " AND r.epoch = ?"
            args.append(epoch)
        acc: dict[str, list[tuple[int, int]]] = {}
        with self._connect() as db:
            for sid, diff, tokens in db.execute(sql, args):
                acc.setdefault(sid, []).append((diff, tokens))
        out = {}
        for sid, rows in acc.items():
            diffs = [d for d, _ in rows]
            helped = sum(1 for d in diffs if d > 0)
            hurt = sum(1 for d in diffs if d < 0)
            out[sid] = ShardUtility(
                shard_id=sid,
                n=len(diffs),
                mv=sum(diffs) / len(diffs),
                helped=helped,
                hurt=hurt,
                p_value=sign_test(helped, hurt),
                tokens=sum(t for _, t in rows),
            )
        return out

    def efficiency(self, *, epoch: str | None = None) -> float:
        """ME = sum of positive MV per loaded token (non-leaked recalls only)."""
        u = self.utilities(epoch=epoch)
        tokens = sum(x.tokens for x in u.values())
        return sum(max(x.mv, 0.0) for x in u.values()) / tokens if tokens else 0.0

    def utility_marks(
        self, *, min_n: int = 5, alpha: float = 0.05, epoch: str | None = None
    ) -> dict[str, float]:
        """Shard -> utility delta for mark_utility, only where the evidence is significant.

        Significance is Bonferroni-corrected over every shard tested, so with 20
        shards each needs p < 0.0025 (an all-one-way sign test over >= 10 cases).
        Returned values are MV in [-1, 1]; the caller decides how to blend them
        into utility_score. Insignificant or under-sampled shards are omitted so
        noise never moves ranking.
        """
        tested = self.utilities(epoch=epoch)
        if not tested:
            return {}
        threshold = alpha / len(tested)
        return {
            sid: x.mv
            for sid, x in tested.items()
            if x.n >= min_n and x.p_value < threshold
        }

"""Evaluator-owned query accounting and bounded feedback for RSI search.

Keep this database outside candidate sandboxes. SQLite serializes reservations
across processes on one host; fleet workers must use the same evaluator service,
not independent local copies or a database on a network filesystem. This module
accounts for queries, not statistical alpha, and does not implement fitness tests.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator
from uuid import uuid4


class BudgetExhausted(RuntimeError):
    """The shared epoch has no remaining sealed queries."""


class EvaluationPending(RuntimeError):
    """An identical evaluation already holds a reservation."""


@dataclass(frozen=True)
class EvaluationContext:
    epoch: str
    evaluator_hash: str
    dataset_hash: str
    parent_hash: str
    task_hash: str
    environment_hash: str

    def __post_init__(self) -> None:
        if any(not isinstance(v, str) or not v.strip() for v in asdict(self).values()):
            raise ValueError("Every context field must be a nonempty string")


def _digest(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class Reservation:
    receipt_id: str
    token: str | None
    decision: bool | None

    @property
    def cached(self) -> bool:
        return self.token is None


class EvaluationLedger:
    """Trusted evaluator API. Never grant candidates direct database access."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS epochs (
                    epoch TEXT PRIMARY KEY,
                    evaluator_hash TEXT NOT NULL,
                    dataset_hash TEXT NOT NULL,
                    budget INTEGER NOT NULL CHECK (budget >= 0)
                );
                CREATE TABLE IF NOT EXISTS receipts (
                    receipt_id TEXT PRIMARY KEY,
                    epoch TEXT NOT NULL REFERENCES epochs(epoch),
                    context_id TEXT NOT NULL,
                    candidate_hash TEXT NOT NULL,
                    lineage TEXT NOT NULL,
                    token TEXT NOT NULL,
                    decision INTEGER CHECK (decision IN (0, 1)),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS receipt_epoch ON receipts(epoch);
                CREATE TABLE IF NOT EXISTS search_constraints (
                    context_id TEXT NOT NULL,
                    mutation_hash TEXT NOT NULL,
                    reproducer_hash TEXT NOT NULL,
                    PRIMARY KEY (context_id, mutation_hash)
                );
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def start_epoch(
        self, epoch: str, evaluator_hash: str, dataset_hash: str, budget: int
    ) -> None:
        """Create an epoch; reopening it cannot change hashes or refill budget."""
        if any(not isinstance(v, str) or not v.strip() for v in
               (epoch, evaluator_hash, dataset_hash)):
            raise ValueError("Epoch and hashes must be nonempty strings")
        if type(budget) is not int or budget < 0:
            raise ValueError("Budget must be a nonnegative integer")
        values = (evaluator_hash, dataset_hash, budget)
        with self._transaction() as db:
            existing = db.execute(
                "SELECT evaluator_hash, dataset_hash, budget FROM epochs WHERE epoch=?",
                (epoch,),
            ).fetchone()
            if existing is not None and existing != values:
                raise ValueError("Epoch configuration is immutable")
            db.execute("INSERT OR IGNORE INTO epochs VALUES (?, ?, ?, ?)",
                       (epoch, *values))

    @staticmethod
    def receipt_id(context: EvaluationContext, candidate_hash: str) -> str:
        if not isinstance(candidate_hash, str) or not candidate_hash.strip():
            raise ValueError("Candidate hash must be a nonempty string")
        return _digest({**asdict(context), "candidate_hash": candidate_hash})

    def reserve(
        self, context: EvaluationContext, candidate_hash: str, lineage: str
    ) -> Reservation:
        """Spend before scoring. Pending/crashed reservations remain spent.

        Lineage is attribution, not part of identity: asking from another lineage
        cannot obtain a second query for the same candidate and context.
        """
        if not isinstance(lineage, str) or not lineage.strip():
            raise ValueError("Lineage must be a nonempty string")
        receipt = self.receipt_id(context, candidate_hash)
        with self._transaction() as db:
            epoch = db.execute(
                "SELECT evaluator_hash, dataset_hash, budget FROM epochs WHERE epoch=?",
                (context.epoch,),
            ).fetchone()
            if epoch is None or epoch[:2] != (context.evaluator_hash, context.dataset_hash):
                raise ValueError("Unknown epoch or evaluator/dataset hash mismatch")
            prior = db.execute("SELECT decision FROM receipts WHERE receipt_id=?",
                               (receipt,)).fetchone()
            if prior is not None:
                if prior[0] is None:
                    raise EvaluationPending(receipt)
                return Reservation(receipt, None, bool(prior[0]))
            spent = db.execute("SELECT COUNT(*) FROM receipts WHERE epoch=?",
                               (context.epoch,)).fetchone()[0]
            if spent >= epoch[2]:
                raise BudgetExhausted(context.epoch)
            token = uuid4().hex
            db.execute(
                "INSERT INTO receipts "
                "(receipt_id, epoch, context_id, candidate_hash, lineage, token) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (receipt, context.epoch, _digest(asdict(context)), candidate_hash,
                 lineage, token),
            )
            return Reservation(receipt, token, None)

    def finish(self, reservation: Reservation, decision: bool) -> bool:
        """Record only the promotion bit, never sealed case IDs or scores."""
        if type(decision) is not bool:
            raise ValueError("Only a boolean promotion decision is permitted")
        if reservation.token is None:
            raise ValueError("Cached feedback cannot complete a reservation")
        with self._transaction() as db:
            prior = db.execute(
                "SELECT decision FROM receipts WHERE receipt_id=? AND token=?",
                (reservation.receipt_id, reservation.token),
            ).fetchone()
            if prior is None:
                raise ValueError("Invalid reservation")
            if prior[0] is not None and bool(prior[0]) != decision:
                raise ValueError("Evaluation decision is immutable")
            db.execute("UPDATE receipts SET decision=? WHERE receipt_id=?",
                       (int(decision), reservation.receipt_id))
        return decision

    def feedback(self, context: EvaluationContext, candidate_hash: str) -> bool | None:
        """Candidate-visible API: one bit, or None before completion."""
        with self._connect() as db:
            row = db.execute("SELECT decision FROM receipts WHERE receipt_id=?",
                             (self.receipt_id(context, candidate_hash),)).fetchone()
        return None if row is None or row[0] is None else bool(row[0])

    def spent(self, epoch: str) -> int:
        with self._connect() as db:
            return db.execute("SELECT COUNT(*) FROM receipts WHERE epoch=?",
                              (epoch,)).fetchone()[0]

    def add_search_constraint(
        self, context: EvaluationContext, mutation_hash: str,
        reproducer_hash: str, *, source: str
    ) -> None:
        """Trusted search evidence only; never copy sealed failures here.

        Source is a caller assertion, not an authentication/provenance mechanism.
        The evaluator service must enforce this boundary when integrating it.
        """
        if source != "search":
            raise ValueError("Only search-set constraints may be shared")
        if any(not isinstance(v, str) or not v.strip() for v in
               (mutation_hash, reproducer_hash)):
            raise ValueError("Mutation and reproducer hashes are required")
        with self._transaction() as db:
            db.execute("INSERT OR IGNORE INTO search_constraints VALUES (?, ?, ?)",
                       (_digest(asdict(context)), mutation_hash, reproducer_hash))

    def blocked(self, context: EvaluationContext, mutation_hash: str) -> bool:
        with self._connect() as db:
            return db.execute(
                "SELECT 1 FROM search_constraints WHERE context_id=? AND mutation_hash=?",
                (_digest(asdict(context)), mutation_hash),
            ).fetchone() is not None

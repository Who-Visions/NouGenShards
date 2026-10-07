"""Executable resilience reference primitives; no live services are invoked.

SQLite is for one host on a local disk. Authentication, isolation, backend
reconciliation, and distributed deployment are adapter responsibilities.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import time
from typing import Callable, Iterable


def digest(value):
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode()).hexdigest()


def require_hash(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("expected lowercase SHA-256")


class Busy(RuntimeError):
    pass


class Indeterminate(RuntimeError):
    pass


class Conflict(RuntimeError):
    pass


class StaleOwner(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class Ticket:
    key: str
    owner: str
    epoch: int
    replay_receipt: str | None = None


class Journal:
    """Durable intent journal. No automatic retry of ambiguous external writes."""

    def __init__(self, path, *, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS effects (
                    key TEXT PRIMARY KEY,
                    payload_hash TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('PREPARED','DISPATCHED','COMMITTED','FAILED')),
                    owner TEXT NOT NULL,
                    epoch INTEGER NOT NULL CHECK(epoch > 0),
                    lease_until REAL NOT NULL,
                    receipt_hash TEXT
                );
                CREATE TABLE IF NOT EXISTS budgets (
                    id TEXT PRIMARY KEY,
                    limit_units INTEGER NOT NULL CHECK(limit_units >= 0),
                    used_units INTEGER NOT NULL CHECK(used_units >= 0)
                );
                CREATE TABLE IF NOT EXISTS reservations (
                    budget_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    units INTEGER NOT NULL CHECK(units > 0),
                    PRIMARY KEY(budget_id,request_id),
                    FOREIGN KEY(budget_id) REFERENCES budgets(id)
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA busy_timeout=5000")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def prepare(self, key, payload_hash, owner, *, lease_seconds=30):
        require_hash(payload_hash)
        if not all(isinstance(v, str) and v for v in (key, owner)):
            raise ValueError("key and owner are required")
        if not isinstance(lease_seconds, (float, int)) or not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError("lease must be finite and positive")
        now = self.clock()
        with self.transaction() as db:
            row = db.execute("SELECT * FROM effects WHERE key=?", (key,)).fetchone()
            if row is None:
                db.execute("INSERT INTO effects VALUES (?,?, 'PREPARED', ?,1,?,NULL)",
                           (key, payload_hash, owner, now + lease_seconds))
                return Ticket(key, owner, 1)
            if row["payload_hash"] != payload_hash:
                raise Conflict("idempotency key reused for a different canonical request")
            if row["state"] == "COMMITTED":
                return Ticket(key, row["owner"], row["epoch"], row["receipt_hash"])
            if row["state"] == "DISPATCHED":
                raise Indeterminate("reconcile backend outcome; do not redispatch")
            if row["state"] == "FAILED":
                raise Conflict("terminal failure requires an explicit new attempt")
            if row["lease_until"] > now:
                raise Busy("prepared intent has a live owner")
            epoch = row["epoch"] + 1
            db.execute("UPDATE effects SET owner=?,epoch=?,lease_until=? WHERE key=?",
                       (owner, epoch, now + lease_seconds, key))
            return Ticket(key, owner, epoch)

    def dispatch(self, ticket: Ticket):
        """Persist ambiguity before contacting the external backend."""
        with self.transaction() as db:
            changed = db.execute(
                "UPDATE effects SET state='DISPATCHED' WHERE key=? AND owner=? AND epoch=? "
                "AND state='PREPARED' AND lease_until>?",
                (ticket.key, ticket.owner, ticket.epoch, self.clock()),
            ).rowcount
            if changed != 1:
                raise StaleOwner("dispatch requires current unexpired ownership")

    def complete(self, ticket: Ticket, verified_receipt_hash):
        """Caller must authenticate and validate the backend receipt first."""
        require_hash(verified_receipt_hash)
        with self.transaction() as db:
            changed = db.execute(
                "UPDATE effects SET state='COMMITTED',receipt_hash=? WHERE key=? AND owner=? "
                "AND epoch=? AND state='DISPATCHED'",
                (verified_receipt_hash, ticket.key, ticket.owner, ticket.epoch),
            ).rowcount
            if changed != 1:
                raise StaleOwner("completion does not match dispatched intent")

    def reconcile(self, key, payload_hash, verified_receipt_hash):
        """Trusted reconciliation adapter confirms a committed backend effect.

        Epoch increment prevents the original dispatcher overwriting its result.
        Absence of a receipt is insufficient to declare a failed/no-effect write.
        """
        require_hash(payload_hash)
        require_hash(verified_receipt_hash)
        with self.transaction() as db:
            changed = db.execute(
                "UPDATE effects SET state='COMMITTED',receipt_hash=?,epoch=epoch+1 "
                "WHERE key=? AND payload_hash=? AND state='DISPATCHED'",
                (verified_receipt_hash, key, payload_hash),
            ).rowcount
            if changed != 1:
                raise Conflict("no matching ambiguous intent to reconcile")

    def budget(self, budget_id, limit_units):
        if isinstance(limit_units, bool) or not isinstance(limit_units, int) or limit_units < 0:
            raise ValueError("budget limit must be a nonnegative integer")
        with self.transaction() as db:
            row = db.execute("SELECT limit_units FROM budgets WHERE id=?", (budget_id,)).fetchone()
            if row and row[0] != limit_units:
                raise Conflict("existing budget configuration is immutable")
            db.execute("INSERT OR IGNORE INTO budgets VALUES (?,?,0)", (budget_id, limit_units))

    def reserve_budget(self, budget_id, request_id, units):
        if isinstance(units, bool) or not isinstance(units, int) or units <= 0:
            raise ValueError("reservation units must be positive integers")
        with self.transaction() as db:
            prior = db.execute("SELECT units FROM reservations WHERE budget_id=? AND request_id=?",
                               (budget_id, request_id)).fetchone()
            if prior:
                if prior[0] != units:
                    raise Conflict("reservation identity cannot change units")
                return False
            row = db.execute("SELECT * FROM budgets WHERE id=?", (budget_id,)).fetchone()
            if row is None:
                raise Conflict("budget must be configured before use")
            if row["used_units"] + units > row["limit_units"]:
                raise BudgetExceeded("shared budget exhausted")
            db.execute("UPDATE budgets SET used_units=used_units+? WHERE id=?", (units, budget_id))
            db.execute("INSERT INTO reservations VALUES (?,?,?)", (budget_id, request_id, units))
            return True


@dataclass(frozen=True)
class Provider:
    name: str
    local: bool
    capabilities: frozenset[str]
    cost_units: int
    healthy: bool = True


def choose_provider(providers: Iterable[Provider], *, local_only, capabilities, max_cost_units):
    """Hard filters precede cost ranking; a failure never changes privacy policy."""
    eligible = [p for p in providers if p.healthy and (p.local or not local_only)
                and set(capabilities) <= p.capabilities and 0 <= p.cost_units <= max_cost_units]
    if not eligible:
        raise Conflict("no provider satisfies privacy/capability/budget policy")
    return min(eligible, key=lambda p: (p.cost_units, p.name))


@dataclass(frozen=True)
class Witness:
    family: str
    independence_group: str
    status: str
    bindings_hash: str
    artifact_hash: str
    signature: str


def promotion_gate(*, bindings, witnesses, required_families, min_groups,
                   critical_violation, verifier, resource_bounds, min_gain=0.01):
    """Gate a proposal using authenticated evidence and predeclared intervals.

    verifier(witness) is a trusted signature/artifact-validation adapter, NOT an
    LLM vote. The caller supplies fixed, simultaneous confidence intervals for
    relative cost deltas; this function does not estimate intervals or alpha.
    """
    if critical_violation:
        return "REGRESSED"
    if (not isinstance(bindings, dict) or set(bindings) != {
            "reference", "candidate", "workload", "environment", "policy", "evaluator"}):
        return "INDETERMINATE"
    try:
        for value in bindings.values():
            require_hash(value)
        expected = digest(bindings)
        required = set(required_families)
        if not required or min_groups < 2 or not math.isfinite(min_gain) or min_gain <= 0:
            return "INDETERMINATE"
        accepted = []
        invalid_evidence = False
        refuted = False
        for witness in witnesses:
            try:
                require_hash(witness.artifact_hash)
                valid = witness.bindings_hash == expected and verifier(witness) is True
            except Exception:
                valid = False
            if not valid:
                invalid_evidence = True
                continue
            if witness.status == "REFUTED":
                refuted = True
            if witness.status == "VERIFIED" and witness.independence_group:
                accepted.append(witness)
        if refuted:
            return "REGRESSED"
        if invalid_evidence:
            return "INDETERMINATE"
        if not required <= {w.family for w in accepted}:
            return "INDETERMINATE"
        if len({w.independence_group for w in accepted}) < min_groups:
            return "INDETERMINATE"
        if not resource_bounds:
            return "INDETERMINATE"
        gain = False
        resource_regression = False
        resource_uncertain = False
        for lower, upper in resource_bounds.values():
            if not all(math.isfinite(v) for v in (lower, upper)) or lower > upper:
                return "INDETERMINATE"
            if lower > 0:
                resource_regression = True
            if upper > 0:
                resource_uncertain = True
            gain = gain or upper <= -min_gain
        if resource_regression:
            return "REGRESSED"
        if resource_uncertain:
            return "INDETERMINATE"
        return "IMPROVED" if gain else "EQUIVALENT"
    except (ValueError, TypeError, AttributeError):
        return "INDETERMINATE"


if __name__ == "__main__":
    print("Reference primitives only. Run: python -m unittest -v test_resilience_core.py")

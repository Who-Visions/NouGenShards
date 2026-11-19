"""Epistemic state of a fleet claim: how true is "done"?

GM ladder (2026-10-04): a claim climbs one rung at a time and can never skip
one. message accepted != read != executed != observed != verified.

    CLAIMED -> EVIDENCED -> EXECUTED -> OBSERVED -> INDEPENDENTLY_VERIFIED

Any rung may fall to REFUTED, which is terminal. Each promotion needs an
evidence reference in evidence_label's grammar (PR, URL, sha, path:line, leg,
shard); INDEPENDENTLY_VERIFIED additionally needs a verifier lane different from
the claimant and from every lane that supplied an earlier rung's evidence.
History is append-only, so a downgrade is a new REFUTED row, never an edit.

This is distinct from claim_lifecycle (task work states), evidence_gate
(policy promotion) and proof_canon (a pure, storage-free proof ladder): it is
the shared, persisted record of what the fleet knows about one statement. Each
step is SHA-256 chained with proof_canon's digest so verify_chain() detects any
edited or reordered row.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterator

from .evidence_label import has_evidence
from .proof_canon import _digest


class ClaimState(str, Enum):
    CLAIMED = "CLAIMED"
    EVIDENCED = "EVIDENCED"
    EXECUTED = "EXECUTED"
    OBSERVED = "OBSERVED"
    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"
    REFUTED = "REFUTED"


LADDER = [
    ClaimState.CLAIMED,
    ClaimState.EVIDENCED,
    ClaimState.EXECUTED,
    ClaimState.OBSERVED,
    ClaimState.INDEPENDENTLY_VERIFIED,
]


class TransitionRefused(ValueError):
    """The requested move would skip a rung, lack evidence, or self-verify."""


@dataclass(frozen=True)
class Step:
    state: ClaimState
    lane: str
    evidence: str
    at: str


def _link(claim_id: str, seq: int, state: str, lane: str, evidence: str, prev: str) -> str:
    return _digest({"id": claim_id, "seq": seq, "state": state, "lane": lane, "evidence": evidence, "prev": prev})


class ClaimLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS claims (
                    claim_id TEXT PRIMARY KEY,
                    claimant TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS steps (
                    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
                    seq INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    lane TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    prev TEXT NOT NULL,
                    handle TEXT NOT NULL,
                    at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (claim_id, seq)
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

    def claim(self, claimant: str, statement: str) -> str:
        if not claimant.strip() or not statement.strip():
            raise ValueError("claimant and statement must be nonempty")
        claim_id = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO claims (claim_id, claimant, statement) VALUES (?, ?, ?)",
                (claim_id, claimant, statement),
            )
            db.execute(
                "INSERT INTO steps (claim_id, seq, state, lane, evidence, prev, handle) VALUES (?, 0, ?, ?, ?, '', ?)",
                (claim_id, ClaimState.CLAIMED.value, claimant, statement,
                 _link(claim_id, 0, ClaimState.CLAIMED.value, claimant, statement, "")),
            )
            db.commit()
        return claim_id

    def history(self, claim_id: str) -> list[Step]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT state, lane, evidence, at FROM steps WHERE claim_id = ? ORDER BY seq",
                (claim_id,),
            ).fetchall()
        if not rows:
            raise KeyError(claim_id)
        return [Step(ClaimState(s), lane, ev, at) for s, lane, ev, at in rows]

    def state(self, claim_id: str) -> ClaimState:
        return self.history(claim_id)[-1].state

    def advance(self, claim_id: str, to: ClaimState, *, lane: str, evidence: str) -> ClaimState:
        """Move up exactly one rung (or to REFUTED). Refuses anything else."""
        if not lane.strip():
            raise TransitionRefused("lane is required")
        if not has_evidence(evidence):
            raise TransitionRefused(f"{to.value} needs an evidence ref (PR, URL, sha, path:line, leg, shard)")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                rows = db.execute(
                    "SELECT seq, state, lane, handle FROM steps WHERE claim_id = ? ORDER BY seq", (claim_id,)
                ).fetchall()
                if not rows:
                    raise KeyError(claim_id)
                seq, current, _, prev = rows[-1]
                current = ClaimState(current)
                if current in (ClaimState.REFUTED, ClaimState.INDEPENDENTLY_VERIFIED) and to != ClaimState.REFUTED:
                    raise TransitionRefused(f"claim is {current.value}")
                if current == ClaimState.REFUTED:
                    raise TransitionRefused("REFUTED is terminal")
                if to != ClaimState.REFUTED:
                    expected = LADDER[LADDER.index(current) + 1]
                    if to != expected:
                        raise TransitionRefused(f"{current.value} can only advance to {expected.value}, not {to.value}")
                    if to == ClaimState.INDEPENDENTLY_VERIFIED:
                        prior = {r[2] for r in rows}
                        if lane in prior:
                            raise TransitionRefused("verifier must differ from the claimant and every prior evidencing lane")
                db.execute(
                    "INSERT INTO steps (claim_id, seq, state, lane, evidence, prev, handle) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (claim_id, seq + 1, to.value, lane, evidence, prev,
                     _link(claim_id, seq + 1, to.value, lane, evidence, prev)),
                )
                db.commit()
            except BaseException:
                db.rollback()
                raise
        return to

    def verify_chain(self, claim_id: str) -> bool:
        """True when every step re-derives and links to its predecessor."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT seq, state, lane, evidence, prev, handle FROM steps WHERE claim_id = ? ORDER BY seq",
                (claim_id,),
            ).fetchall()
        if not rows:
            raise KeyError(claim_id)
        prev = ""
        for seq, state, lane, evidence, p, handle in rows:
            if p != prev or _link(claim_id, seq, state, lane, evidence, p) != handle:
                return False
            prev = handle
        return True

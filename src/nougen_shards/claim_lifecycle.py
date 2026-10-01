"""Durable claim, execution, verification, and commit lifecycle for NouGenMsg tasks.

Implements the hardcade state machine:
RECEIVED -> ACKED/SUBMITTED -> CLAIMED -> WORKING -> VERIFYING -> COMMITTING -> COMPLETE

Interrupt states: INPUT_REQUIRED | AUTH_REQUIRED | BLOCKED
Terminal states:  FAILED | CANCELED | REJECTED

Mechanisms:
- Atomic take_msg: ACK + classification + claim + lease/fencing epoch
- Lease heartbeat / checkpoint with fencing token verification
- Idempotency / effect keys on external mutations
- Stale / orphan claim detection and automatic release
- Verification proof before COMPLETE transition
"""
import enum
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskState(str, enum.Enum):
    RECEIVED = "RECEIVED"
    ACKED = "ACKED"
    SUBMITTED = "SUBMITTED"
    CLAIMED = "CLAIMED"
    WORKING = "WORKING"
    VERIFYING = "VERIFYING"
    COMMITTING = "COMMITTING"
    COMPLETE = "COMPLETE"

    # Interrupt states
    INPUT_REQUIRED = "INPUT_REQUIRED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    BLOCKED = "BLOCKED"

    # Terminal alternatives
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


DEFAULT_LEASE_SECONDS = 300


def get_db_path() -> Path:
    home = Path(os.environ.get("NOUGEN_HOME", str(Path.home() / ".nougen")))
    home.mkdir(parents=True, exist_ok=True)
    return home / "claims_lifecycle.db"


def init_db(db_path: Optional[Path] = None) -> Path:
    p = db_path or get_db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(p) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS claims (
                msg_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                agent_lane TEXT NOT NULL,
                fencing_epoch INTEGER NOT NULL DEFAULT 1,
                lease_expires_at REAL NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                idempotency_key TEXT,
                semantic_version TEXT,
                evidence TEXT,
                verification_proof TEXT,
                error_detail TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_claims_state ON claims(state)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_claims_lease ON claims(lease_expires_at)")
    return p


class FencingViolationError(RuntimeError):
    """Raised when an operation is attempted with an expired or superseded fencing epoch."""
    pass


class InvalidStateTransitionError(ValueError):
    """Raised when a state transition is not allowed by the lifecycle state machine."""
    pass


class ClaimLifecycleManager:
    """Manages atomic claims, fencing epochs, heartbeats, and verification proofs."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = init_db(db_path)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=10.0)

    def register_received(self, msg_id: str, sender_lane: str = "unknown") -> Dict[str, Any]:
        """Record receipt of a message."""
        now = time.time()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO claims (msg_id, state, agent_lane, fencing_epoch, lease_expires_at, created_at, updated_at)
                VALUES (?, ?, ?, 0, 0, ?, ?)
                ON CONFLICT(msg_id) DO UPDATE SET updated_at = excluded.updated_at
            """, (msg_id, TaskState.RECEIVED.value, sender_lane, now, now))
        return self.get_claim(msg_id)

    def take_msg(
        self,
        msg_id: str,
        agent_lane: str,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        semantic_version: str = "v1"
    ) -> Dict[str, Any]:
        """Atomically claim work, bump fencing epoch, and start lease."""
        now = time.time()
        lease_expires = now + max(1, lease_seconds)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT state, agent_lane, fencing_epoch, lease_expires_at FROM claims WHERE msg_id = ?", (msg_id,))
            row = cur.fetchone()

            if row is not None:
                current_state, current_lane, current_epoch, current_lease = row
                # Check if currently held by another live worker
                if current_state in (TaskState.CLAIMED.value, TaskState.WORKING.value, TaskState.VERIFYING.value, TaskState.COMMITTING.value):
                    if current_lease > now and current_lane != agent_lane:
                        raise FencingViolationError(
                            f"Task {msg_id} is actively leased by {current_lane} until {current_lease:.1f} (epoch {current_epoch})"
                        )
                if current_state == TaskState.COMPLETE.value:
                    raise InvalidStateTransitionError(f"Task {msg_id} is already COMPLETE")

                new_epoch = current_epoch + 1
                cur.execute("""
                    UPDATE claims
                    SET state = ?, agent_lane = ?, fencing_epoch = ?, lease_expires_at = ?, updated_at = ?, semantic_version = ?
                    WHERE msg_id = ?
                """, (TaskState.CLAIMED.value, agent_lane, new_epoch, lease_expires, now, semantic_version, msg_id))
            else:
                new_epoch = 1
                cur.execute("""
                    INSERT INTO claims (msg_id, state, agent_lane, fencing_epoch, lease_expires_at, created_at, updated_at, semantic_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (msg_id, TaskState.CLAIMED.value, agent_lane, new_epoch, lease_expires, now, now, semantic_version))

        return self.get_claim(msg_id)

    def heartbeat(
        self,
        msg_id: str,
        fencing_epoch: int,
        state: TaskState = TaskState.WORKING,
        lease_seconds: int = DEFAULT_LEASE_SECONDS
    ) -> bool:
        """Verify fencing epoch and extend lease."""
        now = time.time()
        new_expires = now + max(1, lease_seconds)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT fencing_epoch, state FROM claims WHERE msg_id = ?", (msg_id,))
            row = cur.fetchone()
            if not row:
                raise KeyError(f"Task {msg_id} not found")
            epoch, current_state = row
            if epoch != fencing_epoch:
                raise FencingViolationError(f"Epoch mismatch: active epoch {epoch} != caller epoch {fencing_epoch}")
            if current_state == TaskState.COMPLETE.value:
                return False

            cur.execute("""
                UPDATE claims
                SET state = ?, lease_expires_at = ?, updated_at = ?
                WHERE msg_id = ? AND fencing_epoch = ?
            """, (state.value, new_expires, now, msg_id, fencing_epoch))
            return cur.rowcount > 0

    def verify_step(
        self,
        msg_id: str,
        fencing_epoch: int,
        evidence: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Record verification evidence and transition to VERIFYING."""
        now = time.time()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT fencing_epoch FROM claims WHERE msg_id = ?", (msg_id,))
            row = cur.fetchone()
            if not row or row[0] != fencing_epoch:
                raise FencingViolationError("Fencing epoch mismatch on verify_step")

            cur.execute("""
                UPDATE claims
                SET state = ?, evidence = ?, updated_at = ?
                WHERE msg_id = ? AND fencing_epoch = ?
            """, (TaskState.VERIFYING.value, json.dumps(evidence), now, msg_id, fencing_epoch))

        return self.get_claim(msg_id)

    def commit_step(
        self,
        msg_id: str,
        fencing_epoch: int,
        idempotency_key: str
    ) -> Dict[str, Any]:
        """Verify fencing token and record idempotency key before mutation."""
        now = time.time()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT fencing_epoch, idempotency_key FROM claims WHERE msg_id = ?", (msg_id,))
            row = cur.fetchone()
            if not row or row[0] != fencing_epoch:
                raise FencingViolationError("Fencing epoch mismatch on commit_step")

            cur.execute("""
                UPDATE claims
                SET state = ?, idempotency_key = ?, updated_at = ?
                WHERE msg_id = ? AND fencing_epoch = ?
            """, (TaskState.COMMITTING.value, idempotency_key, now, msg_id, fencing_epoch))

        return self.get_claim(msg_id)

    def complete(
        self,
        msg_id: str,
        fencing_epoch: int,
        verification_proof: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Complete the task with verified proof."""
        now = time.time()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT fencing_epoch, state FROM claims WHERE msg_id = ?", (msg_id,))
            row = cur.fetchone()
            if not row or row[0] != fencing_epoch:
                raise FencingViolationError("Fencing epoch mismatch on complete")

            cur.execute("""
                UPDATE claims
                SET state = ?, verification_proof = ?, lease_expires_at = 0, updated_at = ?
                WHERE msg_id = ? AND fencing_epoch = ?
            """, (TaskState.COMPLETE.value, json.dumps(verification_proof), now, msg_id, fencing_epoch))

        return self.get_claim(msg_id)

    def interrupt(
        self,
        msg_id: str,
        fencing_epoch: int,
        interrupt_state: TaskState,
        reason: str
    ) -> Dict[str, Any]:
        """Transition task to an interrupt state (INPUT_REQUIRED | AUTH_REQUIRED | BLOCKED)."""
        if interrupt_state not in (TaskState.INPUT_REQUIRED, TaskState.AUTH_REQUIRED, TaskState.BLOCKED):
            raise ValueError(f"Invalid interrupt state: {interrupt_state}")
        now = time.time()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT fencing_epoch FROM claims WHERE msg_id = ?", (msg_id,))
            row = cur.fetchone()
            if not row or row[0] != fencing_epoch:
                raise FencingViolationError("Fencing epoch mismatch on interrupt")

            cur.execute("""
                UPDATE claims
                SET state = ?, error_detail = ?, updated_at = ?
                WHERE msg_id = ? AND fencing_epoch = ?
            """, (interrupt_state.value, reason, now, msg_id, fencing_epoch))

        return self.get_claim(msg_id)

    def detect_and_reclaim_stale(self, grace_seconds: int = 0) -> List[Dict[str, Any]]:
        """Identify expired leases in active states and return them to SUBMITTED."""
        now = time.time() - grace_seconds
        active_states = (TaskState.CLAIMED.value, TaskState.WORKING.value, TaskState.VERIFYING.value, TaskState.COMMITTING.value)
        reclaimed = []
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(f"""
                SELECT msg_id, agent_lane, fencing_epoch, lease_expires_at
                FROM claims
                WHERE state IN ({','.join('?' for _ in active_states)})
                  AND lease_expires_at < ?
            """, (*active_states, now))
            rows = cur.fetchall()
            for r in rows:
                mid, lane, epoch, expires = r
                cur.execute("""
                    UPDATE claims
                    SET state = ?, error_detail = ?, updated_at = ?
                    WHERE msg_id = ? AND fencing_epoch = ?
                """, (TaskState.SUBMITTED.value, f"Lease expired at {expires:.1f} for lane {lane}", time.time(), mid, epoch))
                reclaimed.append({"msg_id": mid, "previous_lane": lane, "epoch": epoch})
        return reclaimed

    def get_claim(self, msg_id: str) -> Optional[Dict[str, Any]]:
        """Fetch claim record by msg_id."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM claims WHERE msg_id = ?", (msg_id,))
            row = cur.fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("evidence"):
                try:
                    d["evidence"] = json.loads(d["evidence"])
                except Exception:
                    pass
            if d.get("verification_proof"):
                try:
                    d["verification_proof"] = json.loads(d["verification_proof"])
                except Exception:
                    pass
            return d

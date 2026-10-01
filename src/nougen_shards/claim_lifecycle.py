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
from contextlib import contextmanager
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

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

# The manager enforces the state machine itself: the CLI path (codex_pipe.advance)
# checks order and proof, but callers that use this class directly must not be able
# to skip them (2026-10-01 audit: heartbeat(state=COMPLETE) completed a task with no
# evidence; FAILED/CANCELED/REJECTED tasks could be re-claimed).
ACTIVE_STATES = frozenset({"CLAIMED", "WORKING", "VERIFYING", "COMMITTING"})
INTERRUPT_STATES = frozenset({"INPUT_REQUIRED", "AUTH_REQUIRED", "BLOCKED"})
TERMINAL_STATES = frozenset({"COMPLETE", "FAILED", "CANCELED", "REJECTED"})
LIVE_STATES = ACTIVE_STATES | INTERRUPT_STATES


def _heartbeat_may_set(current: str, new: str) -> bool:
    """A heartbeat renews the lease; it may only keep the state or resume work."""
    if new == current:
        return True
    return new == "WORKING" and current in ({"CLAIMED", "VERIFYING"} | INTERRUPT_STATES)


REQUEUEABLE_STATES = frozenset({"FAILED", "BLOCKED", "INPUT_REQUIRED", "AUTH_REQUIRED"})
DEFAULT_MAX_REQUEUES = 3

# Authority check: called with the live claim row just before a durable effect (the
# commit and the completion). Returns (ok, reason). Authority held when the work was
# claimed is not authority now: the operator may have canceled it, or the lane may have
# been reassigned. A check that raises is treated as a denial (fail closed).
AuthorityCheck = Callable[[Dict[str, Any]], Tuple[bool, str]]


def _authorize(check: Optional[AuthorityCheck], snapshot: Dict[str, Any]) -> None:
    if check is None:
        return
    try:
        ok, why = check(snapshot)
    except Exception as exc:  # fail closed: a broken authority service never grants authority
        raise AuthorityExpiredError(f"authority check failed: {exc}") from exc
    if not ok:
        raise AuthorityExpiredError(f"authority revoked or expired: {why}")


def _snapshot(cur: sqlite3.Cursor, msg_id: str) -> Dict[str, Any]:
    cur.execute("SELECT * FROM claims WHERE msg_id = ?", (msg_id,))
    row = cur.fetchone()
    names = [d[0] for d in cur.description]
    return dict(zip(names, row)) if row else {}


_NEW_COLUMNS = (
    ("claimed_at", "REAL"),
    ("last_heartbeat_at", "REAL"),
    ("last_progress_at", "REAL"),
    ("progress_count", "INTEGER NOT NULL DEFAULT 0"),
    ("requeue_count", "INTEGER NOT NULL DEFAULT 0"),
)


def _migrate(conn: sqlite3.Connection) -> None:
    """Add the progress/requeue columns to a database created before they existed."""
    existing = {r[1] for r in conn.execute("PRAGMA table_info(claims)")}
    for name, decl in _NEW_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE claims ADD COLUMN {name} {decl}")


def _require_state(msg_id: str, current: str, allowed: frozenset, action: str) -> None:
    if current not in allowed:
        raise InvalidStateTransitionError(
            f"Task {msg_id} is {current}; {action} needs one of: {', '.join(sorted(allowed))}")


def get_db_path() -> Path:
    home = Path(os.environ.get("NOUGEN_HOME", str(Path.home() / ".nougen")))
    home.mkdir(parents=True, exist_ok=True)
    return home / "claims_lifecycle.db"


def init_db(db_path: Optional[Path] = None) -> Path:
    p = db_path or get_db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    try:
        with conn:
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
            _migrate(conn)
    finally:
        conn.close()
    return p


class FencingViolationError(RuntimeError):
    """Raised when an operation is attempted with an expired or superseded fencing epoch."""
    pass


class AuthorityExpiredError(FencingViolationError):
    """Raised when the commit-time authority check denies a durable effect."""
    pass


class InvalidStateTransitionError(ValueError):
    """Raised when a state transition is not allowed by the lifecycle state machine."""
    pass


class ClaimLifecycleManager:
    """Manages atomic claims, fencing epochs, heartbeats, and verification proofs."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = init_db(db_path)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

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
            # Serialize read-check-write so two lanes cannot both win a lease.
            cur.execute("BEGIN IMMEDIATE")
            cur.execute("SELECT state, agent_lane, fencing_epoch, lease_expires_at FROM claims WHERE msg_id = ?", (msg_id,))
            row = cur.fetchone()

            if row is not None:
                current_state, current_lane, current_epoch, current_lease = row
                # Check if currently held by another live worker
                if current_state in (TaskState.CLAIMED.value, TaskState.WORKING.value, TaskState.VERIFYING.value, TaskState.COMMITTING.value):
                    if current_lease > now:
                        if current_lane == agent_lane:
                            return self.get_claim(msg_id)
                        raise FencingViolationError(
                            f"Task {msg_id} is actively leased by {current_lane} until {current_lease:.1f} (epoch {current_epoch})"
                        )
                if current_state in TERMINAL_STATES:
                    raise InvalidStateTransitionError(f"Task {msg_id} is already {current_state} (terminal)")

                new_epoch = current_epoch + 1
                cur.execute("""
                    UPDATE claims
                    SET state = ?, agent_lane = ?, fencing_epoch = ?, lease_expires_at = ?, updated_at = ?, semantic_version = ?,
                        claimed_at = ?, last_heartbeat_at = ?, last_progress_at = NULL, progress_count = 0
                    WHERE msg_id = ?
                """, (TaskState.CLAIMED.value, agent_lane, new_epoch, lease_expires, now, semantic_version, now, now, msg_id))
            else:
                new_epoch = 1
                cur.execute("""
                    INSERT INTO claims (msg_id, state, agent_lane, fencing_epoch, lease_expires_at, created_at, updated_at,
                                        semantic_version, claimed_at, last_heartbeat_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (msg_id, TaskState.CLAIMED.value, agent_lane, new_epoch, lease_expires, now, now, semantic_version, now, now))

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
            cur.execute("SELECT fencing_epoch, state, lease_expires_at FROM claims WHERE msg_id = ?", (msg_id,))
            row = cur.fetchone()
            if not row:
                raise KeyError(f"Task {msg_id} not found")
            epoch, current_state, lease_expires_at = row
            if epoch != fencing_epoch:
                raise FencingViolationError(f"Epoch mismatch: active epoch {epoch} != caller epoch {fencing_epoch}")
            if lease_expires_at <= now:
                raise FencingViolationError("Lease expired; the worker must reacquire the task")
            if current_state == TaskState.COMPLETE.value:
                return False
            if not _heartbeat_may_set(current_state, state.value):
                raise InvalidStateTransitionError(
                    f"Task {msg_id} is {current_state}; a heartbeat cannot set it to {state.value}")

            cur.execute("""
                UPDATE claims
                SET state = ?, lease_expires_at = ?, updated_at = ?, last_heartbeat_at = ?
                WHERE msg_id = ? AND fencing_epoch = ? AND lease_expires_at > ?
            """, (state.value, new_expires, now, now, msg_id, fencing_epoch, now))
            return cur.rowcount > 0

    def checkpoint(
        self,
        msg_id: str,
        fencing_epoch: int,
        evidence: Dict[str, Any],
        lease_seconds: int = DEFAULT_LEASE_SECONDS
    ) -> Dict[str, Any]:
        """Record durable progress. Unlike a heartbeat (alive), a checkpoint means work was done.

        Progress is what stall detection watches: a worker that heartbeats forever without a
        checkpoint is alive but not working.
        """
        now = time.time()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT fencing_epoch, state, lease_expires_at FROM claims WHERE msg_id = ?", (msg_id,))
            row = cur.fetchone()
            if not row:
                raise KeyError(f"Task {msg_id} not found")
            epoch, current_state, lease_expires_at = row
            if epoch != fencing_epoch:
                raise FencingViolationError(f"Epoch mismatch: active epoch {epoch} != caller epoch {fencing_epoch}")
            if lease_expires_at <= now:
                raise FencingViolationError("Lease expired; the worker must reacquire the task")
            _require_state(msg_id, current_state, frozenset({"CLAIMED", "WORKING"}), "checkpoint")
            if not evidence:
                raise InvalidStateTransitionError(f"Task {msg_id}: checkpoint needs non-empty evidence")
            cur.execute("""
                UPDATE claims
                SET state = ?, lease_expires_at = ?, updated_at = ?, last_heartbeat_at = ?,
                    last_progress_at = ?, progress_count = progress_count + 1
                WHERE msg_id = ? AND fencing_epoch = ? AND lease_expires_at > ?
            """, (TaskState.WORKING.value, now + max(1, lease_seconds), now, now, now, msg_id, fencing_epoch, now))
        return self.get_claim(msg_id)

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
            cur.execute("SELECT fencing_epoch, lease_expires_at, state FROM claims WHERE msg_id = ?", (msg_id,))
            row = cur.fetchone()
            if not row or row[0] != fencing_epoch or row[1] <= now:
                raise FencingViolationError("Fencing epoch mismatch on verify_step")
            _require_state(msg_id, row[2], frozenset({"WORKING", "VERIFYING"}), "verify_step")
            if not evidence:
                raise InvalidStateTransitionError(f"Task {msg_id}: verify_step needs non-empty evidence")

            cur.execute("""
                UPDATE claims
                SET state = ?, evidence = ?, updated_at = ?
                WHERE msg_id = ? AND fencing_epoch = ? AND lease_expires_at > ?
            """, (TaskState.VERIFYING.value, json.dumps(evidence), now, msg_id, fencing_epoch, now))

        return self.get_claim(msg_id)

    def commit_step(
        self,
        msg_id: str,
        fencing_epoch: int,
        idempotency_key: str,
        authority_check: Optional[AuthorityCheck] = None
    ) -> Dict[str, Any]:
        """Verify fencing token and record idempotency key before mutation.

        `authority_check` re-validates authority at the commit boundary (see AuthorityCheck).
        """
        now = time.time()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT fencing_epoch, idempotency_key, lease_expires_at, state FROM claims WHERE msg_id = ?", (msg_id,))
            row = cur.fetchone()
            if not row or row[0] != fencing_epoch or row[2] <= now:
                raise FencingViolationError("Fencing epoch mismatch on commit_step")
            _require_state(msg_id, row[3], frozenset({"VERIFYING", "COMMITTING"}), "commit_step")
            if not idempotency_key or not str(idempotency_key).strip():
                raise InvalidStateTransitionError(f"Task {msg_id}: commit_step needs an idempotency key")
            if row[1] and row[1] != idempotency_key:
                raise FencingViolationError("A different idempotency key is already bound to this claim")
            _authorize(authority_check, _snapshot(cur, msg_id))

            cur.execute("""
                UPDATE claims
                SET state = ?, idempotency_key = ?, updated_at = ?
                WHERE msg_id = ? AND fencing_epoch = ? AND lease_expires_at > ?
            """, (TaskState.COMMITTING.value, idempotency_key, now, msg_id, fencing_epoch, now))

        return self.get_claim(msg_id)

    def complete(
        self,
        msg_id: str,
        fencing_epoch: int,
        verification_proof: Dict[str, Any],
        authority_check: Optional[AuthorityCheck] = None
    ) -> Dict[str, Any]:
        """Complete the task with verified proof (re-checking authority at the commit boundary)."""
        now = time.time()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT fencing_epoch, state, lease_expires_at FROM claims WHERE msg_id = ?", (msg_id,))
            row = cur.fetchone()
            if not row or row[0] != fencing_epoch or row[2] <= now:
                raise FencingViolationError("Fencing epoch mismatch on complete")
            _require_state(msg_id, row[1], frozenset({"COMMITTING"}), "complete")
            if not verification_proof:
                raise InvalidStateTransitionError(f"Task {msg_id}: complete needs a non-empty verification proof")
            _authorize(authority_check, _snapshot(cur, msg_id))

            cur.execute("""
                UPDATE claims
                SET state = ?, verification_proof = ?, lease_expires_at = 0, updated_at = ?
                WHERE msg_id = ? AND fencing_epoch = ? AND lease_expires_at > ?
            """, (TaskState.COMPLETE.value, json.dumps(verification_proof), now, msg_id, fencing_epoch, now))

        return self.get_claim(msg_id)

    def fail(self, msg_id: str, fencing_epoch: int, reason: str) -> Dict[str, Any]:
        """Close a failed task only while the caller still owns a live lease."""
        now = time.time()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT fencing_epoch, lease_expires_at, state FROM claims WHERE msg_id = ?", (msg_id,))
            row = cur.fetchone()
            if not row or row[0] != fencing_epoch or row[1] <= now:
                raise FencingViolationError("Fencing epoch mismatch or expired lease on fail")
            _require_state(msg_id, row[2], LIVE_STATES, "fail")
            cur.execute("""
                UPDATE claims
                SET state = ?, error_detail = ?, lease_expires_at = 0, updated_at = ?
                WHERE msg_id = ? AND fencing_epoch = ? AND lease_expires_at > ?
            """, (TaskState.FAILED.value, reason, now, msg_id, fencing_epoch, now))
            if not cur.rowcount:
                raise FencingViolationError("Lease expired before fail was recorded")
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
            cur.execute("SELECT fencing_epoch, lease_expires_at, state FROM claims WHERE msg_id = ?", (msg_id,))
            row = cur.fetchone()
            if not row or row[0] != fencing_epoch or row[1] <= now:
                raise FencingViolationError("Fencing epoch mismatch on interrupt")
            _require_state(msg_id, row[2], LIVE_STATES, "interrupt")

            cur.execute("""
                UPDATE claims
                SET state = ?, error_detail = ?, updated_at = ?
                WHERE msg_id = ? AND fencing_epoch = ? AND lease_expires_at > ?
            """, (interrupt_state.value, reason, now, msg_id, fencing_epoch, now))

        return self.get_claim(msg_id)

    def find_expired_leases(self, grace_seconds: int = 0) -> List[Dict[str, Any]]:
        """Active claims whose lease ran out. Read-only; detect_and_reclaim_stale acts on them."""
        cutoff = time.time() - grace_seconds
        active = (TaskState.CLAIMED.value, TaskState.WORKING.value, TaskState.VERIFYING.value, TaskState.COMMITTING.value)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(f"""
                SELECT msg_id, agent_lane, fencing_epoch, lease_expires_at FROM claims
                WHERE state IN ({','.join('?' for _ in active)}) AND lease_expires_at < ?
            """, (*active, cutoff))
            return [{"msg_id": r[0], "previous_lane": r[1], "epoch": r[2], "lease_expires_at": r[3]}
                    for r in cur.fetchall()]

    def detect_stalled(self, no_progress_seconds: int, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """Live claims that are alive but not progressing.

        heartbeat > 0 and no checkpoint for `no_progress_seconds` is a stalled worker: its lease
        keeps renewing, so lease expiry never fires, but nothing is getting done.
        """
        now = time.time() if now is None else now
        cutoff = now - no_progress_seconds
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT msg_id, agent_lane, fencing_epoch, claimed_at, last_heartbeat_at, last_progress_at, progress_count,
                       COALESCE(last_progress_at, claimed_at, created_at) AS since
                FROM claims
                WHERE state IN (?, ?) AND lease_expires_at > ?
                  AND COALESCE(last_progress_at, claimed_at, created_at) < ?
                ORDER BY since
            """, (TaskState.CLAIMED.value, TaskState.WORKING.value, now, cutoff))
            return [{"msg_id": r["msg_id"], "agent_lane": r["agent_lane"], "epoch": r["fencing_epoch"],
                     "idle_seconds": now - r["since"], "progress_count": r["progress_count"],
                     "claimed_at": r["claimed_at"], "last_heartbeat_at": r["last_heartbeat_at"],
                     "last_progress_at": r["last_progress_at"]} for r in cur.fetchall()]

    def reclaim_stalled(self, msg_id: str, fencing_epoch: int, reason: str) -> bool:
        """Take a stalled claim away and fence its worker at once (lease to 0, state SUBMITTED).

        Matches on the epoch so a claim that was already re-taken is left alone.
        """
        now = time.time()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE claims
                SET state = ?, lease_expires_at = 0, error_detail = ?, updated_at = ?
                WHERE msg_id = ? AND fencing_epoch = ? AND state IN (?, ?)
            """, (TaskState.SUBMITTED.value, reason, now, msg_id, fencing_epoch,
                  TaskState.CLAIMED.value, TaskState.WORKING.value))
            return cur.rowcount > 0

    def requeue(self, msg_id: str, reason: str, max_requeues: int = DEFAULT_MAX_REQUEUES) -> Dict[str, Any]:
        """Send a failed or interrupted task back for another attempt. Bounded, so a task that
        keeps failing cannot loop forever; the next take_msg gets a new fencing epoch."""
        now = time.time()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            cur.execute("SELECT state, requeue_count FROM claims WHERE msg_id = ?", (msg_id,))
            row = cur.fetchone()
            if not row:
                raise KeyError(f"Task {msg_id} not found")
            _require_state(msg_id, row[0], REQUEUEABLE_STATES, "requeue")
            if row[1] >= max_requeues:
                raise InvalidStateTransitionError(
                    f"Task {msg_id} was already requeued {row[1]} time(s) (max {max_requeues}); needs a person")
            cur.execute("""
                UPDATE claims
                SET state = ?, lease_expires_at = 0, requeue_count = requeue_count + 1, error_detail = ?, updated_at = ?
                WHERE msg_id = ?
            """, (TaskState.SUBMITTED.value, reason, now, msg_id))
        return self.get_claim(msg_id)

    def cancel(self, msg_id: str, reason: str) -> Dict[str, Any]:
        """Operator withdrawal: the task becomes CANCELED (terminal) and its worker is fenced."""
        now = time.time()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            cur.execute("SELECT state FROM claims WHERE msg_id = ?", (msg_id,))
            row = cur.fetchone()
            if not row:
                raise KeyError(f"Task {msg_id} not found")
            if row[0] in TERMINAL_STATES:
                raise InvalidStateTransitionError(f"Task {msg_id} is already {row[0]} (terminal)")
            cur.execute("""
                UPDATE claims SET state = ?, lease_expires_at = 0, error_detail = ?, updated_at = ?
                WHERE msg_id = ?
            """, (TaskState.CANCELED.value, reason, now, msg_id))
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

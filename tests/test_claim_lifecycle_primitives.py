"""Manager primitives the watchdog needs: progress, stall, requeue, cancel, authority.

Heartbeat proves a process is alive; checkpoint proves it did something. An agent
that heartbeats forever with no new evidence is the "ghost worker" the lifecycle was
built to catch, so progress is tracked separately from liveness. FAILED is terminal
(#649), so retrying needs an explicit, bounded requeue. Authority held at claim time
is not authority at commit time, so the commit boundary re-checks it.
"""
import sqlite3
import time

import pytest

from nougen_shards.claim_lifecycle import (
    AuthorityExpiredError,
    ClaimLifecycleManager,
    FencingViolationError,
    InvalidStateTransitionError,
    TaskState as S,
)


@pytest.fixture
def manager(tmp_path):
    return ClaimLifecycleManager(tmp_path / "claims.db")


def _working(manager, msg="m1", lane="laneA", lease=300):
    epoch = manager.take_msg(msg, lane, lease_seconds=lease)["fencing_epoch"]
    manager.heartbeat(msg, epoch, S.WORKING)
    return epoch


def _age(manager, msg, **cols):
    """Push timestamps into the past so no test has to sleep."""
    sets = ", ".join(f"{k} = ?" for k in cols)
    with manager._connect() as conn:
        conn.execute(f"UPDATE claims SET {sets} WHERE msg_id = ?", (*cols.values(), msg))


# --- schema migration ----------------------------------------------------------

def test_an_old_database_without_the_new_columns_is_migrated(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE claims (msg_id TEXT PRIMARY KEY, state TEXT NOT NULL, agent_lane TEXT NOT NULL,
        fencing_epoch INTEGER NOT NULL DEFAULT 1, lease_expires_at REAL NOT NULL, created_at REAL NOT NULL,
        updated_at REAL NOT NULL, idempotency_key TEXT, semantic_version TEXT, evidence TEXT,
        verification_proof TEXT, error_detail TEXT)""")
    conn.execute("INSERT INTO claims VALUES ('legacy','CLAIMED','laneA',3,?,?,?,NULL,'v1',NULL,NULL,NULL)",
                 (time.time() + 60, time.time(), time.time()))
    conn.commit()
    conn.close()
    m = ClaimLifecycleManager(db)
    row = m.get_claim("legacy")
    assert row["fencing_epoch"] == 3
    for col in ("claimed_at", "last_heartbeat_at", "last_progress_at", "progress_count", "requeue_count"):
        assert col in row
    assert row["progress_count"] == 0 and row["requeue_count"] == 0
    ClaimLifecycleManager(db)                                   # migrating twice is harmless


# --- heartbeat vs checkpoint ----------------------------------------------------

def test_take_records_the_claim_time_and_resets_progress(manager):
    claim = manager.take_msg("m1", "laneA")
    assert claim["claimed_at"] and claim["progress_count"] == 0 and claim["last_progress_at"] is None


def test_heartbeat_records_liveness_not_progress(manager):
    epoch = _working(manager)
    manager.heartbeat("m1", epoch, S.WORKING)
    row = manager.get_claim("m1")
    assert row["last_heartbeat_at"] and row["progress_count"] == 0 and row["last_progress_at"] is None


def test_checkpoint_records_progress_and_renews_the_lease(manager):
    epoch = _working(manager)
    _age(manager, "m1", lease_expires_at=time.time() + 5)         # a nearly-expired lease
    before = manager.get_claim("m1")["lease_expires_at"]
    row = manager.checkpoint("m1", epoch, {"tests": 12, "sha": "abc"}, lease_seconds=300)
    assert row["progress_count"] == 1 and row["last_progress_at"] and row["state"] == "WORKING"
    assert row["lease_expires_at"] > before + 100
    assert manager.checkpoint("m1", epoch, {"tests": 20})["progress_count"] == 2


def test_checkpoint_needs_real_evidence_a_live_lease_and_the_right_epoch(manager):
    epoch = _working(manager)
    with pytest.raises(InvalidStateTransitionError):
        manager.checkpoint("m1", epoch, {})
    with pytest.raises(FencingViolationError):
        manager.checkpoint("m1", epoch + 1, {"x": 1})
    _age(manager, "m1", lease_expires_at=time.time() - 1)
    with pytest.raises(FencingViolationError):
        manager.checkpoint("m1", epoch, {"x": 1})


def test_checkpoint_is_only_for_working_claims(manager):
    epoch = manager.take_msg("m2", "laneA")["fencing_epoch"]
    row = manager.checkpoint("m2", epoch, {"x": 1})             # CLAIMED -> WORKING on first progress
    assert row["state"] == "WORKING"
    manager.verify_step("m2", epoch, {"tests": 1})
    with pytest.raises(InvalidStateTransitionError):
        manager.checkpoint("m2", epoch, {"x": 2})               # VERIFYING is not working


# --- stall detection ------------------------------------------------------------

def test_a_heartbeating_worker_with_no_progress_is_stalled(manager):
    epoch = _working(manager)
    manager.heartbeat("m1", epoch, S.WORKING)
    _age(manager, "m1", claimed_at=time.time() - 2000)
    stalled = manager.detect_stalled(no_progress_seconds=900)
    assert [s["msg_id"] for s in stalled] == ["m1"]
    assert stalled[0]["idle_seconds"] >= 2000 and stalled[0]["progress_count"] == 0


def test_recent_progress_clears_the_stall(manager):
    epoch = _working(manager)
    _age(manager, "m1", claimed_at=time.time() - 2000)
    manager.checkpoint("m1", epoch, {"x": 1})
    assert manager.detect_stalled(no_progress_seconds=900) == []


def test_progress_that_went_quiet_is_stalled_again(manager):
    epoch = _working(manager)
    manager.checkpoint("m1", epoch, {"x": 1})
    _age(manager, "m1", last_progress_at=time.time() - 2000)
    assert [s["msg_id"] for s in manager.detect_stalled(no_progress_seconds=900)] == ["m1"]


def test_expired_and_terminal_claims_are_not_reported_as_stalled(manager):
    epoch = _working(manager, "gone")
    _age(manager, "gone", claimed_at=time.time() - 5000, lease_expires_at=time.time() - 1)   # expired: reclaim path
    manager.take_msg("done", "laneA")
    with manager._connect() as conn:
        conn.execute("UPDATE claims SET state='COMPLETE', lease_expires_at=0, claimed_at=? WHERE msg_id='done'",
                     (time.time() - 5000,))
    assert manager.detect_stalled(no_progress_seconds=900) == []
    assert epoch


def test_reclaiming_a_stalled_worker_fences_it_immediately(manager):
    epoch = _working(manager)
    _age(manager, "m1", claimed_at=time.time() - 2000)
    assert manager.reclaim_stalled("m1", epoch, "no progress for 2000s") is True
    row = manager.get_claim("m1")
    assert row["state"] == "SUBMITTED" and row["lease_expires_at"] == 0 and "no progress" in row["error_detail"]
    with pytest.raises(FencingViolationError):
        manager.checkpoint("m1", epoch, {"late": True})         # the zombie cannot report progress
    with pytest.raises(FencingViolationError):
        manager.heartbeat("m1", epoch, S.WORKING)
    again = manager.take_msg("m1", "laneB")
    assert again["fencing_epoch"] == epoch + 1 and again["agent_lane"] == "laneB"


def test_reclaim_stalled_ignores_a_stale_epoch(manager):
    epoch = _working(manager)
    assert manager.reclaim_stalled("m1", epoch + 5, "x") is False
    assert manager.get_claim("m1")["state"] == "WORKING"


def test_find_expired_leases_does_not_mutate(manager):
    _working(manager, "e1")
    _age(manager, "e1", lease_expires_at=time.time() - 10)
    assert [r["msg_id"] for r in manager.find_expired_leases()] == ["e1"]
    assert manager.get_claim("e1")["state"] == "WORKING"
    assert [r["msg_id"] for r in manager.detect_and_reclaim_stale()] == ["e1"]
    assert manager.get_claim("e1")["state"] == "SUBMITTED"


# --- requeue / cancel -----------------------------------------------------------

def test_a_failed_task_can_be_requeued_and_reclaimed(manager):
    epoch = _working(manager)
    manager.fail("m1", epoch, "tests red")
    row = manager.requeue("m1", "fixed the flaky fixture")
    assert row["state"] == "SUBMITTED" and row["requeue_count"] == 1 and row["lease_expires_at"] == 0
    again = manager.take_msg("m1", "laneB")
    assert again["fencing_epoch"] == epoch + 1


def test_requeue_is_bounded(manager):
    epoch = _working(manager)
    manager.fail("m1", epoch, "boom")
    for _ in range(3):
        manager.requeue("m1", "try again", max_requeues=3)
        epoch = manager.take_msg("m1", "laneA")["fencing_epoch"]
        manager.heartbeat("m1", epoch, S.WORKING)
        manager.fail("m1", epoch, "boom")
    with pytest.raises(InvalidStateTransitionError):
        manager.requeue("m1", "one more", max_requeues=3)
    assert manager.get_claim("m1")["state"] == "FAILED"


@pytest.mark.parametrize("state", ["COMPLETE", "CANCELED", "REJECTED", "CLAIMED", "WORKING"])
def test_only_failed_or_interrupted_tasks_can_be_requeued(manager, state):
    manager.take_msg("m1", "laneA")
    with manager._connect() as conn:
        conn.execute("UPDATE claims SET state = ? WHERE msg_id = 'm1'", (state,))
    with pytest.raises(InvalidStateTransitionError):
        manager.requeue("m1", "no")


@pytest.mark.parametrize("state", ["FAILED", "BLOCKED", "INPUT_REQUIRED", "AUTH_REQUIRED"])
def test_failed_and_interrupted_tasks_requeue(manager, state):
    manager.take_msg("m1", "laneA")
    with manager._connect() as conn:
        conn.execute("UPDATE claims SET state = ? WHERE msg_id = 'm1'", (state,))
    assert manager.requeue("m1", "unblocked")["state"] == "SUBMITTED"


def test_requeue_of_an_unknown_task_is_a_key_error(manager):
    with pytest.raises(KeyError):
        manager.requeue("nope", "x")


def test_cancel_is_terminal_and_fences_the_worker(manager):
    epoch = _working(manager)
    row = manager.cancel("m1", "operator withdrew the request")
    assert row["state"] == "CANCELED" and row["lease_expires_at"] == 0
    with pytest.raises(FencingViolationError):
        manager.heartbeat("m1", epoch, S.WORKING)
    with pytest.raises(InvalidStateTransitionError):
        manager.take_msg("m1", "laneB")
    with pytest.raises(InvalidStateTransitionError):
        manager.requeue("m1", "no")


def test_a_completed_task_cannot_be_canceled(manager):
    epoch = _working(manager)
    manager.verify_step("m1", epoch, {"t": 1})
    manager.commit_step("m1", epoch, "k")
    manager.complete("m1", epoch, {"ok": True})
    with pytest.raises(InvalidStateTransitionError):
        manager.cancel("m1", "too late")


# --- commit-time authority ------------------------------------------------------

def _committing_ready(manager):
    epoch = _working(manager)
    manager.verify_step("m1", epoch, {"t": 1})
    return epoch


def test_commit_is_refused_when_authority_was_revoked(manager):
    epoch = _committing_ready(manager)
    with pytest.raises(AuthorityExpiredError, match="revoked"):
        manager.commit_step("m1", epoch, "k", authority_check=lambda claim: (False, "operator revoked authority"))
    assert manager.get_claim("m1")["state"] == "VERIFYING"       # nothing was committed
    assert manager.get_claim("m1")["idempotency_key"] is None


def test_complete_rechecks_authority_too(manager):
    epoch = _committing_ready(manager)
    manager.commit_step("m1", epoch, "k")
    with pytest.raises(AuthorityExpiredError):
        manager.complete("m1", epoch, {"ok": True}, authority_check=lambda claim: (False, "lane lost ownership"))
    assert manager.get_claim("m1")["state"] == "COMMITTING"


def test_the_check_sees_the_live_claim(manager):
    epoch = _committing_ready(manager)
    seen = {}

    def check(claim):
        seen.update(claim)
        return True, ""
    manager.commit_step("m1", epoch, "k", authority_check=check)
    assert seen["agent_lane"] == "laneA" and seen["fencing_epoch"] == epoch and seen["state"] == "VERIFYING"


def test_a_check_that_raises_denies_the_commit(manager):
    epoch = _committing_ready(manager)

    def boom(claim):
        raise RuntimeError("authority service down")
    with pytest.raises(AuthorityExpiredError, match="authority service down"):
        manager.commit_step("m1", epoch, "k", authority_check=boom)
    assert manager.get_claim("m1")["state"] == "VERIFYING"       # fail closed


def test_authority_error_is_a_fencing_error(manager):
    assert issubclass(AuthorityExpiredError, FencingViolationError)


def test_no_check_keeps_the_existing_behavior(manager):
    epoch = _committing_ready(manager)
    assert manager.commit_step("m1", epoch, "k")["state"] == "COMMITTING"
    assert manager.complete("m1", epoch, {"ok": True})["state"] == "COMPLETE"

"""The claim lifecycle must enforce its own state machine, not rely on callers.

2026-10-01 audit of #646/#647 on main: the CLI path (codex_pipe.advance) checks
fencing, lease, evidence and order, but ClaimLifecycleManager, which
tools/nougenmsg.py and other callers use directly, accepted:
  - heartbeat(state=COMPLETE) straight from CLAIMED, with no evidence
  - complete() with an empty proof, from any active state
  - commit_step() with no prior verify_step
  - heartbeat(state=RECEIVED), moving a live claim backwards
  - take_msg() re-claiming a FAILED / REJECTED / CANCELED task (the docstring
    names them terminal; only COMPLETE was refused)
So "ACK != DONE, evidence closes work" held only if every caller went through
the CLI. These tests pin it inside the manager.
"""
import time

import pytest

from nougen_shards.claim_lifecycle import (
    ClaimLifecycleManager,
    FencingViolationError,
    InvalidStateTransitionError,
    TaskState as S,
)


@pytest.fixture
def manager(tmp_path):
    return ClaimLifecycleManager(tmp_path / "claims.db")


def _claimed(manager, msg="m1", lane="laneA", lease=300):
    claim = manager.take_msg(msg, lane, lease_seconds=lease)
    return claim["fencing_epoch"]


def _working(manager, msg="m1"):
    epoch = _claimed(manager, msg)
    manager.heartbeat(msg, epoch, S.WORKING)
    return epoch


def _force(manager, msg, state):
    with manager._connect() as conn:
        conn.execute("UPDATE claims SET state = ?, lease_expires_at = ? WHERE msg_id = ?",
                     (state, 0 if state in ("COMPLETE", "FAILED", "CANCELED", "REJECTED") else time.time() + 300, msg))


# --- completion needs the whole path and real proof --------------------------

def test_heartbeat_cannot_complete_a_task(manager):
    epoch = _claimed(manager)
    with pytest.raises(InvalidStateTransitionError):
        manager.heartbeat("m1", epoch, S.COMPLETE)
    assert manager.get_claim("m1")["state"] == "CLAIMED"


def test_heartbeat_cannot_move_a_claim_backwards_or_sideways(manager):
    epoch = _working(manager)
    for bad in (S.RECEIVED, S.ACKED, S.SUBMITTED, S.CLAIMED, S.COMMITTING, S.FAILED, S.REJECTED):
        with pytest.raises(InvalidStateTransitionError):
            manager.heartbeat("m1", epoch, bad)
    assert manager.get_claim("m1")["state"] == "WORKING"


def test_complete_requires_a_non_empty_proof(manager):
    epoch = _working(manager)
    manager.verify_step("m1", epoch, {"tests": 32})
    manager.commit_step("m1", epoch, "k1")
    for empty in ({}, None):
        with pytest.raises(InvalidStateTransitionError):
            manager.complete("m1", epoch, empty)
    assert manager.get_claim("m1")["state"] == "COMMITTING"


def test_complete_requires_the_commit_step(manager):
    epoch = _working(manager)
    with pytest.raises(InvalidStateTransitionError):
        manager.complete("m1", epoch, {"proof": "x"})
    manager.verify_step("m1", epoch, {"tests": 1})
    with pytest.raises(InvalidStateTransitionError):
        manager.complete("m1", epoch, {"proof": "x"})        # verified but never committed
    assert manager.get_claim("m1")["state"] == "VERIFYING"


def test_commit_requires_verification_first(manager):
    epoch = _working(manager)
    with pytest.raises(InvalidStateTransitionError):
        manager.commit_step("m1", epoch, "k1")
    assert manager.get_claim("m1")["idempotency_key"] is None


def test_verify_requires_working_and_real_evidence(manager):
    epoch = _claimed(manager)
    with pytest.raises(InvalidStateTransitionError):
        manager.verify_step("m1", epoch, {"tests": 1})        # still CLAIMED, nothing was worked
    manager.heartbeat("m1", epoch, S.WORKING)
    with pytest.raises(InvalidStateTransitionError):
        manager.verify_step("m1", epoch, {})


def test_commit_requires_an_idempotency_key(manager):
    epoch = _working(manager)
    manager.verify_step("m1", epoch, {"tests": 1})
    with pytest.raises(InvalidStateTransitionError):
        manager.commit_step("m1", epoch, "")


def test_the_legal_path_still_works_end_to_end(manager):
    epoch = _claimed(manager)
    manager.heartbeat("m1", epoch, S.WORKING)
    manager.heartbeat("m1", epoch, S.WORKING)                  # renewing is fine
    manager.verify_step("m1", epoch, {"tests": 32})
    manager.verify_step("m1", epoch, {"tests": 33})            # re-verifying is fine
    manager.commit_step("m1", epoch, "k1")
    manager.commit_step("m1", epoch, "k1")                     # same key is idempotent
    done = manager.complete("m1", epoch, {"verdict": "ACCEPTED"})
    assert done["state"] == "COMPLETE"


def test_failed_verification_may_return_to_working(manager):
    epoch = _working(manager)
    manager.verify_step("m1", epoch, {"tests": 1})
    assert manager.heartbeat("m1", epoch, S.WORKING)           # more work needed
    assert manager.get_claim("m1")["state"] == "WORKING"


# --- terminal means terminal -------------------------------------------------

@pytest.mark.parametrize("state", ["COMPLETE", "FAILED", "CANCELED", "REJECTED"])
def test_a_terminal_task_cannot_be_reclaimed(manager, state):
    _claimed(manager)
    _force(manager, "m1", state)
    with pytest.raises(InvalidStateTransitionError):
        manager.take_msg("m1", "laneB")
    assert manager.get_claim("m1")["state"] == state


def test_failed_through_the_api_is_terminal(manager):
    epoch = _claimed(manager)
    manager.fail("m1", epoch, "boom")
    with pytest.raises(InvalidStateTransitionError):
        manager.take_msg("m1", "laneB")


@pytest.mark.parametrize("state", ["INPUT_REQUIRED", "AUTH_REQUIRED", "BLOCKED", "SUBMITTED"])
def test_interrupted_or_released_work_can_be_reclaimed(manager, state):
    _claimed(manager)
    _force(manager, "m1", state)
    with manager._connect() as conn:
        conn.execute("UPDATE claims SET lease_expires_at = 0 WHERE msg_id = 'm1'")
    again = manager.take_msg("m1", "laneB")
    assert again["state"] == "CLAIMED" and again["agent_lane"] == "laneB" and again["fencing_epoch"] == 2


def test_an_interrupted_task_resumes_to_working_with_the_same_epoch(manager):
    epoch = _working(manager)
    manager.interrupt("m1", epoch, S.INPUT_REQUIRED, "need a decision")
    assert manager.heartbeat("m1", epoch, S.WORKING)
    assert manager.get_claim("m1")["state"] == "WORKING"


# --- fail / interrupt only from live work -------------------------------------

def test_fail_and_interrupt_need_live_work(manager):
    epoch = _claimed(manager)
    manager.fail("m1", epoch, "boom")
    with pytest.raises((InvalidStateTransitionError, FencingViolationError)):
        manager.fail("m1", epoch, "again")
    with pytest.raises((InvalidStateTransitionError, FencingViolationError)):
        manager.interrupt("m1", epoch, S.BLOCKED, "late")


def test_interrupt_rejects_non_interrupt_states(manager):
    epoch = _claimed(manager)
    with pytest.raises(ValueError):
        manager.interrupt("m1", epoch, S.COMPLETE, "sneaky")


# --- fencing still outranks everything ---------------------------------------

def test_expired_lease_is_a_fencing_error_even_for_an_illegal_transition(manager):
    epoch = _claimed(manager, lease=1)
    time.sleep(1.1)
    with pytest.raises(FencingViolationError):
        manager.heartbeat("m1", epoch, S.COMPLETE)
    with pytest.raises(FencingViolationError):
        manager.complete("m1", epoch, {})


def test_a_superseded_epoch_is_refused_before_state_rules(manager):
    old = _claimed(manager, lease=1)
    time.sleep(1.1)
    manager.detect_and_reclaim_stale()
    manager.take_msg("m1", "laneB")
    with pytest.raises(FencingViolationError):
        manager.heartbeat("m1", old, S.WORKING)

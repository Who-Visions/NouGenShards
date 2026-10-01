"""Unit tests for the durable claim/execute/verify/commit lifecycle state machine."""
import time
import pytest
from nougen_shards.claim_lifecycle import (
    ClaimLifecycleManager,
    TaskState,
    FencingViolationError,
)


@pytest.fixture
def manager(tmp_path):
    db = tmp_path / "test_lifecycle.db"
    return ClaimLifecycleManager(db)


def test_full_lifecycle_progression(manager):
    msg_id = "test-msg-001"
    
    # 1. Received
    r1 = manager.register_received(msg_id, sender_lane="chatgpt-app")
    assert r1["state"] == TaskState.RECEIVED.value
    assert r1["fencing_epoch"] == 0

    # 2. Take / Claim (Atomic claim + lease + epoch)
    r2 = manager.take_msg(msg_id, agent_lane="blade-antigravity", lease_seconds=60)
    assert r2["state"] == TaskState.CLAIMED.value
    assert r2["agent_lane"] == "blade-antigravity"
    epoch = r2["fencing_epoch"]
    assert epoch == 1
    assert r2["lease_expires_at"] > time.time()

    # 3. Working (Heartbeat)
    ok = manager.heartbeat(msg_id, fencing_epoch=epoch, state=TaskState.WORKING, lease_seconds=120)
    assert ok is True
    r3 = manager.get_claim(msg_id)
    assert r3["state"] == TaskState.WORKING.value

    # 4. Verifying
    evidence = {"test_runs": 32, "all_passed": True, "git_sha": "abc1234"}
    r4 = manager.verify_step(msg_id, fencing_epoch=epoch, evidence=evidence)
    assert r4["state"] == TaskState.VERIFYING.value
    assert r4["evidence"]["all_passed"] is True

    # 5. Committing (with Idempotency / effect key)
    effect_key = "relay:commit:sha:abc1234"
    r5 = manager.commit_step(msg_id, fencing_epoch=epoch, idempotency_key=effect_key)
    assert r5["state"] == TaskState.COMMITTING.value
    assert r5["idempotency_key"] == effect_key

    # 6. Complete
    proof = {"signed_by": "operator", "verdict": "ACCEPTED"}
    r6 = manager.complete(msg_id, fencing_epoch=epoch, verification_proof=proof)
    assert r6["state"] == TaskState.COMPLETE.value
    assert r6["verification_proof"]["verdict"] == "ACCEPTED"


def test_fencing_epoch_rejects_stale_worker(manager):
    msg_id = "test-fencing-002"
    r1 = manager.take_msg(msg_id, agent_lane="worker-1", lease_seconds=1)
    epoch_1 = r1["fencing_epoch"]

    # Sleep to allow lease expiry
    time.sleep(1.05)

    # Expiry itself fences the worker, even before the sweeper runs.
    with pytest.raises(FencingViolationError):
        manager.heartbeat(msg_id, fencing_epoch=epoch_1)
    with pytest.raises(FencingViolationError):
        manager.commit_step(msg_id, fencing_epoch=epoch_1, idempotency_key="late-effect")

    # Stale reclamation
    reclaimed = manager.detect_and_reclaim_stale(grace_seconds=0)
    assert len(reclaimed) == 1
    assert reclaimed[0]["msg_id"] == msg_id

    # Worker 2 takes over
    r2 = manager.take_msg(msg_id, agent_lane="worker-2", lease_seconds=60)
    epoch_2 = r2["fencing_epoch"]
    assert epoch_2 > epoch_1

    # Worker 1 tries to commit with stale epoch -> MUST FAIL
    with pytest.raises(FencingViolationError):
        manager.commit_step(msg_id, fencing_epoch=epoch_1, idempotency_key="stale-effect")


def test_concurrent_claim_blocked_while_lease_active(manager):
    msg_id = "test-concurrent-003"
    manager.take_msg(msg_id, agent_lane="worker-primary", lease_seconds=300)

    # Another worker attempts to take while primary lease is active
    with pytest.raises(FencingViolationError):
        manager.take_msg(msg_id, agent_lane="worker-rogue", lease_seconds=60)


def test_repeated_take_by_same_lane_keeps_the_live_fencing_epoch(manager):
    msg_id = "test-retry-005"
    first = manager.take_msg(msg_id, agent_lane="chatgpt-app/thread-1", lease_seconds=60)
    second = manager.take_msg(msg_id, agent_lane="chatgpt-app/thread-1", lease_seconds=60)
    assert second["fencing_epoch"] == first["fencing_epoch"]


def test_interrupt_states(manager):
    msg_id = "test-interrupt-004"
    r = manager.take_msg(msg_id, agent_lane="worker-1", lease_seconds=60)
    epoch = r["fencing_epoch"]

    r_auth = manager.interrupt(msg_id, fencing_epoch=epoch, interrupt_state=TaskState.AUTH_REQUIRED, reason="Missing Cloudflare token")
    assert r_auth["state"] == TaskState.AUTH_REQUIRED.value
    assert "Missing Cloudflare token" in r_auth["error_detail"]

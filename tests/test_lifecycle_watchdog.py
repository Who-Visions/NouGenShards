"""The watchdog makes the lifecycle drive itself.

#644-#649 built ACK != DONE: claims, leases, fencing, evidence. Nothing ran it. An
actionable message acked by an agent that then went quiet stayed "acked" forever, an
expired claim stayed expired, and a worker that kept heartbeating without doing
anything was never noticed. sweep() is the loop that closes those:

  expired lease            -> reclaim, fence the old worker, make it claimable again
  alive but no progress    -> same (heartbeat is not progress)
  acked, actionable, nobody took it for > grace -> report it and wake the lane, once per window
"""
import json
import os
import time

import pytest

from nougen_shards import codex_pipe, lifecycle_watchdog as wd
from nougen_shards.claim_lifecycle import (
    ClaimLifecycleManager,
    FencingViolationError,
    TaskState as S,
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    monkeypatch.setenv("NOUGEN_CODEX_INBOX", str(inbox))
    monkeypatch.setenv("NOUGEN_HOME", str(tmp_path))
    monkeypatch.setenv("NOUGEN_AGENT", "codex")
    return inbox


@pytest.fixture
def manager(env, tmp_path):
    return ClaimLifecycleManager()


def _stage(mid, text="please implement the thing", **extra):
    codex_pipe.save({"message_id": mid, "thread": "t", "text": text, **extra})


def _ack(mid, **kw):
    return codex_pipe.acknowledge(mid, consumer="codex", thread="t", **kw)


def _take(mid, consumer="codex"):
    return codex_pipe.take(mid, consumer=consumer, thread="t")


def _age_ack(mid, seconds):
    """Make the ack look `seconds` old by rewriting the history timestamps."""
    path = codex_pipe._find_lifecycle_path(mid)
    rec = json.loads(path.read_text(encoding="utf-8"))
    then = time.time() - seconds
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(then))
    for event in rec["history"]:
        event["at"] = stamp
    path.write_text(json.dumps(rec), encoding="utf-8")


def _expire(manager, mid, **cols):
    sets = ", ".join(f"{k} = ?" for k in cols)
    with manager._connect() as conn:
        conn.execute(f"UPDATE claims SET {sets} WHERE msg_id = ?", (*cols.values(), mid))


# --- unclaimed actionable messages ----------------------------------------------

def test_an_empty_inbox_sweeps_clean(env, manager):
    report = wd.sweep()
    assert report["needs_claim"] == [] and report["reclaimed"] == [] and report["stalled"] == []
    assert report["metrics"]["pending_total"] == 0 and report["dry_run"] is False


def test_acked_actionable_and_unclaimed_past_grace_is_reported(env, manager):
    _stage("11111111-0000-4000-8000-000000000001")
    _ack("11111111-0000-4000-8000-000000000001")
    _age_ack("11111111-0000-4000-8000-000000000001", 600)
    report = wd.sweep(dispatch_grace_s=300)
    assert [n["message_id"] for n in report["needs_claim"]] == ["11111111-0000-4000-8000-000000000001"]
    assert report["needs_claim"][0]["age_s"] >= 600
    assert report["metrics"]["oldest_unclaimed_age_s"] >= 600


def test_a_fresh_ack_is_not_yet_a_problem(env, manager):
    _stage("11111111-0000-4000-8000-000000000002")
    _ack("11111111-0000-4000-8000-000000000002")
    report = wd.sweep(dispatch_grace_s=300)
    assert report["needs_claim"] == []
    assert report["metrics"]["pending_total"] == 1 and report["metrics"]["unclaimed_total"] == 1


def test_informational_messages_never_become_obligations(env, manager):
    mid = "11111111-0000-4000-8000-000000000003"
    _stage(mid, text="TOUCHDOWN: radar fix merged. No reply needed.")
    _ack(mid)
    _age_ack(mid, 9999)
    rec = codex_pipe.lifecycle(mid)
    assert rec["actionable"] is False and rec["pending_execution"] is False
    assert rec["classification"]["reason"]
    assert wd.sweep()["needs_claim"] == []


def test_a_claimed_message_is_not_unclaimed(env, manager):
    mid = "11111111-0000-4000-8000-000000000004"
    _stage(mid)
    _take(mid)
    _age_ack(mid, 9999)
    assert wd.sweep(dispatch_grace_s=300)["needs_claim"] == []


# --- waking ---------------------------------------------------------------------

def test_wake_is_called_once_per_window_and_recorded(env, manager):
    mid = "11111111-0000-4000-8000-000000000005"
    _stage(mid)
    _ack(mid)
    _age_ack(mid, 900)
    woken = []
    first = wd.sweep(dispatch_grace_s=300, wake=lambda entry: woken.append(entry["message_id"]) or True)
    assert woken == [mid] and first["woken"] == [mid]
    again = wd.sweep(dispatch_grace_s=300, wake=lambda entry: woken.append("DUP") or True)
    assert woken == [mid] and again["woken"] == []                     # inside the window: no spam
    assert codex_pipe.lifecycle(mid)["wake_count"] == 1
    later = wd.sweep(dispatch_grace_s=300, now=time.time() + 400, wake=lambda e: woken.append("LATER") or True)
    assert woken == [mid, "LATER"] and later["woken"] == [mid]


def test_a_failing_wake_does_not_stop_the_sweep(env, manager):
    mid = "11111111-0000-4000-8000-000000000006"
    _stage(mid)
    _ack(mid)
    _age_ack(mid, 900)

    def boom(entry):
        raise OSError("pipe closed")
    report = wd.sweep(dispatch_grace_s=300, wake=boom)
    assert report["woken"] == [] and report["wake_failed"][0]["message_id"] == mid
    assert "pipe closed" in report["wake_failed"][0]["error"]
    assert [n["message_id"] for n in report["needs_claim"]] == [mid]


def test_wake_returning_false_is_a_failure_not_a_success(env, manager):
    mid = "11111111-0000-4000-8000-000000000007"
    _stage(mid)
    _ack(mid)
    _age_ack(mid, 900)
    report = wd.sweep(dispatch_grace_s=300, wake=lambda e: False)
    assert report["woken"] == [] and report["wake_failed"]
    assert "wake_count" not in codex_pipe.lifecycle(mid)


def test_default_wake_text_tells_the_agent_what_to_run(env, manager):
    text = wd.wake_text({"message_id": "abc", "age_s": 600.4})
    assert "take-msg abc" in text and "10 min" in text


# --- expired leases ---------------------------------------------------------------

def test_an_expired_claim_is_reclaimed_and_the_old_worker_is_fenced(env, manager):
    mid = "22222222-0000-4000-8000-000000000001"
    _stage(mid)
    taken = _take(mid)
    old_epoch = taken["fencing_epoch"]
    _expire(manager, mid, lease_expires_at=time.time() - 5)
    report = wd.sweep()
    assert [r["msg_id"] for r in report["reclaimed"]] == [mid]
    assert manager.get_claim(mid)["state"] == "SUBMITTED"
    rec = codex_pipe.lifecycle(mid)
    assert rec["state"] == "ACKED" and rec["pending_execution"] is True and rec.get("claim_lane") is None
    assert rec["history"][-1]["released"] is True and "lease expired" in rec["history"][-1]["reason"]
    with pytest.raises(FencingViolationError):
        manager.heartbeat(mid, old_epoch, S.WORKING)
    again = codex_pipe.take(mid, consumer="claude", thread="t")
    assert again["fencing_epoch"] == old_epoch + 1 and again["lifecycle_state"] == "CLAIMED"


def test_a_released_message_shows_up_as_unclaimed_after_the_grace(env, manager):
    mid = "22222222-0000-4000-8000-000000000002"
    _stage(mid)
    _take(mid)
    _expire(manager, mid, lease_expires_at=time.time() - 5)
    wd.sweep()
    assert wd.sweep(dispatch_grace_s=300)["needs_claim"] == []         # just released
    later = wd.sweep(dispatch_grace_s=300, now=time.time() + 600)
    assert [n["message_id"] for n in later["needs_claim"]] == [mid]


# --- stalled workers --------------------------------------------------------------

def test_a_worker_that_heartbeats_but_never_checkpoints_is_reclaimed(env, manager):
    mid = "33333333-0000-4000-8000-000000000001"
    _stage(mid)
    epoch = _take(mid)["fencing_epoch"]
    manager.heartbeat(mid, epoch, S.WORKING)
    _expire(manager, mid, claimed_at=time.time() - 5000)
    report = wd.sweep(no_progress_s=900)
    assert [s["msg_id"] for s in report["stalled"]] == [mid]
    assert manager.get_claim(mid)["state"] == "SUBMITTED"
    assert codex_pipe.lifecycle(mid)["state"] == "ACKED"
    with pytest.raises(FencingViolationError):
        manager.checkpoint(mid, epoch, {"late": True})


def test_a_worker_that_checkpoints_is_not_stalled(env, manager):
    mid = "33333333-0000-4000-8000-000000000002"
    _stage(mid)
    epoch = _take(mid)["fencing_epoch"]
    _expire(manager, mid, claimed_at=time.time() - 5000)
    manager.checkpoint(mid, epoch, {"tests": 3})
    assert wd.sweep(no_progress_s=900)["stalled"] == []
    assert manager.get_claim(mid)["state"] == "WORKING"


# --- dry run ----------------------------------------------------------------------

def test_dry_run_reports_everything_and_changes_nothing(env, manager):
    expired, stalled, quiet = ("44444444-0000-4000-8000-00000000000%d" % i for i in (1, 2, 3))
    for mid in (expired, stalled, quiet):
        _stage(mid)
    _take(expired)
    _expire(manager, expired, lease_expires_at=time.time() - 5)
    epoch = _take(stalled)["fencing_epoch"]
    manager.heartbeat(stalled, epoch, S.WORKING)
    _expire(manager, stalled, claimed_at=time.time() - 5000)
    _ack(quiet)
    _age_ack(quiet, 900)
    woken = []
    report = wd.sweep(dry_run=True, dispatch_grace_s=300, no_progress_s=900, wake=lambda e: woken.append(e) or True)
    assert report["dry_run"] is True
    assert [r["msg_id"] for r in report["reclaimed"]] == [expired]
    assert [s["msg_id"] for s in report["stalled"]] == [stalled]
    assert [n["message_id"] for n in report["needs_claim"]] == [quiet]
    assert woken == [] and report["woken"] == []
    assert manager.get_claim(expired)["state"] == "CLAIMED"          # claimed, never heartbeated: untouched
    assert manager.get_claim(stalled)["state"] == "WORKING"
    assert "wake_count" not in codex_pipe.lifecycle(quiet)


def test_terminal_messages_are_left_alone(env, manager):
    mid = "55555555-0000-4000-8000-000000000001"
    _stage(mid)
    _take(mid)
    path = codex_pipe._find_lifecycle_path(mid)
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec.update(state="COMPLETE", pending_execution=False)
    path.write_text(json.dumps(rec), encoding="utf-8")
    _expire(manager, mid, lease_expires_at=time.time() - 5)
    report = wd.sweep()
    assert report["needs_claim"] == [] and codex_pipe.lifecycle(mid)["state"] == "COMPLETE"


def test_run_loop_runs_the_requested_number_of_sweeps(env, manager):
    sleeps = []
    reports = wd.run_loop(every_s=60, iterations=3, sleep=sleeps.append)
    assert len(reports) == 3 and sleeps == [60, 60]


# --- requeue / cancel through codex_pipe ---------------------------------------------

def _failed(mid, manager):
    _stage(mid)
    epoch = _take(mid)["fencing_epoch"]
    manager.heartbeat(mid, epoch, S.WORKING)
    manager.fail(mid, epoch, "tests red")
    path = codex_pipe._find_lifecycle_path(mid)
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec.update(state="FAILED", pending_execution=False)
    path.write_text(json.dumps(rec), encoding="utf-8")
    return epoch


def test_requeue_makes_a_failed_message_claimable_again(env, manager):
    mid = "66666666-0000-4000-8000-000000000001"
    epoch = _failed(mid, manager)
    out = codex_pipe.requeue(mid, "fixed the fixture")
    assert out["status"] == "requeued" and out["requeue_count"] == 1
    rec = codex_pipe.lifecycle(mid)
    assert rec["state"] == "ACKED" and rec["pending_execution"] is True
    assert codex_pipe.take(mid, consumer="claude", thread="t")["fencing_epoch"] == epoch + 1


def test_requeue_is_refused_for_a_message_that_did_not_fail(env, manager):
    mid = "66666666-0000-4000-8000-000000000002"
    _stage(mid)
    _take(mid)
    assert codex_pipe.requeue(mid, "x")["status"] == "not_requeueable"
    assert codex_pipe.requeue("nope", "x")["status"] == "no_lifecycle"


def test_requeue_stops_after_the_bound(env, manager):
    mid = "66666666-0000-4000-8000-000000000003"
    _failed(mid, manager)
    with manager._connect() as conn:
        conn.execute("UPDATE claims SET requeue_count = 3 WHERE msg_id = ?", (mid,))
    out = codex_pipe.requeue(mid, "again")
    assert out["status"] == "requeue_refused" and "needs a person" in out["error"]
    assert codex_pipe.lifecycle(mid)["state"] == "FAILED"


def test_cancel_withdraws_the_message_and_fences_the_worker(env, manager):
    mid = "77777777-0000-4000-8000-000000000001"
    _stage(mid)
    epoch = _take(mid)["fencing_epoch"]
    out = codex_pipe.cancel(mid, "operator withdrew it")
    assert out["status"] == "canceled"
    rec = codex_pipe.lifecycle(mid)
    assert rec["state"] == "CANCELED" and rec["pending_execution"] is False
    with pytest.raises(FencingViolationError):
        manager.heartbeat(mid, epoch, S.WORKING)
    assert codex_pipe.pending_execution() == []
    assert codex_pipe.cancel(mid, "again")["status"] == "already_terminal"
    assert codex_pipe.advance(mid, "EXECUTING", consumer="codex", fencing_epoch=epoch)["advanced"] is False


def test_cancel_before_any_claim_still_works(env, manager):
    mid = "77777777-0000-4000-8000-000000000002"
    _stage(mid)
    _ack(mid)
    assert codex_pipe.cancel(mid, "not needed")["status"] == "canceled"
    assert codex_pipe.lifecycle(mid)["state"] == "CANCELED"


# --- commit-time authority --------------------------------------------------------------

def test_authority_check_denies_a_reassigned_or_terminal_claim(env, manager):
    mid = "88888888-0000-4000-8000-000000000001"
    _stage(mid)
    taken = _take(mid)
    epoch = taken["fencing_epoch"]
    lane = taken["claim_lane"]
    check = codex_pipe._commit_authority(mid, None, lane, epoch)
    claim = manager.get_claim(mid)
    assert check(claim) == (True, "")
    assert check(dict(claim, fencing_epoch=epoch + 1))[0] is False
    assert check(dict(claim, agent_lane="someone-else"))[0] is False
    path = codex_pipe._find_lifecycle_path(mid)
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["state"] = "CANCELED"
    path.write_text(json.dumps(rec), encoding="utf-8")
    ok, why = check(claim)
    assert ok is False and "CANCELED" in why
    assert codex_pipe._commit_authority("missing", None, lane, epoch)(claim)[0] is False


def test_checkpoint_through_advance_counts_as_progress(env, manager, monkeypatch):
    """advance(CHECKPOINTED) must call manager.checkpoint, or a worker doing real work looks stalled."""
    mid = "88888888-0000-4000-8000-000000000002"
    _stage(mid)
    epoch = _take(mid)["fencing_epoch"]
    seen = []
    real = ClaimLifecycleManager.checkpoint

    def spy(self_, msg_id, fencing_epoch, evidence, *a, **k):
        seen.append((msg_id, fencing_epoch))
        return real(self_, msg_id, fencing_epoch, evidence, *a, **k)

    monkeypatch.setattr(ClaimLifecycleManager, "checkpoint", spy)
    monkeypatch.setattr(codex_pipe, "verify_lifecycle_evidence", lambda state, evidence, **kw: {
        "verified": True, "normalized_evidence": {"kind": "checkpoint", "note": "x"}, "evidence_sha256": "a" * 64})
    assert codex_pipe.advance(mid, "EXECUTING", consumer="codex", fencing_epoch=epoch)["advanced"]
    out = codex_pipe.advance(mid, "CHECKPOINTED", {"kind": "checkpoint", "note": "x"}, consumer="codex", fencing_epoch=epoch)
    assert out["advanced"], out
    assert seen == [(mid, epoch)]
    assert manager.get_claim(mid)["progress_count"] == 1


def test_complete_is_refused_when_authority_vanishes_before_the_commit(env, manager, monkeypatch):
    mid = "88888888-0000-4000-8000-000000000003"
    _stage(mid)
    epoch = _take(mid)["fencing_epoch"]
    monkeypatch.setattr(codex_pipe, "verify_lifecycle_evidence", lambda state, evidence, **kw: {
        "verified": True, "normalized_evidence": {"kind": "complete"}, "evidence_sha256": "b" * 64})
    assert codex_pipe.advance(mid, "EXECUTING", consumer="codex", fencing_epoch=epoch)["advanced"]
    real_commit = ClaimLifecycleManager.commit_step

    def revoke_then_commit(self_, msg_id, fencing_epoch, key, authority_check=None):
        path = codex_pipe._find_lifecycle_path(msg_id)
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["state"] = "CANCELED"                                  # the operator cancels mid-flight
        path.write_text(json.dumps(rec), encoding="utf-8")
        return real_commit(self_, msg_id, fencing_epoch, key, authority_check=authority_check)

    monkeypatch.setattr(ClaimLifecycleManager, "commit_step", revoke_then_commit)
    out = codex_pipe.advance(mid, "COMPLETE", {"kind": "complete"}, consumer="codex", fencing_epoch=epoch)
    assert out["advanced"] is False and out["status"] == "authority_expired"
    assert manager.get_claim(mid)["state"] == "VERIFYING"          # nothing was committed
    assert os.environ.get("NOUGEN_HOME")


# --- the CLI -----------------------------------------------------------------------------

def test_cli_sweep_requeue_and_cancel(env, manager):
    from nougen_shards import live
    mid = "99999999-0000-4000-8000-000000000001"
    _stage(mid)
    _ack(mid)
    _age_ack(mid, 900)
    out = json.loads(live.handle_live_command(["sweep-msg", "--dry-run", "--grace", "300"]))
    assert out["dry_run"] is True and out["needs_claim"][0]["message_id"] == mid
    done = json.loads(live.handle_live_command(["cancel-msg", mid, "not", "needed", "any", "more"]))
    assert done["status"] == "canceled"
    failed = json.loads(live.handle_live_command(["requeue-msg", mid, "retry"]))
    assert failed["status"] == "not_requeueable"
    assert "sweep-msg" in live.handle_live_command(["no-such-command"])


def test_cli_sweep_rejects_a_bad_number(env, manager):
    from nougen_shards import live
    out = json.loads(live.handle_live_command(["sweep-msg", "--grace", "soon"]))
    assert out["status"] == "usage_error" and "--grace" in out["error"]


# --- default wake: real NouGenMsgBus.live_ping result shapes --------------------------------

@pytest.mark.parametrize("result,expected", [
    ({"claude_pipes": {"delivered": [{"socket": "x", "attempt": 1}], "errors": []}}, True),
    ({"antigravity": {"status": "delivered", "pipe_delivered": True}}, True),
    ({"codex": {"status": "queued", "queue_accepted": True}}, True),
    ({"codex": {"status": "saved", "pipe_delivered": False}}, False),     # filed in an inbox, nobody woken
    ({"claude_pipes": {"delivered": [], "errors": ["no live session"]}}, False),
    ({"skipped": "addressed to blade, not this node"}, False),
    ({}, False),
    (None, False),
    ({"claude_pipes": {"delivered": []}, "antigravity": {"status": "delivered"}}, True),   # any lane is enough
])
def test_delivery_is_read_from_the_real_result_shapes(result, expected):
    assert wd._delivered(result) is expected


def test_default_wake_pings_the_lane_that_acked_with_the_watchdog_text(env, manager, monkeypatch):
    from nougen_shards.nougenmsg import NouGenMsgBus
    calls = []

    def fake(target, text, *a, **k):
        calls.append((target, text))
        return {"codex": {"status": "queued"}}
    monkeypatch.setattr(NouGenMsgBus, "live_ping", staticmethod(fake) if isinstance(
        NouGenMsgBus.__dict__.get("live_ping"), staticmethod) else classmethod(lambda cls, t, x, *a, **k: fake(t, x)))
    assert wd.default_wake({"message_id": "abc", "age_s": 700, "consumer": "claude"}) is True
    assert calls and calls[0][0] == "claude" and "take-msg abc" in calls[0][1]

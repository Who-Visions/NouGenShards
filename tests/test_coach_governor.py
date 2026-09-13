"""Tests for the ENFORCED coach_governor (vs the advisory-only quota/reasoning
governors it composes with). Each test maps to a move in
wargames/coach-governor-hardening.md."""
import time

import pytest

from nougen_shards.coach_governor import (
    BudgetExceeded,
    CircuitLevel,
    CoachGovernor,
    FanoutExceeded,
    KillSwitchActive,
    LoopSuspected,
)


def make_gov(tmp_path):
    return CoachGovernor(telemetry_path=str(tmp_path / "coach_governor.jsonl"))


def test_ceiling_denies_before_spend(tmp_path):
    gov = make_gov(tmp_path)
    gov.register_scope("m/p/a/t", ceiling=100.0)
    lease = gov.acquire_lease("m/p/a/t", 60.0)
    lease.settle(60.0)
    with pytest.raises(BudgetExceeded):
        gov.acquire_lease("m/p/a/t", 50.0)
    # denied lease must not have touched the ledger
    status = gov.status("m/p/a/t")
    assert status["spent"] == 60.0
    assert status["reserved"] == 0.0


def test_lease_reserves_before_caller_work_runs(tmp_path):
    """The core fix: denial happens pre-call, not after spend already
    happened (the exact advisory-only failure mode)."""
    gov = make_gov(tmp_path)
    gov.register_scope("m/p/a/t", ceiling=10.0)
    work_ran = []
    with pytest.raises(BudgetExceeded):
        lease = gov.acquire_lease("m/p/a/t", 20.0)
        work_ran.append(True)  # never reached
    assert work_ran == []
    assert gov.status("m/p/a/t")["spent"] == 0.0


def test_partial_settle_refunds_estimate(tmp_path):
    gov = make_gov(tmp_path)
    gov.register_scope("m/p/a/t", ceiling=100.0)
    lease = gov.acquire_lease("m/p/a/t", 50.0)
    lease.settle(10.0)  # actual usage much less than the estimate
    status = gov.status("m/p/a/t")
    assert status["spent"] == 10.0
    assert status["reserved"] == 0.0
    # room remains for a follow-up lease that the naive estimate would've blocked
    gov.acquire_lease("m/p/a/t", 80.0)


def test_kill_switch_blocks_all_subsequent_leases(tmp_path):
    gov = make_gov(tmp_path)
    gov.register_scope("m/p/a/t", ceiling=1000.0)
    gov.acquire_lease("m/p/a/t", 1.0).settle()
    gov.set_kill("m", reason="GM emergency stop")
    with pytest.raises(KillSwitchActive):
        gov.acquire_lease("m/p/a/t", 1.0)
    with pytest.raises(KillSwitchActive):
        gov.acquire_lease("m/other/agent/t2", 1.0)
    gov.clear_kill("m", reason="resolved")
    gov.acquire_lease("m/p/a/t", 1.0)  # works again


def test_kill_on_ancestor_blocks_descendant_scope(tmp_path):
    gov = make_gov(tmp_path)
    gov.set_kill("m/p", reason="provider outage")
    with pytest.raises(KillSwitchActive):
        gov.acquire_lease("m/p/a/t", 1.0)


def test_fanout_limit_denies_overcommit_and_settle_frees_slot(tmp_path):
    gov = make_gov(tmp_path)
    gov.register_scope("m/p/a/t", ceiling=1000.0)
    leases = [gov.acquire_lease("m/p/a/t", 1.0, kind="child_agent") for _ in range(8)]
    with pytest.raises(FanoutExceeded):
        gov.acquire_lease("m/p/a/t", 1.0, kind="child_agent")
    leases[0].settle()
    # freeing one slot allows a 9th sequential (not just concurrent) lease
    gov.acquire_lease("m/p/a/t", 1.0, kind="child_agent")


def test_burn_velocity_loop_detection(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_COACH_MAX_BURN_COUNT", "3")
    monkeypatch.setenv("NOUGEN_COACH_BURN_WINDOW_S", "60")
    import importlib
    import nougen_shards.coach_governor as cg
    importlib.reload(cg)
    gov = cg.CoachGovernor(telemetry_path=str(tmp_path / "t.jsonl"))
    gov.register_scope("m/p/a/t", ceiling=1000.0)
    for _ in range(3):
        gov.acquire_lease("m/p/a/t", 5.0).settle(5.0)
    with pytest.raises(cg.LoopSuspected):
        gov.acquire_lease("m/p/a/t", 5.0)
    importlib.reload(cg)  # restore module-level env-derived constants


def test_varied_amounts_do_not_trip_loop_detector(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_COACH_MAX_BURN_COUNT", "3")
    monkeypatch.setenv("NOUGEN_COACH_BURN_WINDOW_S", "60")
    import importlib
    import nougen_shards.coach_governor as cg
    importlib.reload(cg)
    gov = cg.CoachGovernor(telemetry_path=str(tmp_path / "t.jsonl"))
    gov.register_scope("m/p/a/t", ceiling=1000.0)
    for amt in (1.0, 5.0, 20.0):
        gov.acquire_lease("m/p/a/t", amt).settle(amt)
    gov.acquire_lease("m/p/a/t", 3.0).settle(3.0)  # not denied: amounts too varied
    importlib.reload(cg)


def test_circuit_levels_progress_with_spend(tmp_path):
    gov = make_gov(tmp_path)
    gov.register_scope("m/p/a/t", ceiling=100.0)
    assert gov.level("m/p/a/t") == CircuitLevel.NORMAL
    gov.acquire_lease("m/p/a/t", 65.0).settle(65.0)
    assert gov.level("m/p/a/t") == CircuitLevel.WATCH
    gov.acquire_lease("m/p/a/t", 20.0).settle(20.0)  # 85%
    assert gov.level("m/p/a/t") == CircuitLevel.THROTTLE


def test_containment_denies_non_reversible_work(tmp_path):
    gov = make_gov(tmp_path)
    gov.register_scope("m/p/a/t", ceiling=100.0)
    gov.acquire_lease("m/p/a/t", 95.0).settle(95.0)  # -> CONTAINMENT
    with pytest.raises(Exception):
        gov.acquire_lease("m/p/a/t", 0.1, consequence_class=3)
    gov.acquire_lease("m/p/a/t", 0.1, consequence_class=1)  # reversible still allowed


def test_checkpoint_gate_requires_explicit_ack(tmp_path):
    gov = make_gov(tmp_path)
    gov.register_scope("m/p/a/t", ceiling=100.0)
    gov.acquire_lease("m/p/a/t", 98.0).settle(98.0)  # crosses CHECKPOINT_PCT
    with pytest.raises(Exception):
        gov.acquire_lease("m/p/a/t", 0.1)
    gov.ack_checkpoint("m/p/a/t", "reviewed by GM")
    gov.acquire_lease("m/p/a/t", 0.1)


def test_telemetry_attribution_written(tmp_path):
    gov = make_gov(tmp_path)
    gov.register_scope("m/p/a/t", ceiling=100.0)
    gov.acquire_lease("m/p/a/t", 1.0, provider="anthropic", model="sonnet-5",
                       agent="claude-cli", task="coach-hardening", tool="Bash").settle(1.0)
    import json
    lines = (tmp_path / "coach_governor.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    rec = json.loads(lines[0])
    for key in ("ts", "machine", "provider", "model", "agent", "task", "tool",
                "scope_path", "event", "amount", "level"):
        assert key in rec


def test_ceiling_bump_does_not_reset_spend(tmp_path):
    gov = make_gov(tmp_path)
    gov.register_scope("m/p/a/t", ceiling=10.0)
    gov.acquire_lease("m/p/a/t", 10.0).settle(10.0)
    gov.register_scope("m/p/a/t", ceiling=20.0)
    assert gov.status("m/p/a/t")["spent"] == 10.0
    gov.acquire_lease("m/p/a/t", 10.0)  # room from the bump, not a reset


def test_singleton_shared_across_callers():
    from nougen_shards.coach_governor import get_default_governor
    g1 = get_default_governor()
    g2 = get_default_governor()
    assert g1 is g2

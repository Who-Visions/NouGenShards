"""Hardcade CRON OUT tests (leg 20260923T165947Z, done-when items 3-5).

Covers: idempotent run_key, overlap policies, misfire policies, retry vs
recurrence, timezone-aware next-fire, governance refusal, the closed state
machine, and parity between the local adapter and the cron-expression
compiler against the same schedule contract.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards.hardcade_cron_out import (  # noqa: E402
    Cadence, CronExpressionAdapter, CronOutError, CronOutSchedule,
    GovernanceRefused, Governance, IdempotencyViolation, InvalidTransition,
    LifecycleState, LocalLoopAdapter, MisfirePolicy, OverlapPolicy,
    Reliability, ScheduleState, Verification, cron_out, parse_cron_out_command,
    run_key,
)

UTC = timezone.utc
NY = "America/New_York"


def schedule(**over):
    defaults = dict(
        schedule_id="integrity-hourly", task_ref="shard_integrity_sweep",
        task_revision="current_verified",
        cadence=Cadence("interval", "15m", NY),
        reliability=Reliability(),
        governance=Governance(lease_required=False, budget_required=False),
    )
    defaults.update(over)
    return CronOutSchedule(**defaults)


# --------------------------------------------------------- schedule contract
def test_timezone_is_mandatory():
    with pytest.raises(ValueError):
        Cadence("interval", "15m", "")


def test_unknown_timezone_fails_fast_at_construction_not_at_fire_time():
    with pytest.raises(Exception):
        Cadence("interval", "15m", "Nowhere/Fake")


def test_interval_syntax_validated_eagerly():
    with pytest.raises(ValueError):
        Cadence("interval", "not-an-interval", NY)


def test_retry_none_with_multiple_attempts_is_rejected():
    """retry != recurrence: max_attempts>1 needs an actual retry policy."""
    from nougen_shards.hardcade_cron_out import RetryPolicy
    with pytest.raises(ValueError):
        Reliability(retry=RetryPolicy.NONE, max_attempts=3)


def test_edited_bumps_generation():
    s = schedule()
    s2 = s.edited(cadence=Cadence("interval", "30m", NY))
    assert s2.generation == s.generation + 1
    assert s.generation == 1  # original untouched (frozen)


# ----------------------------------------------------------------- run_key
def test_run_key_is_deterministic():
    s = schedule()
    t = datetime(2026, 9, 23, 15, 0, tzinfo=UTC)
    assert run_key(s, t) == run_key(s, t)


def test_run_key_changes_with_generation():
    s = schedule()
    t = datetime(2026, 9, 23, 15, 0, tzinfo=UTC)
    s2 = s.edited()
    assert run_key(s, t) != run_key(s2, t)


def test_run_key_requires_timezone_aware_input():
    s = schedule()
    with pytest.raises(ValueError):
        run_key(s, datetime(2026, 9, 23, 15, 0))  # naive


def test_a_retry_keeps_the_same_run_key_new_attempt_id():
    """The leg's own worked example: attempt_1 failed, attempt_2 succeeded,
    run_key unchanged, modelled as ONE logical run with two attempts."""
    s = schedule(reliability=Reliability(overlap=OverlapPolicy.ALLOW, max_attempts=2,
                                         retry=__import__("nougen_shards.hardcade_cron_out",
                                                          fromlist=["RetryPolicy"]).RetryPolicy.FIXED))
    st = ScheduleState(s)
    st.transition(LifecycleState.ARMED)
    st.transition(LifecycleState.DUE)
    t = datetime(2026, 9, 23, 15, 0, tzinfo=UTC)

    key1, attempt1 = st.begin_run(t, "phoebus")
    st.finish_run(key1, attempt1, "failure")
    key2, attempt2 = st.begin_run(t, "phoebus")  # retry: same nominal fire time
    st.finish_run(key2, attempt2, "success")

    assert key1 == key2
    assert attempt1 == 1 and attempt2 == 2
    receipt = st.receipts[key1]
    assert len(receipt.attempts) == 2
    assert receipt.final_outcome == "success"


# --------------------------------------------------------------- idempotency
def test_two_scheduler_fires_of_the_same_nominal_time_do_not_double_run():
    """Duplicate-fire simulation: a scheduler that (bug, restart, clock skew)
    fires the same nominal occurrence twice must not run it twice once the
    first attempt has already succeeded.

    max_attempts is deliberately generous (3) here so the assertion isolates
    the idempotency guard specifically -- with max_attempts=1 (the default)
    a low attempt ceiling would incidentally block the second call too, and
    the test would pass for the wrong reason. Confirmed by negative control:
    removing the idempotency check while max_attempts stayed at 1 still
    failed here, but for CronOutError('exhausted max_attempts'), not
    IdempotencyViolation -- proving the two guards are distinct and this
    version is needed to test the right one."""
    from nougen_shards.hardcade_cron_out import RetryPolicy
    s = schedule(reliability=Reliability(overlap=OverlapPolicy.ALLOW,
                                         retry=RetryPolicy.FIXED, max_attempts=3))
    st = ScheduleState(s)
    st.transition(LifecycleState.ARMED)
    st.transition(LifecycleState.DUE)
    t = datetime(2026, 9, 23, 15, 0, tzinfo=UTC)

    key, attempt = st.begin_run(t, "phoebus")
    st.finish_run(key, attempt, "success")

    with pytest.raises(IdempotencyViolation):
        st.begin_run(t, "phoebus")  # duplicate fire of an already-succeeded occurrence


def test_negative_control_a_new_nominal_time_is_not_blocked_by_idempotency():
    """Confirms the previous test is checking idempotency, not just refusing
    all subsequent begin_run calls outright."""
    s = schedule(reliability=Reliability(overlap=OverlapPolicy.ALLOW))
    st = ScheduleState(s)
    st.transition(LifecycleState.ARMED)
    st.transition(LifecycleState.DUE)
    t1 = datetime(2026, 9, 23, 15, 0, tzinfo=UTC)
    t2 = datetime(2026, 9, 23, 15, 15, tzinfo=UTC)

    key1, a1 = st.begin_run(t1, "phoebus")
    st.finish_run(key1, a1, "success")
    key2, a2 = st.begin_run(t2, "phoebus")  # a genuinely new occurrence
    assert key2 != key1
    assert st.finish_run(key2, a2, "success").final_outcome == "success"


# ------------------------------------------------------------------ overlap
def test_overlap_forbid_refuses_a_second_concurrent_occurrence():
    s = schedule(reliability=Reliability(overlap=OverlapPolicy.FORBID))
    st = ScheduleState(s)
    st.transition(LifecycleState.ARMED)
    st.transition(LifecycleState.DUE)
    t1 = datetime(2026, 9, 23, 15, 0, tzinfo=UTC)
    t2 = datetime(2026, 9, 23, 15, 15, tzinfo=UTC)

    st.begin_run(t1, "phoebus")  # left running, not finished
    with pytest.raises(CronOutError):
        st.begin_run(t2, "phoebus")


def test_overlap_allow_permits_a_second_concurrent_occurrence():
    s = schedule(reliability=Reliability(overlap=OverlapPolicy.ALLOW))
    st = ScheduleState(s)
    st.transition(LifecycleState.ARMED)
    st.transition(LifecycleState.DUE)
    t1 = datetime(2026, 9, 23, 15, 0, tzinfo=UTC)
    t2 = datetime(2026, 9, 23, 15, 15, tzinfo=UTC)

    key1, _ = st.begin_run(t1, "phoebus")
    key2, _ = st.begin_run(t2, "phoebus")  # does not raise
    assert key1 != key2


# ------------------------------------------------------------------ misfire
def test_misfire_coalesce_latest_collapses_missed_fires_to_one():
    s = schedule(cadence=Cadence("interval", "15m", NY),
                reliability=Reliability(misfire=MisfirePolicy.COALESCE_LATEST))
    adapter = LocalLoopAdapter(s, operation=lambda: "success")
    # Nothing has ticked in 2 hours -> 8 missed 15-minute occurrences.
    start = datetime(2026, 9, 23, 10, 0, tzinfo=ZoneInfo(NY))
    adapter._last_fire = start
    now = start + timedelta(hours=2)
    receipt = adapter.tick(now=now)
    assert receipt is not None
    # Exactly one run happened, and its receipts dict has one entry.
    assert len(adapter.state.receipts) == 1


def test_misfire_all_backfills_every_missed_occurrence():
    s = schedule(cadence=Cadence("interval", "15m", NY),
                reliability=Reliability(misfire=MisfirePolicy.ALL, overlap=OverlapPolicy.ALLOW))
    adapter = LocalLoopAdapter(s, operation=lambda: "success")
    start = datetime(2026, 9, 23, 10, 0, tzinfo=ZoneInfo(NY))
    adapter._last_fire = start
    now = start + timedelta(hours=1)  # 4 missed occurrences
    adapter.tick(now=now)
    assert len(adapter.state.receipts) == 4


def test_misfire_skip_drops_every_missed_occurrence():
    s = schedule(cadence=Cadence("interval", "15m", NY),
                reliability=Reliability(misfire=MisfirePolicy.SKIP))
    adapter = LocalLoopAdapter(s, operation=lambda: "success")
    start = datetime(2026, 9, 23, 10, 0, tzinfo=ZoneInfo(NY))
    adapter._last_fire = start
    now = start + timedelta(hours=1)
    receipt = adapter.tick(now=now)
    assert receipt is None
    assert len(adapter.state.receipts) == 0


# --------------------------------------------------------------- next fire
def test_next_fire_after_is_timezone_grid_anchored_across_restarts():
    """Restarting the process must land on the SAME grid, not a new one
    anchored to whenever the process happened to restart."""
    s = schedule(cadence=Cadence("interval", "15m", NY))
    t = datetime(2026, 9, 23, 15, 3, tzinfo=UTC)
    n1 = s.next_fire_after(t)
    # A "restart" a few seconds later must compute the identical next fire.
    n2 = s.next_fire_after(t + timedelta(seconds=5))
    assert n1 == n2


def test_next_fire_after_cron_kind_is_not_implemented_here():
    s = schedule(cadence=Cadence("cron", "*/15 * * * *", NY))
    with pytest.raises(CronOutError):
        s.next_fire_after(datetime.now(UTC))


# ------------------------------------------------------------------ governance
def test_lease_required_but_absent_refuses_the_run():
    s = schedule(governance=Governance(lease_required=True, budget_required=False, lease_token=None))
    st = ScheduleState(s)
    st.transition(LifecycleState.ARMED)
    st.transition(LifecycleState.DUE)
    with pytest.raises(GovernanceRefused):
        st.begin_run(datetime(2026, 9, 23, 15, 0, tzinfo=UTC), "phoebus")


def test_lease_granted_allows_the_run():
    s = schedule(governance=Governance(lease_required=True, budget_required=False, lease_token="lease-1"))
    st = ScheduleState(s)
    st.transition(LifecycleState.ARMED)
    st.transition(LifecycleState.DUE)
    key, attempt = st.begin_run(datetime(2026, 9, 23, 15, 0, tzinfo=UTC), "phoebus")
    assert key


def test_kill_switch_refuses_regardless_of_lease():
    s = schedule(governance=Governance(lease_required=True, budget_required=False,
                                       lease_token="lease-1", killed=True))
    st = ScheduleState(s)
    st.transition(LifecycleState.ARMED)
    st.transition(LifecycleState.DUE)
    with pytest.raises(GovernanceRefused):
        st.begin_run(datetime(2026, 9, 23, 15, 0, tzinfo=UTC), "phoebus")


def test_governor_containment_level_suspends_regardless_of_local_state():
    """CoachGovernor integration point: a fleet-wide CONTAINMENT level must
    override this schedule's own state machine, not just be advisory."""
    s = schedule()
    st = ScheduleState(s)
    st.transition(LifecycleState.ARMED)
    st.transition(LifecycleState.DUE)
    st.apply_governor_level("CONTAINMENT")
    assert st.state is LifecycleState.SUSPENDED


# ------------------------------------------------------------- state machine
def test_state_machine_is_closed_illegal_edges_refused():
    s = schedule()
    st = ScheduleState(s)
    assert st.state is LifecycleState.CRONNED
    with pytest.raises(InvalidTransition):
        st.transition(LifecycleState.RUNNING)  # cannot skip ARMED/DUE/LEASED


def test_full_happy_path_sequence_matches_the_leg_verbatim():
    s = schedule(governance=Governance(lease_required=False, budget_required=False))
    st = ScheduleState(s)
    for target in (LifecycleState.ARMED, LifecycleState.DUE):
        st.transition(target)
    t = datetime(2026, 9, 23, 15, 0, tzinfo=UTC)
    key, attempt = st.begin_run(t, "phoebus")
    assert st.state is LifecycleState.RUNNING
    st.finish_run(key, attempt, "success")
    assert st.state is LifecycleState.DUE  # RECEIPTED -> SLEEPING -> DUE, verbatim from the leg


def test_terminated_is_a_true_terminal_state():
    s = schedule()
    st = ScheduleState(s)
    st.transition(LifecycleState.ARMED)
    st.transition(LifecycleState.TERMINATED)
    with pytest.raises(InvalidTransition):
        st.transition(LifecycleState.ARMED)


# ------------------------------------------------------------------ adapters
def test_cron_expression_adapter_compiles_common_intervals():
    assert CronExpressionAdapter.compile(schedule(cadence=Cadence("interval", "15m", NY))) == "*/15 * * * *"
    assert CronExpressionAdapter.compile(schedule(cadence=Cadence("interval", "1h", NY))) == "0 */1 * * *"
    assert CronExpressionAdapter.compile(schedule(cadence=Cadence("interval", "1d", NY))) == "0 0 */1 * *"


def test_cron_expression_adapter_passes_through_explicit_cron_cadence():
    s = schedule(cadence=Cadence("cron", "0 3 * * *", NY))
    assert CronExpressionAdapter.compile(s) == "0 3 * * *"


def test_cron_expression_adapter_refuses_sub_minute_intervals():
    with pytest.raises(CronOutError):
        CronExpressionAdapter.compile(schedule(cadence=Cadence("interval", "30s", NY)))


def test_local_adapter_and_cron_adapter_agree_on_the_same_schedule_contract():
    """Both adapters are compiled/driven from the SAME CronOutSchedule value
    -- proving the schedule really is backend-neutral, not tied to one
    adapter's internals."""
    s = schedule(cadence=Cadence("interval", "15m", NY))
    cron_expr = CronExpressionAdapter.compile(s)
    adapter = LocalLoopAdapter(s, operation=lambda: "success")
    assert cron_expr == "*/15 * * * *"
    assert adapter.schedule is s
    assert adapter.state.schedule.cadence.every == "15m"


def test_local_adapter_runs_and_receipts_a_due_occurrence():
    s = schedule(cadence=Cadence("interval", "15m", NY))
    adapter = LocalLoopAdapter(s, operation=lambda: "success")
    start = datetime(2026, 9, 23, 10, 0, tzinfo=ZoneInfo(NY))
    adapter._last_fire = start
    receipt = adapter.tick(now=start + timedelta(minutes=15))
    assert receipt is not None and receipt.final_outcome == "success"


def test_local_adapter_records_failure_and_reraises():
    def boom():
        raise RuntimeError("operation failed")
    s = schedule(cadence=Cadence("interval", "15m", NY))
    adapter = LocalLoopAdapter(s, operation=boom)
    start = datetime(2026, 9, 23, 10, 0, tzinfo=ZoneInfo(NY))
    adapter._last_fire = start
    with pytest.raises(RuntimeError):
        adapter.tick(now=start + timedelta(minutes=15))
    receipt = list(adapter.state.receipts.values())[0]
    assert receipt.final_outcome == "failure"


# ------------------------------------------------------------------ grammar
@pytest.mark.parametrize("text,expected_operation", [
    ("Cron out the tracker reconciliation every hour.", "the tracker reconciliation"),
    ("Cron this out nightly.", "nightly"),
    ("Cron out Dream Lane at 3 AM.", "Dream Lane at 3 AM"),
    ("Cron that sweep out every fifteen minutes, forbid overlap.", "sweep"),
])
def test_operator_grammar_examples_from_the_leg_all_parse_without_crashing(text, expected_operation):
    result = parse_cron_out_command(text)
    assert result["operation"] == expected_operation


def test_formal_grammar_extracts_every_clause_precisely():
    result = parse_cron_out_command("CRON OUT the sweep EVERY 15m TZ America/New_York OVERLAP forbid")
    assert result["every_interval"] == "15m"
    assert result["tz"] == NY
    assert result["overlap"] == "forbid"


def test_non_cron_out_text_is_refused_not_silently_accepted():
    with pytest.raises(CronOutError):
        parse_cron_out_command("just do the thing")


def test_cron_out_builder_produces_a_usable_schedule():
    s = cron_out("shard integrity sweep", "current_verified", Cadence("interval", "15m", NY))
    assert s.task_ref == "shard integrity sweep"
    assert s.schedule_id == "shard_integrity_sweep"
    assert isinstance(s.verification, Verification) and s.verification.receipt_required

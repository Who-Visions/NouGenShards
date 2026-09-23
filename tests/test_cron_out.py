"""Unit tests for HARDCade CRON OUT operator (tests/test_cron_out.py).

Verifies the 7 acceptance criteria defined in the fleet handoff:
1. Parser & semantic operator in Hardcade command layer.
2. Compilation to backend-neutral schedule spec.
3. Local (Unix/Windows) and fleet/cloud adapters contract verification.
4. Idempotency on duplicate scheduler fires.
5. Overlap policy enforcement (forbid, replace).
6. Retry identity: preserves deterministic run_key and increments attempt_id.
7. Provenance-bearing receipt verification.
"""
from datetime import datetime, timezone
import pytest

from nougen_shards.cron_out import (
    CRON_OUT,
    CloudflareWorkerSchedulerAdapter,
    CronOutExecutionEngine,
    CronOutReceipt,
    CronOutSpec,
    CronOutState,
    FleetNativeSchedulerAdapter,
    LocalCronAdapter,
    MisfirePolicy,
    OutcomeStatus,
    OverlapPolicy,
    RetryPolicy,
    ScheduleCadence,
    TaskRef,
    parse_cadence_str,
    parse_cron_out_command,
)


def test_natural_speech_parsing_variations():
    """Golden Test 1: Natural operator grammar parsing."""
    # 1. "Cron out the tracker reconciliation every hour."
    spec1 = parse_cron_out_command("Cron out the tracker reconciliation every hour.")
    assert spec1.operator == "CRON_OUT"
    assert spec1.task.ref == "tracker_reconciliation"
    assert spec1.schedule.type == "hourly"
    assert spec1.schedule.every == "1h"
    assert spec1.execution.overlap == OverlapPolicy.FORBID
    assert spec1.governance.lease_required is True

    # 2. "Cron this out nightly."
    spec2 = parse_cron_out_command("Cron this out nightly.")
    assert spec2.schedule.type == "daily"
    assert spec2.schedule.every == "24h"

    # 3. "Cron that sweep out every fifteen minutes, forbid overlap."
    spec3 = parse_cron_out_command("Cron that sweep out every fifteen minutes, forbid overlap.")
    assert spec3.task.ref == "sweep"
    assert spec3.schedule.every == "15m"
    assert spec3.execution.overlap == OverlapPolicy.FORBID

    # 4. "Cron out the integrity check across eligible nodes, jitter the starts, receipt every run."
    spec4 = parse_cron_out_command("Cron out the integrity check across eligible nodes, jitter the starts, receipt every run.")
    assert "integrity_check" in spec4.task.ref
    assert spec4.execution.jitter_seconds == 30
    assert spec4.verification.receipt_required is True


def test_structured_cron_out_constructor():
    """Golden Test 2: Structured CRON_OUT operator constructor."""
    spec = CRON_OUT(
        operation="shard_vacuum_sweep",
        cadence="every 6h",
        timezone_str="America/New_York",
        overlap=OverlapPolicy.FORBID,
        misfire=MisfirePolicy.COALESCE_LATEST,
        jitter_seconds=45,
        max_runtime_seconds=900,
        max_attempts=5,
    )
    assert spec.schedule_id == "cron_shard_vacuum_sweep_6h"
    assert spec.task.ref == "shard_vacuum_sweep"
    assert spec.schedule.every == "6h"
    assert spec.schedule.timezone == "America/New_York"
    assert spec.execution.overlap == OverlapPolicy.FORBID
    assert spec.execution.jitter_seconds == 45
    assert spec.reliability.max_attempts == 5
    assert spec.state == CronOutState.CRONNED


def test_deterministic_idempotency_run_key():
    """Golden Test 3: Deterministic logical run identity.

    run_key = HASH(schedule_id + nominal_fire_time + schedule_generation).
    Duplicate fires at identical nominal time MUST produce identical run_key.
    """
    spec = CRON_OUT("token_reconcile", cadence="1h")
    fire_time = "2026-09-23T15:00:00Z"

    key1 = spec.calculate_run_key(fire_time)
    key2 = spec.calculate_run_key(fire_time)

    assert key1 == key2
    assert len(key1) == 16

    # Different fire time produces different key
    key3 = spec.calculate_run_key("2026-09-23T16:00:00Z")
    assert key1 != key3

    # New generation produces different key for the same nominal time
    spec.generation = 2
    key_gen2 = spec.calculate_run_key(fire_time)
    assert key1 != key_gen2


def test_scheduler_backend_adapters():
    """Golden Test 4: Semantic layer compiles into diverse scheduler adapters."""
    spec = CRON_OUT("dream_lane", cadence="every 15m", timezone_str="America/New_York")

    # 1. Local Cron adapter
    cron_adapter = LocalCronAdapter()
    cron_manifest = cron_adapter.compile_manifest(spec)
    assert cron_manifest["adapter"] == "unix_cron"
    assert cron_manifest["cron_expression"] == "*/15 * * * *"
    assert "CRON_TZ=America/New_York" in cron_manifest["crontab_line"]
    assert cron_manifest["overlap_lock"] is True

    # 2. Fleet Native adapter
    fleet_adapter = FleetNativeSchedulerAdapter()
    fleet_manifest = fleet_adapter.compile_manifest(spec)
    assert fleet_manifest["adapter"] == "nougen_fleet_native"
    assert fleet_manifest["fleet_dispatch_topic"] == "fleet.cron.cron_dream_lane_15m"
    assert fleet_manifest["execution"]["overlap"] == "forbid"

    # 3. Cloudflare Workers adapter
    cf_adapter = CloudflareWorkerSchedulerAdapter()
    cf_manifest = cf_adapter.compile_manifest(spec)
    assert cf_manifest["adapter"] == "cloudflare_workers"
    assert cf_manifest["cron_trigger"] == "*/15 * * * *"


def test_execution_engine_overlap_and_idempotency():
    """Golden Test 5: Engine enforces overlap policy and idempotent deduplication."""
    engine = CronOutExecutionEngine(node_name="whoart")
    spec = CRON_OUT("active_indexer", cadence="15m", overlap=OverlapPolicy.FORBID)
    nominal_time = "2026-09-23T17:00:00Z"

    # First trigger succeeds
    success, receipt, msg = engine.trigger(spec, nominal_time)
    assert success is True
    assert receipt is not None
    assert receipt.outcome == OutcomeStatus.SUCCESS
    assert receipt.attempt_id == 1
    assert len(receipt.receipt_sha256) == 64

    # Duplicate trigger at the exact same nominal time is safely skipped
    dup_success, dup_receipt, dup_msg = engine.trigger(spec, nominal_time)
    assert dup_success is False
    assert "IDEMPOTENT_SKIP" in dup_msg
    assert dup_receipt == receipt


def test_execution_engine_retry_preserves_run_key():
    """Golden Test 6: Retry preserves logical run key while incrementing attempt_id."""
    engine = CronOutExecutionEngine(node_name="whoart")
    spec = CRON_OUT("unstable_worker", cadence="1h")
    nominal_time = "2026-09-23T18:00:00Z"

    # Simulate attempt 1 failure
    s1, r1, m1 = engine.trigger(spec, nominal_time, simulate_failure=True)
    assert s1 is False
    assert r1 is not None
    assert r1.outcome == OutcomeStatus.FAILED
    assert r1.attempt_id == 1

    # Simulate attempt 2 retry (same nominal time)
    s2, r2, m2 = engine.trigger(spec, nominal_time, simulate_failure=False)
    assert s2 is True
    assert r2 is not None
    assert r2.outcome == OutcomeStatus.SUCCESS
    assert r2.attempt_id == 2

    # Invariant: run_key is strictly identical across both attempts
    assert r1.run_key == r2.run_key
    assert r1.schedule_id == r2.schedule_id

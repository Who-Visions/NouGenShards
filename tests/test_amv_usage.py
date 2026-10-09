import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

import pytest

from nougen_shards.amv_usage import (
    AMVUsageEvent,
    append_usage_event,
    cloud_equivalent_cost,
    local_energy_cost_usd,
    read_usage_events,
    simulate_workload,
    summarize_events,
    PriceRate,
    event_from_provider_response,
)


def _event(**overrides):
    fields = dict(
        event_id="event-1",
        job_id="job-opaque-1",
        stage="scene_description",
        provider="ollama",
        pricing_basis="free_local",
        token_measurement="exact",
        usage_source="provider_reported",
        pricing_status="not_applicable",
        execution_location="local",
        cache_measurement="exact",
        status="completed",
        model="qwen3-vl:2b",
        modality="video",
        input_tokens=120,
        output_tokens=18,
        cached_tokens=0,
        reasoning_tokens=0,
        video_frames=4,
        duration_ms=850.0,
        gpu_seconds=0.7,
        peak_vram_mb=2900.0,
    )
    fields.update(overrides)
    return AMVUsageEvent(**fields)


def test_exact_local_event_serializes_without_prompt_and_is_explicitly_free():
    row = _event().to_ledger_row()
    assert row["model"] == "local/qwen3-vl:2b"
    assert row["token_measurement"] == "exact"
    assert row["input_tokens"] == 120
    assert row["provider"] == "ollama"
    assert row["pricing_basis"] == "free_local"
    assert row["actual_new_api_charges_usd"] == 0.0
    assert row["cost_usd"] == 0.0
    assert row["pricing_status"] == "not_applicable"
    assert row["usage_source"] == "provider_reported"
    assert row["execution_location"] == "local"
    assert row["trace_id"] == row["job_id"]
    assert row["model_id"] == "qwen3-vl:2b"
    assert "prompt" not in row
    assert "media_path" not in row


def test_unavailable_token_counts_are_not_fabricated():
    event = _event(
        event_id="render-1", stage="render", provider="ffmpeg",
        pricing_basis="deterministic", token_measurement="unavailable",
        cache_measurement="unavailable",
        usage_source="unavailable", pricing_status="not_applicable",
        model=None, input_tokens=None, output_tokens=None, cached_tokens=None,
        reasoning_tokens=None, cpu_seconds=9.2, output_frames=900,
    )
    row = event.to_ledger_row()
    assert row["input_tokens"] is None
    assert row["token_measurement"] == "unavailable"
    assert row["output_frames"] == 900
    assert row["actual_new_api_charges_usd"] == 0.0
    assert row["cost_usd"] == 0.0
    assert row["compute_ms"] == 850.0


def test_provider_adapters_preserve_exact_counts_and_never_keep_content():
    event = event_from_provider_response(
        response={
            "model": "local-qwen",
            "prompt_eval_count": 140,
            "eval_count": 21,
            "total_duration": 2_500_000_000,
            "response": "must not be retained",
        },
        usage_format="ollama",
        event_fields={
            "event_id": "provider-1", "job_id": "job-1", "stage": "scene_description",
            "provider": "ollama", "pricing_basis": "free_local", "status": "completed",
            "modality": "video", "execution_location": "local",
        },
    )
    row = event.to_ledger_row()
    assert row["token_measurement"] == "exact"
    assert row["input_tokens"] == 140
    assert row["output_tokens"] == 21
    assert row["duration_ms"] == 2500
    assert row["cached_tokens"] is None
    assert row["cache_measurement"] == "unavailable"
    assert "response" not in row

    openai_event = event_from_provider_response(
        response={
            "model": "vision-model",
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 22,
                "prompt_tokens_details": {"cached_tokens": 30},
                "completion_tokens_details": {"reasoning_tokens": 5},
            },
        },
        usage_format="openai-compatible",
        event_fields={
            "event_id": "provider-2", "job_id": "job-1", "stage": "amv_planning",
            "provider": "gateway", "pricing_basis": "provider_billed", "status": "completed",
            "modality": "text", "execution_location": "cloud",
        },
    )
    assert openai_event.input_tokens == 70
    assert openai_event.cached_tokens == 30
    assert openai_event.reasoning_tokens == 5


def test_provider_response_without_cache_breakdown_keeps_input_exact_but_cache_unknown():
    event = event_from_provider_response(
        response={"model": "text-model", "usage": {"prompt_tokens": 10, "completion_tokens": 3}},
        usage_format="openai-compatible",
        event_fields={
            "event_id": "provider-no-cache", "job_id": "job-1", "stage": "amv_planning",
            "provider": "gateway", "pricing_basis": "provider_billed", "status": "completed",
            "modality": "text", "execution_location": "cloud",
        },
    )
    assert event.token_measurement == "exact"
    assert event.input_tokens == 10
    assert event.cache_measurement == "unavailable"
    assert event.cached_tokens is None


def test_unknown_provider_price_stays_null_and_keeps_telemetry_provenance():
    event = _event(
        event_id="unknown-price", provider="unknown-cloud", pricing_basis="provider_billed",
        pricing_status="unknown", execution_location="cloud", cost_usd=None,
        model="vendor/private-unlisted-model", model_version="v7",
    )
    row = event.to_ledger_row()
    assert row["pricing_status"] == "unknown"
    assert row["cost_usd"] is None
    assert row["actual_new_api_charges_usd"] is None
    assert row["model_id"] == "vendor/private-unlisted-model"
    assert row["model_version"] == "v7"
    assert row["usage_source"] == "provider_reported"


def test_tracker_leaves_unknown_model_unpriced_and_frames_unavailable(tmp_path):
    ledger = tmp_path / "usage.jsonl"
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "timestamp": now, "source": "NouGenAMV", "provider": "unknown-cloud",
            "model": "vendor/private-unlisted-model", "model_id": "vendor/private-unlisted-model",
            "model_version": "v7", "pricing_basis": "provider_billed", "pricing_status": "unknown",
            "execution_location": "cloud", "usage_source": "provider_reported",
            "token_measurement": "exact", "input_tokens": 100, "output_tokens": 20,
            "cached_tokens": 0, "reasoning_tokens": 0, "trace_id": "trace-a",
            "job_id": "job-a", "event_id": "event-a", "compute_ms": 123,
        },
        {
            "timestamp": now, "source": "NouGenAMV", "provider": "ollama",
            "model": "local/qwen3-vl:2b", "model_id": "qwen3-vl:2b",
            "pricing_basis": "free_local", "pricing_status": "not_applicable",
            "execution_location": "local", "usage_source": "unavailable",
            "token_measurement": "unavailable", "input_tokens": None, "output_tokens": None,
            "cached_tokens": None, "reasoning_tokens": None, "video_frames": 300,
            "actual_new_api_charges_usd": 0.0, "cost_usd": 0.0,
            "trace_id": "trace-b", "job_id": "job-b", "event_id": "event-b",
        },
        {
            "timestamp": now, "source": "legacy-writer", "provider": "unknown-cloud",
            "model": "legacy-unlabeled-model", "input_tokens": 55, "output_tokens": 12,
            "cached_tokens": 0, "reasoning_tokens": 0,
        },
        {
            "timestamp": now, "source": "NouGenAMV", "provider": "gateway",
            "model": "gpt-5.4-mini", "pricing_basis": "provider_billed",
            "pricing_status": "known", "execution_location": "cloud",
            "usage_source": "provider_reported", "token_measurement": "exact",
            "input_tokens": 1_000_000, "output_tokens": 1_000_000,
            "cached_tokens": 0, "reasoning_tokens": 0,
        },
    ]
    ledger.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    isolated_home = tmp_path / "isolated-home"
    isolated_home.mkdir()
    env = dict(os.environ)
    env["HOME"] = str(isolated_home)
    env["FLEET_USAGE_LEDGER"] = str(ledger)
    src = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    script = Path(__file__).resolve().parents[1] / "tools" / "token_tracker.py"
    completed = subprocess.run(
        [sys.executable, str(script), "2"], check=True, capture_output=True,
        text=True, env=env, timeout=45,
    )
    assert "vendor/private-unlisted-model" in completed.stdout
    assert "Unknown-price usage" in completed.stdout
    assert "unpriced" in completed.stdout
    assert "Unavailable-usage invocations" in completed.stdout
    assert "Unknown model prices are excluded" in completed.stdout
    assert "300" in completed.stdout
    assert "legacy-unlabeled-model" in completed.stdout
    known_model_line = next(
        line for line in completed.stdout.splitlines()
        if line.strip().startswith("gpt-5.4-mini")
    )
    assert "$5.25" in known_model_line


def test_exact_token_events_require_model_and_all_usage_fields():
    with pytest.raises(ValueError, match="model identifier"):
        _event(model=None)
    with pytest.raises(ValueError, match="cached_tokens"):
        _event(cached_tokens=None)


def test_append_is_idempotent_and_report_aggregates_stage_compute(tmp_path):
    ledger = tmp_path / "usage.jsonl"
    event = _event(verification_status="passed")
    assert append_usage_event(event, ledger) is True
    assert append_usage_event(event, ledger) is False
    rows, malformed = read_usage_events(ledger)
    report = summarize_events(rows)
    assert malformed == 0
    assert report["events"] == 1
    stage = report["by_stage"]["scene_description"]
    assert stage["exact_invocations"] == 1
    assert stage["input_tokens"] == 120
    assert stage["video_frames"] == 4
    assert stage["gpu_seconds"] == pytest.approx(0.7)
    assert stage["actual_new_api_charges_usd"] == 0
    assert report["verified_completed_jobs"] == 1
    assert report["actual_cost_per_verified_job_usd"] == 0
    assert len(ledger.read_text().splitlines()) == 1


def test_nougen_amv_report_cli_reads_the_fleet_ledger(tmp_path):
    ledger = tmp_path / "usage.jsonl"
    append_usage_event(_event(verification_status="passed"), ledger)
    env = dict(os.environ)
    env["FLEET_USAGE_LEDGER"] = str(ledger)
    src = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(
        [sys.executable, "-m", "nougen_shards.cli", "amv", "report", "--json"],
        check=True, capture_output=True, text=True, env=env,
    )
    report = json.loads(completed.stdout)
    assert report["events"] == 1
    assert report["verified_completed_jobs"] == 1
    assert report["by_stage"]["scene_description"]["video_frames"] == 4


def test_simulator_cli_reports_illustrative_values_without_writing_ledger(tmp_path):
    ledger = tmp_path / "must-not-be-created.jsonl"
    env = dict(os.environ)
    env["FLEET_USAGE_LEDGER"] = str(ledger)
    src = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(
        [sys.executable, "-m", "nougen_shards.cli", "amv", "simulate", "--json"],
        check=True, capture_output=True, text=True, env=env,
    )
    result = json.loads(completed.stdout)
    assert result["actual_usage"] is False
    assert result["new_api_charges_usd"] == 0
    assert not ledger.exists()


def test_cloud_equivalent_uses_uncached_and_cached_rates_separately():
    rates = PriceRate(
        input_usd_per_million=0.5,
        output_usd_per_million=1.05,
        cached_input_usd_per_million=0.1,
        catalog_id="test-card",
        effective_date="2026-01-01",
        source="test fixture",
    )
    assert cloud_equivalent_cost(
        input_tokens=100_000, cached_tokens=50_000, output_tokens=10_000, rate=rates
    ) == pytest.approx(0.0655)


def test_simulator_example_is_labeled_and_not_actual_usage():
    result = simulate_workload(
        shots=250, input_tokens_per_shot=1800, output_tokens_per_shot=250,
        input_rate=0.5, output_rate=1.05,
    )
    assert result["input_tokens"] == 450_000
    assert result["output_tokens"] == 62_500
    assert result["cloud_equivalent_usd"] == pytest.approx(0.290625)
    assert result["new_api_charges_usd"] == 0
    assert result["actual_usage"] is False
    assert "ILLUSTRATIVE" in result["label"]


def test_energy_estimate_is_separate_from_cloud_inference():
    result = simulate_workload(
        shots=1, input_tokens_per_shot=10, output_tokens_per_shot=5,
        input_rate=1.0, output_rate=2.0, energy_kwh=0.4, electricity_rate=0.2,
    )
    assert result["local_energy_cost_usd"] == pytest.approx(0.08)
    assert result["cloud_equivalent_usd"] == pytest.approx(0.00002)
    assert local_energy_cost_usd(0.4, 0.2) == pytest.approx(0.08)


def test_hardware_allocation_requires_complete_inputs_and_is_separate():
    result = simulate_workload(
        shots=1, input_tokens_per_shot=10, output_tokens_per_shot=5,
        input_rate=1.0, output_rate=2.0,
        hardware_purchase_usd=1200, device_hours=2, expected_hardware_lifetime_hours=6000,
    )
    assert result["hardware_allocation_usd"] == pytest.approx(0.4)
    assert result["new_api_charges_usd"] == 0
    with pytest.raises(ValueError, match="requires purchase cost"):
        simulate_workload(
            shots=1, input_tokens_per_shot=10, output_tokens_per_shot=5,
            input_rate=1.0, output_rate=2.0, hardware_purchase_usd=1200,
        )


def test_reject_invalid_cost_inputs():
    with pytest.raises(ValueError, match="cached_fraction"):
        simulate_workload(
            shots=1, input_tokens_per_shot=1, output_tokens_per_shot=1,
            input_rate=1, output_rate=1, cached_fraction=1.1,
        )
    with pytest.raises(ValueError, match="non-negative integer"):
        cloud_equivalent_cost(input_tokens=-1, output_tokens=0, cached_tokens=0,
                              rate=PriceRate(1, 1, 1, "x", "2026-01-01", "fixture"))
    with pytest.raises(ValueError, match="finite"):
        simulate_workload(
            shots=1, input_tokens_per_shot=1, output_tokens_per_shot=1,
            input_rate=float("nan"), output_rate=1,
        )


def test_reader_skips_malformed_rows_and_ignores_other_sources(tmp_path):
    ledger = tmp_path / "usage.jsonl"
    ledger.write_text(
        json.dumps({"source": "another-writer"}) + "\n{broken\n"
        + json.dumps(_event().to_ledger_row()) + "\n",
        encoding="utf-8",
    )
    rows, malformed = read_usage_events(ledger)
    assert len(rows) == 1
    assert malformed == 1

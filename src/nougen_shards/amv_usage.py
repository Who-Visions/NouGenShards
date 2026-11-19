"""Append-only NouGenAMV workload accounting and illustrative cost simulation.

Production events share the fleet usage JSONL ledger consumed by
``tools/token_tracker.py``. The event schema keeps token measurement, local
compute, hypothetical cloud pricing, and actual API charges distinct.
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


TokenMeasurement = Literal["exact", "estimated", "unavailable"]
PricingBasis = Literal[
    "free_local", "provider_billed", "subscription_included", "deterministic", "unknown"
]
UsageSource = Literal["provider_reported", "tokenizer_measured", "estimated", "unavailable"]
PricingStatus = Literal["known", "unknown", "not_applicable"]
ExecutionLocation = Literal["local", "cloud", "hybrid"]
_STAGES = {
    "ingest", "video_indexing", "audio_analysis", "scene_description",
    "amv_planning", "timeline_compilation", "render", "export", "fleet_relay",
}
_NONNEGATIVE_INT_FIELDS = {
    "attempt", "input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens",
    "audio_samples", "video_frames", "output_frames", "asset_count", "network_bytes",
}
_NONNEGATIVE_FLOAT_FIELDS = {
    "analyzed_seconds", "duration_ms", "cpu_seconds", "gpu_seconds", "cpu_utilization_pct",
    "gpu_utilization_pct", "peak_vram_mb", "peak_ram_mb", "energy_kwh",
    "actual_new_api_charges_usd", "network_latency_ms",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LOCAL_LOCK = threading.RLock()


def default_ledger_path() -> Path:
    """Use the existing fleet token ledger path, honoring its established override."""
    configured = os.environ.get("FLEET_USAGE_LEDGER")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[2] / "tools" / "vault" / "fleet_usage.jsonl"


def _validate_number(name: str, value: int | float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{name} must be a non-negative number or None")
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        raise ValueError(f"{name} must be finite")


@dataclass(frozen=True)
class AMVUsageEvent:
    """One completed or failed stage attempt; no prompt/media content is stored."""

    event_id: str
    job_id: str
    stage: str
    provider: str
    pricing_basis: PricingBasis
    token_measurement: TokenMeasurement
    status: Literal["completed", "failed", "cached"]
    execution_location: ExecutionLocation
    usage_source: UsageSource = "unavailable"
    pricing_status: PricingStatus = "unknown"
    trace_id: str | None = None
    model_id: str | None = None
    cost_usd: float | None = None
    cache_measurement: Literal["exact", "estimated", "unavailable"] = "unavailable"
    source: str = "NouGenAMV"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    node: str | None = None
    lane: str | None = None
    model: str | None = None
    model_version: str | None = None
    modality: Literal["text", "image", "audio", "video", "multimodal", "none"] = "none"
    provider_usage_units: dict[str, int] = field(default_factory=dict)
    attempt: int = 1
    input_tokens: int | None = None  # uncached if cache count is known; full prompt otherwise
    output_tokens: int | None = None
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None  # annotation; do not add twice to output cost
    cache_hit: bool = False
    duration_ms: float | None = None
    audio_samples: int | None = None
    video_frames: int | None = None
    analyzed_seconds: float | None = None
    output_frames: int | None = None
    asset_count: int | None = None
    cpu_seconds: float | None = None
    gpu_seconds: float | None = None
    cpu_utilization_pct: float | None = None
    gpu_utilization_pct: float | None = None
    peak_vram_mb: float | None = None
    peak_ram_mb: float | None = None
    energy_kwh: float | None = None
    energy_measurement: Literal["measured", "estimated", "unavailable"] = "unavailable"
    energy_source: str | None = None
    network_bytes: int | None = None
    network_latency_ms: float | None = None
    actual_new_api_charges_usd: float | None = None
    price_catalog_id: str | None = None
    price_effective_date: str | None = None
    config_sha256: str | None = None
    source_fingerprint_sha256: str | None = None
    manifest_sha256: str | None = None
    output_sha256: str | None = None
    verification_status: Literal["pending", "passed", "failed"] = "pending"

    def __post_init__(self) -> None:
        for name in ("event_id", "job_id", "provider", "source"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")
        if self.stage not in _STAGES:
            raise ValueError(f"unsupported stage: {self.stage}")
        if self.token_measurement not in {"exact", "estimated", "unavailable"}:
            raise ValueError("unsupported token_measurement")
        if self.usage_source not in {"provider_reported", "tokenizer_measured", "estimated", "unavailable"}:
            raise ValueError("unsupported usage_source")
        if self.pricing_status not in {"known", "unknown", "not_applicable"}:
            raise ValueError("unsupported pricing_status")
        if self.execution_location not in {"local", "cloud", "hybrid"}:
            raise ValueError("unsupported execution_location")
        if self.pricing_basis not in {
            "free_local", "provider_billed", "subscription_included", "deterministic", "unknown"
        }:
            raise ValueError("unsupported pricing_basis")
        if self.status not in {"completed", "failed", "cached"}:
            raise ValueError("unsupported status")
        try:
            parsed_timestamp = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            raise ValueError("timestamp must be an ISO-8601 datetime") from None
        if parsed_timestamp.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        if self.modality not in {"text", "image", "audio", "video", "multimodal", "none"}:
            raise ValueError("unsupported modality")
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 1:
            raise ValueError("attempt must be at least 1")
        if self.verification_status not in {"pending", "passed", "failed"}:
            raise ValueError("unsupported verification_status")
        for name in _NONNEGATIVE_INT_FIELDS:
            _validate_number(name, getattr(self, name))
            value = getattr(self, name)
            if value is not None and not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
        for name in _NONNEGATIVE_FLOAT_FIELDS:
            _validate_number(name, getattr(self, name))
        for name in ("cpu_utilization_pct", "gpu_utilization_pct"):
            value = getattr(self, name)
            if value is not None and value > 100:
                raise ValueError(f"{name} must be between 0 and 100")
        for name in ("config_sha256", "source_fingerprint_sha256", "manifest_sha256", "output_sha256"):
            value = getattr(self, name)
            if value is not None and not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        for name, value in self.provider_usage_units.items():
            if not name.strip() or isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("provider_usage_units must map names to non-negative integer counts")
        token_values = (self.input_tokens, self.output_tokens)
        if self.token_measurement in {"exact", "estimated"} and any(value is None for value in token_values):
            raise ValueError("measured token events require input and output token counts")
        valid_usage_sources = {
            "exact": {"provider_reported", "tokenizer_measured"},
            "estimated": {"estimated"},
            "unavailable": {"unavailable"},
        }
        if self.usage_source not in valid_usage_sources[self.token_measurement]:
            raise ValueError("usage_source must match token_measurement provenance")
        if self.token_measurement != "unavailable" and (not self.model or self.modality == "none"):
            raise ValueError("measured token events require a model identifier and modality")
        if self.token_measurement == "unavailable" and any(
            value is not None for value in (*token_values, self.cached_tokens)
        ):
            raise ValueError("unavailable token events cannot contain token counts")
        if self.cache_measurement == "unavailable" and self.cached_tokens is not None:
            raise ValueError("unavailable cache measurement cannot contain cached token counts")
        if self.cache_measurement != "unavailable" and self.cached_tokens is None:
            raise ValueError("measured cache usage requires cached_tokens")
        if self.pricing_basis == "free_local" and self.actual_new_api_charges_usd not in (None, 0, 0.0):
            raise ValueError("free_local events cannot report new API charges")
        if self.model_id and self.model and self.model_id != self.model:
            raise ValueError("model_id and model must identify the same model")
        _validate_number("cost_usd", self.cost_usd)
        if self.pricing_status == "unknown" and self.cost_usd is not None:
            raise ValueError("unknown pricing cannot carry a cost_usd value")
        if self.pricing_status == "known" and self.cost_usd is None:
            raise ValueError("known pricing requires cost_usd")
        if self.pricing_status == "not_applicable" and self.cost_usd not in (None, 0, 0.0):
            raise ValueError("not_applicable pricing cannot carry a nonzero cost_usd")
        if self.energy_measurement == "unavailable" and self.energy_kwh is not None:
            raise ValueError("unavailable energy measurement cannot contain energy_kwh")
        if self.energy_measurement != "unavailable" and self.energy_kwh is None:
            raise ValueError("measured or estimated energy requires energy_kwh")
        if self.energy_measurement == "measured" and not self.energy_source:
            raise ValueError("measured energy requires its meter/source identifier")

    def to_ledger_row(self) -> dict:
        """Serialize as a fleet token row plus namespaced workload metadata."""
        row = asdict(self)
        if row["pricing_status"] == "unknown" and self.pricing_basis in {
            "free_local", "subscription_included", "deterministic"
        }:
            row["pricing_status"] = "not_applicable"
        row["model_id"] = self.model_id or self.model
        row["trace_id"] = self.trace_id or self.job_id
        row["compute_ms"] = self.duration_ms
        row["cost_usd"] = self.cost_usd
        # Unknown local model IDs must never hit token_tracker's paid fallback.
        if self.pricing_basis == "free_local" and self.model and not self.model.startswith("local/"):
            row["model"] = f"local/{self.model}"
        row["lane"] = self.lane or "nougenamv"
        if row["actual_new_api_charges_usd"] is None and self.pricing_basis in {
            "free_local", "subscription_included", "deterministic"
        }:
            row["actual_new_api_charges_usd"] = 0.0
        if row["pricing_status"] == "not_applicable" and row["cost_usd"] is None:
            row["cost_usd"] = row["actual_new_api_charges_usd"]
        return row


def append_usage_event(event: AMVUsageEvent, path: str | os.PathLike | None = None) -> bool:
    """Append one JSONL event under an OS lock; return False for duplicate event IDs."""
    ledger = Path(path) if path is not None else default_ledger_path()
    ledger.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(event.to_ledger_row(), sort_keys=True, separators=(",", ":")) + "\n"
    encoded = payload.encode("utf-8")
    with _LOCAL_LOCK:
        fd = os.open(ledger, os.O_CREAT | os.O_RDWR | os.O_APPEND, 0o600)
        try:
            _lock_fd(fd)
            with os.fdopen(os.dup(fd), "r", encoding="utf-8") as reader:
                for line in reader:
                    try:
                        if json.loads(line).get("event_id") == event.event_id:
                            return False
                    except json.JSONDecodeError:
                        continue
            written = os.write(fd, encoded)
            if written != len(encoded):
                raise OSError("short write while appending AMV usage event")
            os.fsync(fd)
            return True
        finally:
            _unlock_fd(fd)
            os.close(fd)


def event_from_provider_response(
    *,
    response: dict,
    usage_format: Literal["ollama", "openai-compatible"],
    event_fields: dict,
) -> AMVUsageEvent:
    """Build an event from provider usage metadata without retaining response text.

    Ollama's ``prompt_eval_count``/``eval_count`` and OpenAI-compatible
    ``usage.prompt_tokens``/``completion_tokens`` are accepted. Missing usage
    stays unavailable; frame counts are never used to synthesize token counts.
    """
    if not isinstance(response, dict):
        raise ValueError("provider response must be a mapping")

    def is_count(value):
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    if usage_format == "ollama":
        raw_input = response.get("prompt_eval_count")
        raw_output = response.get("eval_count")
        cached = None
        reasoning = 0
        input_key, output_key = "prompt_eval_count", "eval_count"
        duration_ns = response.get("total_duration")
        cache_status = "unavailable"
    elif usage_format == "openai-compatible":
        usage = response.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}
        raw_input = usage.get("prompt_tokens")
        raw_output = usage.get("completion_tokens")
        details = usage.get("prompt_tokens_details") or {}
        completion_details = usage.get("completion_tokens_details") or {}
        if not isinstance(details, dict):
            details = {}
        if not isinstance(completion_details, dict):
            completion_details = {}
        cached = details.get("cached_tokens")
        cache_status = "exact" if is_count(cached) else "unavailable"
        reasoning = completion_details.get("reasoning_tokens", 0) or 0
        input_key, output_key = "prompt_tokens", "completion_tokens"
        duration_ns = None
    else:
        raise ValueError("unsupported usage_format")

    usage_is_exact = is_count(raw_input) and is_count(raw_output) and is_count(reasoning)
    fields = dict(event_fields)
    if not fields.get("model"):
        fields["model"] = response.get("model")
    fields.setdefault("model_id", fields.get("model"))
    fields.setdefault("trace_id", fields.get("job_id"))
    fields.setdefault("execution_location", "cloud" if fields.get("pricing_basis") == "provider_billed" else "local")
    fields.setdefault(
        "pricing_status",
        "not_applicable" if fields.get("pricing_basis") in {"free_local", "deterministic", "subscription_included"} else "unknown",
    )
    if usage_is_exact:
        if cache_status == "exact" and cached > raw_input:
            raise ValueError("cached prompt tokens exceed total prompt tokens")
        if usage_format == "openai-compatible" and reasoning > raw_output:
            raise ValueError("reasoning tokens exceed completion tokens")
        uncached = raw_input - cached if cache_status == "exact" else raw_input
        non_reasoning_output = raw_output - reasoning if usage_format == "openai-compatible" else raw_output
        fields.update(
            token_measurement="exact",
            usage_source="provider_reported",
            input_tokens=uncached,
            output_tokens=non_reasoning_output,
            cached_tokens=cached,
            cache_measurement=cache_status,
            reasoning_tokens=reasoning,
            provider_usage_units={input_key: raw_input, output_key: raw_output},
        )
    else:
        fields.update(
            token_measurement="unavailable",
            usage_source="unavailable",
            input_tokens=None,
            output_tokens=None,
            cached_tokens=None,
            cache_measurement="unavailable",
            reasoning_tokens=None,
            provider_usage_units={},
        )
    if fields.get("duration_ms") is None and is_count(duration_ns):
        fields["duration_ms"] = duration_ns / 1_000_000
    return AMVUsageEvent(**fields)


def _lock_fd(fd: int) -> None:
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX)


def _unlock_fd(fd: int) -> None:
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)


def read_usage_events(path: str | os.PathLike | None = None) -> tuple[list[dict], int]:
    """Read valid NouGenAMV ledger rows and return (rows, malformed_line_count)."""
    ledger = Path(path) if path is not None else default_ledger_path()
    if not ledger.exists():
        return [], 0
    rows: list[dict] = []
    malformed = 0
    with ledger.open("r", encoding="utf-8", errors="replace") as reader:
        for line in reader:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(row, dict) and row.get("source") == "NouGenAMV":
                rows.append(row)
    return rows, malformed


@dataclass(frozen=True)
class PriceRate:
    """Dated hypothetical cloud-equivalent rates, in USD per million tokens."""

    input_usd_per_million: float
    output_usd_per_million: float
    cached_input_usd_per_million: float
    catalog_id: str
    effective_date: str
    source: str
    modality: str = "text"

    def __post_init__(self) -> None:
        for name in ("input_usd_per_million", "output_usd_per_million", "cached_input_usd_per_million"):
            value = getattr(self, name)
            _validate_number(name, value)
        if not self.catalog_id.strip() or not self.source.strip():
            raise ValueError("catalog_id and source are required")


def cloud_equivalent_cost(
    *, input_tokens: int, output_tokens: int, cached_tokens: int, rate: PriceRate
) -> float:
    """Compute hypothetical value; input_tokens are uncached (cache reads separate)."""
    for name, value in (("input_tokens", input_tokens), ("output_tokens", output_tokens), ("cached_tokens", cached_tokens)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    return (
        input_tokens * rate.input_usd_per_million
        + cached_tokens * rate.cached_input_usd_per_million
        + output_tokens * rate.output_usd_per_million
    ) / 1_000_000


def local_energy_cost_usd(energy_kwh: float, electricity_usd_per_kwh: float) -> float:
    _validate_number("energy_kwh", energy_kwh)
    _validate_number("electricity_usd_per_kwh", electricity_usd_per_kwh)
    return energy_kwh * electricity_usd_per_kwh


def simulate_workload(
    *, shots: int, input_tokens_per_shot: int, output_tokens_per_shot: int,
    input_rate: float, output_rate: float, cached_fraction: float = 0.0,
    cache_rate: float | None = None, energy_kwh: float | None = None,
    electricity_rate: float | None = None, hardware_purchase_usd: float | None = None,
    device_hours: float | None = None, expected_hardware_lifetime_hours: float | None = None,
) -> dict:
    """Calculate a labeled scenario without writing it to any production ledger."""
    for name, value in (("shots", shots), ("input_tokens_per_shot", input_tokens_per_shot),
                        ("output_tokens_per_shot", output_tokens_per_shot)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    _validate_number("cached_fraction", cached_fraction)
    for name, value in (("input_rate", input_rate), ("output_rate", output_rate),
                        ("cache_rate", cache_rate), ("energy_kwh", energy_kwh),
                        ("electricity_rate", electricity_rate)):
        _validate_number(name, value)
    if not 0 <= cached_fraction <= 1:
        raise ValueError("cached_fraction must be between 0 and 1")
    hardware_inputs = (hardware_purchase_usd, device_hours, expected_hardware_lifetime_hours)
    if any(value is not None for value in hardware_inputs):
        if any(value is None for value in hardware_inputs):
            raise ValueError("hardware allocation requires purchase cost, device hours, and expected lifetime hours")
        for name, value in zip(("hardware_purchase_usd", "device_hours", "expected_hardware_lifetime_hours"), hardware_inputs):
            _validate_number(name, value)
        if expected_hardware_lifetime_hours <= 0:
            raise ValueError("expected_hardware_lifetime_hours must be positive")
    total_input = shots * input_tokens_per_shot
    cached = int(total_input * cached_fraction)
    uncached = total_input - cached
    rate = PriceRate(
        input_usd_per_million=input_rate,
        output_usd_per_million=output_rate,
        cached_input_usd_per_million=cache_rate if cache_rate is not None else input_rate,
        catalog_id="illustrative-user-input",
        effective_date="not-a-provider-price",
        source="illustrative simulator inputs; not verified provider pricing",
    )
    result = {
        "label": "ILLUSTRATIVE SIMULATION — NOT OBSERVED USAGE OR A PROVIDER QUOTE",
        "shots": shots,
        "input_tokens": uncached,
        "cached_input_tokens": cached,
        "output_tokens": shots * output_tokens_per_shot,
        "cloud_equivalent_usd": cloud_equivalent_cost(
            input_tokens=uncached, cached_tokens=cached,
            output_tokens=shots * output_tokens_per_shot, rate=rate,
        ),
        "input_rate_usd_per_million": input_rate,
        "output_rate_usd_per_million": output_rate,
        "cache_rate_usd_per_million": rate.cached_input_usd_per_million,
        "new_api_charges_usd": 0.0,
        "local_energy_kwh": energy_kwh,
        "local_energy_cost_usd": (
            local_energy_cost_usd(energy_kwh, electricity_rate)
            if energy_kwh is not None and electricity_rate is not None else None
        ),
        "hardware_allocation_usd": (
            hardware_purchase_usd / expected_hardware_lifetime_hours * device_hours
            if hardware_purchase_usd is not None else None
        ),
        "actual_usage": False,
    }
    return result


def summarize_events(events: list[dict]) -> dict:
    """Aggregate observed AMV rows by stage without pricing unknown rates."""
    stages: dict[str, dict] = {}
    for event in events:
        if event.get("source") != "NouGenAMV":
            continue
        stage = str(event.get("stage") or "unknown")
        bucket = stages.setdefault(stage, {
            "attempts": 0, "completed": 0, "failed": 0, "cache_hits": 0,
            "exact_invocations": 0, "estimated_invocations": 0,
            "unavailable_invocations": 0, "input_tokens": 0, "output_tokens": 0,
            "cache_unavailable_invocations": 0,
            "exact_input_tokens": 0, "exact_output_tokens": 0, "exact_cached_tokens": 0,
            "estimated_input_tokens": 0, "estimated_output_tokens": 0,
            "estimated_cached_tokens": 0,
            "cached_tokens": 0, "reasoning_tokens": 0, "video_frames": 0,
            "audio_samples": 0, "cpu_seconds": 0.0, "gpu_seconds": 0.0,
            "duration_ms": 0.0, "energy_kwh": 0.0, "energy_known_events": 0,
            "actual_new_api_charges_usd": 0.0, "asset_count": 0,
            "retries": 0, "max_peak_vram_mb": None, "max_peak_ram_mb": None,
            "cpu_utilization_sum": 0.0, "cpu_utilization_events": 0,
            "gpu_utilization_sum": 0.0, "gpu_utilization_events": 0,
            "network_bytes": 0, "network_latency_ms": 0.0,
            "verified_job_ids": set(), "job_ids": set(),
        })
        bucket["attempts"] += 1
        bucket["completed"] += event.get("status") in {"completed", "cached"}
        bucket["failed"] += event.get("status") == "failed"
        bucket["cache_hits"] += bool(event.get("cache_hit"))
        bucket["retries"] += int((event.get("attempt") or 1) > 1)
        if event.get("job_id"):
            bucket["job_ids"].add(event["job_id"])
            if event.get("verification_status") == "passed":
                bucket["verified_job_ids"].add(event["job_id"])
        measurement = event.get("token_measurement", "unavailable")
        if measurement not in {"exact", "estimated", "unavailable"}:
            measurement = "unavailable"
        bucket[f"{measurement}_invocations"] += 1
        if event.get("cache_measurement", "unavailable") == "unavailable":
            bucket["cache_unavailable_invocations"] += 1
        if measurement in {"exact", "estimated"}:
            for name in ("input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens"):
                count = int(event.get(name) or 0)
                bucket[name] += count
                if name != "reasoning_tokens":
                    bucket[f"{measurement}_{name}"] += count
        for name in ("video_frames", "audio_samples", "asset_count", "network_bytes"):
            bucket[name] += int(event.get(name) or 0)
        for name in ("cpu_seconds", "gpu_seconds", "duration_ms", "network_latency_ms"):
            bucket[name] += float(event.get(name) or 0)
        for source_name, max_name in (("peak_vram_mb", "max_peak_vram_mb"), ("peak_ram_mb", "max_peak_ram_mb")):
            value = event.get(source_name)
            if value is not None:
                bucket[max_name] = max(bucket[max_name] or 0, float(value))
        for source_name, sum_name, count_name in (
            ("cpu_utilization_pct", "cpu_utilization_sum", "cpu_utilization_events"),
            ("gpu_utilization_pct", "gpu_utilization_sum", "gpu_utilization_events"),
        ):
            value = event.get(source_name)
            if value is not None:
                bucket[sum_name] += float(value)
                bucket[count_name] += 1
        if event.get("energy_kwh") is not None:
            bucket["energy_kwh"] += float(event["energy_kwh"])
            bucket["energy_known_events"] += 1
        if event.get("actual_new_api_charges_usd") is not None:
            bucket["actual_new_api_charges_usd"] += float(event["actual_new_api_charges_usd"])
    for bucket in stages.values():
        bucket["jobs_seen"] = len(bucket.pop("job_ids"))
        bucket["verified_jobs"] = len(bucket.pop("verified_job_ids"))
        bucket["avg_cpu_utilization_pct"] = (
            bucket["cpu_utilization_sum"] / bucket["cpu_utilization_events"]
            if bucket["cpu_utilization_events"] else None
        )
        bucket["avg_gpu_utilization_pct"] = (
            bucket["gpu_utilization_sum"] / bucket["gpu_utilization_events"]
            if bucket["gpu_utilization_events"] else None
        )
    job_stages: dict[str, list[dict]] = {}
    for event in events:
        if event.get("source") == "NouGenAMV" and event.get("job_id"):
            job_stages.setdefault(event["job_id"], []).append(event)

    verified_job_ids = set()
    for job_id, j_events in job_stages.items():
        has_passed_terminal = any(
            e.get("stage") in {"export", "render"} and e.get("verification_status") == "passed"
            for e in j_events
        )
        has_failed = any(
            e.get("status") == "failed" or e.get("verification_status") == "failed"
            for e in j_events
        )
        if has_passed_terminal and not has_failed:
            verified_job_ids.add(job_id)

    has_missing_billed_charge = any(
        e.get("pricing_basis") == "provider_billed" and e.get("actual_new_api_charges_usd") is None
        for e in events if e.get("source") == "NouGenAMV"
    )
    if has_missing_billed_charge:
        total_actual_charges = None
    else:
        total_actual_charges = sum(
            float(event.get("actual_new_api_charges_usd") or 0.0) for event in events
            if event.get("source") == "NouGenAMV"
        )
    verified_jobs = len(verified_job_ids)
    return {
        "events": sum(v["attempts"] for v in stages.values()),
        "verified_completed_jobs": verified_jobs,
        "actual_new_api_charges_usd": total_actual_charges,
        "actual_cost_per_verified_job_usd": (
            (total_actual_charges / verified_jobs)
            if (total_actual_charges is not None and verified_jobs)
            else None
        ),
        "by_stage": stages,
    }

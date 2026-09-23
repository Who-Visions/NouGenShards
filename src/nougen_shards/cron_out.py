"""HARDCade CRON OUT — Backend-Agnostic Temporal Deployment Operator.

Canonical Definition:
    CRON OUT = take a proven operation and roll it out across time as a persistent,
    governed, recurring autonomous execution.

    ROLL OUT changes WHERE an operation lives.
    CRON OUT changes WHEN an operation lives.

Short human law:
    Make time responsible for calling it again.

Authority:
    Dave authorial/operator lock, 2026-09-23.
    Leg: 20260923T165947Z__chatgpt-app__g-whoentertains
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore


# ============================================================================
# 1. ENUMS & STATE MACHINE
# ============================================================================

class CronOutState(str, Enum):
    """Lifecycle states for a CRON OUT persistent autonomous schedule."""
    MANUAL = "MANUAL"
    PROVEN = "PROVEN"
    CRONNED = "CRONNED"
    ARMED = "ARMED"
    DUE = "DUE"
    LEASED = "LEASED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    RECEIPTED = "RECEIPTED"
    SLEEPING = "SLEEPING"
    # Failure / containment branches
    RETRYING = "RETRYING"
    THROTTLED = "THROTTLED"
    QUARANTINED = "QUARANTINED"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"


class OverlapPolicy(str, Enum):
    FORBID = "forbid"
    REPLACE = "replace"
    ALLOW = "allow"


class MisfirePolicy(str, Enum):
    COALESCE_LATEST = "coalesce_latest"
    SKIP = "skip"
    EARLIEST = "earliest"
    ALL = "all"


class RetryPolicy(str, Enum):
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR = "linear"
    IMMEDIATE = "immediate"
    NONE = "none"


class OutcomeStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    THROTTLED = "THROTTLED"
    KILLED = "KILLED"
    TIMED_OUT = "TIMED_OUT"


# ============================================================================
# 2. CANONICAL DATA STRUCTURES
# ============================================================================

@dataclass(frozen=True)
class TaskRef:
    ref: str
    revision: str = "current_verified"
    command: Optional[str] = None
    args: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScheduleCadence:
    type: str  # "interval", "cron", "daily", "hourly"
    every: str  # "15m", "1h", "24h", "*/15 * * * *"
    timezone: str = "America/New_York"
    precision: str = "windowed"


@dataclass(frozen=True)
class ExecutionPolicy:
    overlap: OverlapPolicy = OverlapPolicy.FORBID
    misfire: MisfirePolicy = MisfirePolicy.COALESCE_LATEST
    jitter_seconds: int = 30
    max_runtime_seconds: int = 600


@dataclass(frozen=True)
class ReliabilityPolicy:
    max_attempts: int = 3
    retry: RetryPolicy = RetryPolicy.EXPONENTIAL_BACKOFF
    dead_letter: bool = True
    base_backoff_seconds: int = 15


@dataclass(frozen=True)
class GovernancePolicy:
    lease_required: bool = True
    budget_required: bool = True
    kill_switch: bool = True
    max_tokens_per_run: int = 50000


@dataclass(frozen=True)
class VerificationPolicy:
    receipt_required: bool = True
    record_nominal_fire_time: bool = True
    record_actual_start: bool = True
    record_actual_finish: bool = True
    record_executor: bool = True
    record_outcome: bool = True


@dataclass
class CronOutSpec:
    """Canonical specification of a CRON OUT persistent autonomous schedule."""
    operator: str = "CRON_OUT"
    version: int = 1
    schedule_id: str = ""
    task: TaskRef = field(default_factory=lambda: TaskRef(ref="default"))
    schedule: ScheduleCadence = field(default_factory=lambda: ScheduleCadence(type="interval", every="1h"))
    execution: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    reliability: ReliabilityPolicy = field(default_factory=ReliabilityPolicy)
    governance: GovernancePolicy = field(default_factory=GovernancePolicy)
    verification: VerificationPolicy = field(default_factory=VerificationPolicy)
    generation: int = 1
    state: CronOutState = CronOutState.CRONNED
    created_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        d["execution"]["overlap"] = self.execution.overlap.value
        d["execution"]["misfire"] = self.execution.misfire.value
        d["reliability"]["retry"] = self.reliability.retry.value
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def calculate_run_key(self, nominal_fire_time_utc: str) -> str:
        """Deterministic run key = HASH(schedule_id + nominal_fire_time + schedule_generation).

        A retry keeps the exact same run key and increments attempt_id.
        """
        payload = f"{self.schedule_id}:{nominal_fire_time_utc}:{self.generation}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass
class CronOutReceipt:
    """Provenance-bearing receipt generated at the conclusion of every logical run."""
    run_key: str
    schedule_id: str
    nominal_fire_time: str
    actual_start: str
    actual_finish: str
    attempt_id: int
    executor_node: str
    outcome: OutcomeStatus
    error_message: Optional[str] = None
    receipt_sha256: str = ""

    def __post_init__(self):
        if not self.receipt_sha256:
            content = f"{self.run_key}:{self.schedule_id}:{self.nominal_fire_time}:{self.actual_start}:{self.actual_finish}:{self.attempt_id}:{self.executor_node}:{self.outcome.value}:{self.error_message}"
            self.receipt_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()


# ============================================================================
# 3. PARSER / GRAMMAR COMPILER
# ============================================================================

def parse_cadence_str(text: str) -> Tuple[str, str]:
    """Parse human cadence string into (schedule_type, every_value)."""
    t = text.lower().strip()
    if t in ("nightly", "daily", "every day", "1d", "24h"):
        return ("daily", "24h")
    if t in ("hourly", "every hour", "1h"):
        return ("hourly", "1h")
    
    # "every 2 hours", "every 6h"
    m_hr = re.search(r"every\s+(\d+)\s*(h|hr|hours)\b", t)
    if m_hr:
        return ("interval", f"{m_hr.group(1)}h")

    # "every 15 minutes", "every 15m", "every fifteen minutes"
    m_min = re.search(r"every\s+(\d+|fifteen|thirty|five|ten)\s*(m|min|minutes)?\b", t)
    if m_min:
        val = m_min.group(1)
        word_map = {"five": "5m", "ten": "10m", "fifteen": "15m", "thirty": "30m"}
        if val in word_map:
            return ("interval", word_map[val])
        return ("interval", f"{val}m")

    # cron expression format: 5 tokens
    parts = t.split()
    if len(parts) == 5:
        return ("cron", t)

    return ("interval", text)


def parse_cron_out_command(prompt: str) -> CronOutSpec:
    """Parse natural speech or structured command into a canonical CronOutSpec.

    Examples:
        - "Cron out the tracker reconciliation every hour."
        - "Cron this out nightly."
        - "Cron out Dream Lane at 3 AM."
        - "Cron that sweep out every fifteen minutes, forbid overlap."
        - "Cron out the integrity check across eligible nodes, jitter the starts, receipt every run."
        - "CRON OUT shard_sync EVERY 15m TZ America/New_York OVERLAP forbid"
    """
    clean = prompt.strip()
    # Normalize operator prefix
    clean_lower = clean.lower()

    # Extract task/operation name
    task_name = "operation"
    m_task = re.search(r"(?:cron\s+out|cron\s+that|cron\s+this\s+out|cron)\s+(?:the\s+)?([a-zA-Z0-9_\-]+(?:\s+[a-zA-Z0-9_\-]+)?)", clean, re.IGNORECASE)
    if m_task:
        cand = m_task.group(1).strip()
        # Clean out grammar tokens if caught
        cand_clean = re.sub(r"\b(every|at|nightly|hourly|across|forbid|jitter|out)\b.*", "", cand, flags=re.IGNORECASE).strip()
        if cand_clean and cand_clean not in ("this", "that"):
            task_name = cand_clean.replace(" ", "_")

    # Extract cadence
    cadence_type, every_val = "interval", "1h"
    m_every = re.search(r"\bevery\s+([a-zA-Z0-9_\-]+(?:\s+[a-zA-Z0-9_\-]+)?)", clean, re.IGNORECASE)
    if m_every:
        cadence_type, every_val = parse_cadence_str(m_every.group(0))
    elif "nightly" in clean_lower:
        cadence_type, every_val = ("daily", "24h")
    elif "hourly" in clean_lower:
        cadence_type, every_val = ("hourly", "1h")
    elif "at 3 am" in clean_lower:
        cadence_type, every_val = ("cron", "0 3 * * *")

    # Extract overlap policy
    overlap = OverlapPolicy.FORBID
    if "allow overlap" in clean_lower or "overlap allow" in clean_lower:
        overlap = OverlapPolicy.ALLOW
    elif "replace overlap" in clean_lower or "overlap replace" in clean_lower:
        overlap = OverlapPolicy.REPLACE

    # Extract jitter
    jitter = 30 if ("jitter" in clean_lower or "jitter the starts" in clean_lower) else 0

    # Extract timezone
    tz = "America/New_York"
    m_tz = re.search(r"\btz\s+([a-zA-Z0-9_\-/]+)", clean, re.IGNORECASE)
    if m_tz:
        tz = m_tz.group(1)

    schedule_id = f"cron_{task_name}_{every_val.replace(' ', '_').replace('*', 'X')}".lower()

    return CronOutSpec(
        schedule_id=schedule_id,
        task=TaskRef(ref=task_name),
        schedule=ScheduleCadence(type=cadence_type, every=every_val, timezone=tz),
        execution=ExecutionPolicy(overlap=overlap, jitter_seconds=jitter),
        reliability=ReliabilityPolicy(max_attempts=3, retry=RetryPolicy.EXPONENTIAL_BACKOFF),
        governance=GovernancePolicy(lease_required=True, budget_required=True, kill_switch=True),
        verification=VerificationPolicy(receipt_required=True),
        state=CronOutState.CRONNED,
    )


def CRON_OUT(
    operation: Union[str, TaskRef],
    cadence: Union[str, ScheduleCadence] = "1h",
    timezone_str: str = "America/New_York",
    overlap: OverlapPolicy = OverlapPolicy.FORBID,
    misfire: MisfirePolicy = MisfirePolicy.COALESCE_LATEST,
    jitter_seconds: int = 30,
    max_runtime_seconds: int = 600,
    max_attempts: int = 3,
    lease_required: bool = True,
    kill_switch: bool = True,
) -> CronOutSpec:
    """Abstract operator constructor: CRON_OUT(...) -> CronOutSpec."""
    if isinstance(operation, str):
        t_ref = TaskRef(ref=operation)
    else:
        t_ref = operation

    if isinstance(cadence, str):
        c_type, c_every = parse_cadence_str(cadence)
        sc = ScheduleCadence(type=c_type, every=c_every, timezone=timezone_str)
    else:
        sc = cadence

    schedule_id = f"cron_{t_ref.ref}_{sc.every.replace(' ', '_').replace('*', 'X')}".lower()

    return CronOutSpec(
        schedule_id=schedule_id,
        task=t_ref,
        schedule=sc,
        execution=ExecutionPolicy(
            overlap=overlap,
            misfire=misfire,
            jitter_seconds=jitter_seconds,
            max_runtime_seconds=max_runtime_seconds,
        ),
        reliability=ReliabilityPolicy(max_attempts=max_attempts),
        governance=GovernancePolicy(lease_required=lease_required, kill_switch=kill_switch),
        state=CronOutState.CRONNED,
    )


# ============================================================================
# 4. BACKEND ADAPTERS
# ============================================================================

class SchedulerAdapter(ABC):
    """Abstract scheduler adapter. Semantic layer owns intent; adapter owns syntax."""

    @abstractmethod
    def compile_manifest(self, spec: CronOutSpec) -> Dict[str, Any]:
        """Compile a CronOutSpec into the target scheduler's native representation."""
        pass


class LocalCronAdapter(SchedulerAdapter):
    """Adapter for Unix crontab / system scheduler."""

    def compile_manifest(self, spec: CronOutSpec) -> Dict[str, Any]:
        cron_expr = spec.schedule.every
        if spec.schedule.type == "hourly":
            cron_expr = "0 * * * *"
        elif spec.schedule.type == "daily":
            cron_expr = "0 0 * * *"
        elif spec.schedule.type == "interval" and spec.schedule.every.endswith("m"):
            m = spec.schedule.every[:-1]
            cron_expr = f"*/{m} * * * *"
        elif spec.schedule.type == "interval" and spec.schedule.every.endswith("h"):
            h = spec.schedule.every[:-1]
            cron_expr = f"0 */{h} * * *"

        cmd = spec.task.command or f"nougen run {spec.task.ref}"
        crontab_line = f"{cron_expr} CRON_TZ={spec.schedule.timezone} {cmd}"
        return {
            "adapter": "unix_cron",
            "cron_expression": cron_expr,
            "timezone": spec.schedule.timezone,
            "crontab_line": crontab_line,
            "overlap_lock": spec.execution.overlap == OverlapPolicy.FORBID,
        }


class FleetNativeSchedulerAdapter(SchedulerAdapter):
    """Adapter for NouGen Native Fleet Scheduler (distributed event bus + state table)."""

    def compile_manifest(self, spec: CronOutSpec) -> Dict[str, Any]:
        return {
            "adapter": "nougen_fleet_native",
            "schedule_id": spec.schedule_id,
            "operator": spec.operator,
            "task_ref": spec.task.ref,
            "cadence": asdict(spec.schedule),
            "execution": {
                "overlap": spec.execution.overlap.value,
                "misfire": spec.execution.misfire.value,
                "jitter_seconds": spec.execution.jitter_seconds,
                "max_runtime_seconds": spec.execution.max_runtime_seconds,
            },
            "governance": asdict(spec.governance),
            "verification": asdict(spec.verification),
            "fleet_dispatch_topic": f"fleet.cron.{spec.schedule_id}",
        }


class CloudflareWorkerSchedulerAdapter(SchedulerAdapter):
    """Adapter for Cloudflare Workers Cron Triggers."""

    def compile_manifest(self, spec: CronOutSpec) -> Dict[str, Any]:
        cron_expr = spec.schedule.every
        if spec.schedule.type == "hourly":
            cron_expr = "0 * * * *"
        elif spec.schedule.type == "daily":
            cron_expr = "0 4 * * *"  # default midnight EST = 04:00 UTC
        elif spec.schedule.type == "interval" and spec.schedule.every.endswith("m"):
            m = spec.schedule.every[:-1]
            cron_expr = f"*/{m} * * * *"
        elif spec.schedule.type == "interval" and spec.schedule.every.endswith("h"):
            h = spec.schedule.every[:-1]
            cron_expr = f"0 */{h} * * *"

        return {
            "adapter": "cloudflare_workers",
            "wrangler_config": {
                "triggers": {
                    "crons": [cron_expr]
                }
            },
            "cron_trigger": cron_expr,
            "worker_handler": "scheduled(event, env, ctx)",
        }


# ============================================================================
# 5. EXECUTION ENGINE & SIMULATOR
# ============================================================================

class CronOutExecutionEngine:
    """Manages active runs, idempotency locks, overlap, retries, and receipts."""

    def __init__(self, node_name: str = "whoart"):
        self.node_name = node_name
        self.active_runs: Dict[str, str] = {}  # schedule_id -> run_key
        self.receipts: List[CronOutReceipt] = []
        self.run_history: Dict[str, int] = {}  # run_key -> attempt_count

    def trigger(
        self,
        spec: CronOutSpec,
        nominal_fire_time_utc: str,
        simulate_failure: bool = False,
    ) -> Tuple[bool, Optional[CronOutReceipt], str]:
        """Attempt to trigger a scheduled run for the given nominal fire time."""
        run_key = spec.calculate_run_key(nominal_fire_time_utc)

        # 1. Overlap Check
        if spec.schedule_id in self.active_runs:
            existing_run_key = self.active_runs[spec.schedule_id]
            if spec.execution.overlap == OverlapPolicy.FORBID:
                return (False, None, f"OVERLAP_FORBIDDEN: schedule {spec.schedule_id} has active run {existing_run_key}")
            elif spec.execution.overlap == OverlapPolicy.REPLACE:
                # Replace active run
                del self.active_runs[spec.schedule_id]

        # 2. Idempotency Check: if this run_key has already succeeded, do not rerun
        past_receipt = next((r for r in self.receipts if r.run_key == run_key and r.outcome == OutcomeStatus.SUCCESS), None)
        if past_receipt:
            return (False, past_receipt, f"IDEMPOTENT_SKIP: run_key {run_key} already completed successfully")

        # 3. Governance check (kill switch)
        if not spec.governance.kill_switch:
            return (False, None, "GOVERNANCE_DENIED: kill switch disabled or denied")

        # Mark active
        self.active_runs[spec.schedule_id] = run_key
        attempt_id = self.run_history.get(run_key, 0) + 1
        self.run_history[run_key] = attempt_id

        actual_start = datetime.now(timezone.utc).isoformat()

        # Simulate execution
        if simulate_failure:
            actual_finish = datetime.now(timezone.utc).isoformat()
            receipt = CronOutReceipt(
                run_key=run_key,
                schedule_id=spec.schedule_id,
                nominal_fire_time=nominal_fire_time_utc,
                actual_start=actual_start,
                actual_finish=actual_finish,
                attempt_id=attempt_id,
                executor_node=self.node_name,
                outcome=OutcomeStatus.FAILED,
                error_message="Simulated run failure",
            )
            # Remove from active
            del self.active_runs[spec.schedule_id]
            self.receipts.append(receipt)
            return (False, receipt, f"EXECUTION_FAILED: attempt {attempt_id} failed")

        actual_finish = datetime.now(timezone.utc).isoformat()
        receipt = CronOutReceipt(
            run_key=run_key,
            schedule_id=spec.schedule_id,
            nominal_fire_time=nominal_fire_time_utc,
            actual_start=actual_start,
            actual_finish=actual_finish,
            attempt_id=attempt_id,
            executor_node=self.node_name,
            outcome=OutcomeStatus.SUCCESS,
        )
        del self.active_runs[spec.schedule_id]
        self.receipts.append(receipt)
        return (True, receipt, "SUCCESS")

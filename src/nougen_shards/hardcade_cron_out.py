"""Hardcade CRON OUT: backend-agnostic temporal deployment operator.

Owner authorial/operator lock, leg 20260923T165947Z (Dave, 2026-09-23).

    CRON OUT = take a proven operation and roll it out across time as a
    persistent, governed, recurring autonomous execution.

    ROLL OUT changes WHERE an operation lives.
    CRON OUT changes WHEN an operation lives.

        "Make time responsible for calling it again."

This is a control-plane transformation operator, not a cron-syntax wrapper.
The semantic layer (this module) owns intent: a :class:`CronOutSchedule`
carries the full contract -- cadence, timezone, overlap policy, misfire
policy, retry, idempotent run identity, governance, verification -- and is
constructed independently of any scheduler backend. A *backend adapter*
(``CronExpressionAdapter``, ``LocalLoopAdapter``, ...) compiles that same
schedule to its own syntax or drives it directly. The adapter owns syntax;
it never owns intent.

    CRON OUT != LOOP IT
    CRON OUT != KEEP IT RUNNING
    CRON OUT != RETRY IT
    CRON OUT != WATCH IT

Explicitly out of scope for this module (per the leg): CoachGovernor/TokenFuse
lease enforcement and fleet-scale distributed leasing are integration points,
declared here as a required field on :class:`Governance` and left for the
lane that owns CoachGovernor to wire in. A schedule with ``lease_required``
unset to a real lease is not runnable -- :meth:`ScheduleState.can_run` refuses
it -- but this module does not itself grant leases.
"""
from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

__all__ = [
    "OverlapPolicy", "MisfirePolicy", "RetryPolicy", "LifecycleState",
    "Cadence", "Reliability", "Governance", "Verification", "CronOutSchedule",
    "RunAttempt", "RunReceipt", "ScheduleState", "CronOutError",
    "IdempotencyViolation", "InvalidTransition", "GovernanceRefused",
    "cron_out", "parse_cron_out_command",
    "CronExpressionAdapter", "LocalLoopAdapter",
]


class CronOutError(Exception):
    """Base error for this module."""


class IdempotencyViolation(CronOutError):
    """Raised if a caller tries to run a second logical occurrence under a
    run_key that has already reached a terminal state without an explicit
    retry (same run_key, new attempt_id)."""


class InvalidTransition(CronOutError):
    """Raised on a state-machine transition the spec does not allow."""


class GovernanceRefused(CronOutError):
    """Raised when a run is attempted without satisfying its declared
    governance requirements (lease, budget, kill switch)."""


# --------------------------------------------------------------- policy enums
class OverlapPolicy(str, Enum):
    FORBID = "forbid"      # a still-running prior occurrence blocks the next
    REPLACE = "replace"    # cancel the running occurrence, start the new one
    ALLOW = "allow"        # concurrent occurrences permitted


class MisfirePolicy(str, Enum):
    """What happens to fire times missed while nothing was watching (the
    process was down, the node was asleep, ...)."""
    SKIP = "skip"                  # drop every missed occurrence
    COALESCE_LATEST = "coalesce_latest"  # run once for the most recent miss
    EARLIEST = "earliest"          # run once for the oldest miss
    ALL = "all"                    # run once per missed occurrence (backfill)


class RetryPolicy(str, Enum):
    NONE = "none"
    FIXED = "fixed"
    EXPONENTIAL_BACKOFF = "exponential_backoff"


class LifecycleState(str, Enum):
    """The state machine from the leg, verbatim. Integrates with
    CoachGovernor's NORMAL/WATCH/THROTTLE/CONTAINMENT/CHECKPOINT/KILL levels
    rather than duplicating a second safety system: a governor level of
    THROTTLE or worse forces a transition to THROTTLED/SUSPENDED regardless
    of this state machine's own edges (see :meth:`ScheduleState.apply_governor_level`).
    """
    MANUAL = "manual"
    PROVEN = "proven"
    CRONNED = "cronned"
    ARMED = "armed"
    DUE = "due"
    LEASED = "leased"
    RUNNING = "running"
    VERIFYING = "verifying"
    RECEIPTED = "receipted"
    SLEEPING = "sleeping"
    # failure branches
    RETRYING = "retrying"
    THROTTLED = "throttled"
    QUARANTINED = "quarantined"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


# The happy-path edges plus the documented failure branches, exactly as the
# leg's state machine names them. Anything not listed here is refused by
# ScheduleState.transition() -- the state machine is closed, not advisory.
_ALLOWED_EDGES: Dict[LifecycleState, Tuple[LifecycleState, ...]] = {
    LifecycleState.MANUAL: (LifecycleState.PROVEN,),
    LifecycleState.PROVEN: (LifecycleState.CRONNED,),
    LifecycleState.CRONNED: (LifecycleState.ARMED, LifecycleState.SUSPENDED),
    LifecycleState.ARMED: (LifecycleState.DUE, LifecycleState.SUSPENDED, LifecycleState.TERMINATED),
    LifecycleState.DUE: (LifecycleState.LEASED, LifecycleState.SLEEPING,  # overlap FORBID: skip back to sleep
                         LifecycleState.THROTTLED, LifecycleState.SUSPENDED),
    LifecycleState.LEASED: (LifecycleState.RUNNING, LifecycleState.QUARANTINED, LifecycleState.SUSPENDED),
    LifecycleState.RUNNING: (LifecycleState.VERIFYING, LifecycleState.RETRYING,
                             LifecycleState.THROTTLED, LifecycleState.QUARANTINED,
                             LifecycleState.SUSPENDED, LifecycleState.TERMINATED),
    LifecycleState.VERIFYING: (LifecycleState.RECEIPTED, LifecycleState.QUARANTINED),
    LifecycleState.RECEIPTED: (LifecycleState.SLEEPING,),
    LifecycleState.SLEEPING: (LifecycleState.DUE, LifecycleState.SUSPENDED, LifecycleState.TERMINATED),
    LifecycleState.RETRYING: (LifecycleState.LEASED, LifecycleState.QUARANTINED, LifecycleState.SUSPENDED),
    LifecycleState.THROTTLED: (LifecycleState.DUE, LifecycleState.SUSPENDED),
    LifecycleState.QUARANTINED: (LifecycleState.SUSPENDED, LifecycleState.TERMINATED),
    LifecycleState.SUSPENDED: (LifecycleState.ARMED, LifecycleState.TERMINATED),
    LifecycleState.TERMINATED: (),
}


# ------------------------------------------------------------- schedule parts
@dataclass(frozen=True)
class Cadence:
    """Cadence + explicit timezone. ``every`` is an ISO-8601-ish duration
    shorthand ("15m", "1h", "1d") OR a cron expression when ``kind`` is
    "cron". Timezone is never implicit -- the leg requires it explicit."""
    kind: str               # "interval" | "cron"
    every: str              # "15m" style, or a 5-field cron expression
    timezone: str           # IANA zone name, e.g. "America/New_York"

    def __post_init__(self) -> None:
        if not self.timezone:
            raise ValueError("Cadence.timezone must be explicit -- the leg forbids implicit timezone")
        ZoneInfo(self.timezone)  # raises if unknown; fail fast, not at fire time
        if self.kind not in ("interval", "cron"):
            raise ValueError(f"Cadence.kind must be 'interval' or 'cron', got {self.kind!r}")
        if self.kind == "interval":
            _parse_interval(self.every)  # validate now


def _parse_interval(spec: str) -> timedelta:
    units = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    if len(spec) < 2 or spec[-1] not in units:
        raise ValueError(f"unrecognised interval {spec!r}; expected e.g. '15m', '1h', '1d'")
    try:
        n = int(spec[:-1])
    except ValueError:
        raise ValueError(f"unrecognised interval {spec!r}; expected e.g. '15m', '1h', '1d'") from None
    if n <= 0:
        raise ValueError(f"interval must be positive, got {spec!r}")
    return timedelta(**{units[spec[-1]]: n})


@dataclass(frozen=True)
class Reliability:
    overlap: OverlapPolicy = OverlapPolicy.FORBID
    misfire: MisfirePolicy = MisfirePolicy.COALESCE_LATEST
    jitter_seconds: int = 0
    max_runtime_seconds: int = 600
    retry: RetryPolicy = RetryPolicy.NONE
    max_attempts: int = 1
    dead_letter: bool = True

    def __post_init__(self) -> None:
        if self.jitter_seconds < 0:
            raise ValueError("jitter_seconds must be >= 0")
        if self.max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be > 0")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.retry is RetryPolicy.NONE and self.max_attempts > 1:
            raise ValueError("retry=NONE but max_attempts>1 -- retry != recurrence, "
                            "a retry policy must be set to retry")


@dataclass(frozen=True)
class Governance:
    """Fleet-safety gate. This module enforces PRESENCE of a lease/budget
    object when required=True; it does not itself grant leases -- that is
    CoachGovernor/TokenFuse's job, wired in by whoever owns that lane."""
    lease_required: bool = True
    budget_required: bool = True
    kill_switch: bool = True
    lease_token: Optional[str] = None   # supplied by CoachGovernor at run time
    budget_token: Optional[str] = None  # supplied by TokenFuse at run time
    killed: bool = False


@dataclass(frozen=True)
class Verification:
    receipt_required: bool = True
    record_nominal_fire_time: bool = True
    record_actual_start: bool = True
    record_actual_finish: bool = True
    record_executor: bool = True
    record_outcome: bool = True


@dataclass(frozen=True)
class CronOutSchedule:
    """The full backend-neutral schedule contract from the leg's canonical
    object, as an immutable, hashable value. ``generation`` increments on any
    edit to cadence/execution/reliability -- it is part of the deterministic
    run_key so an edited schedule never collides with a stale one at the same
    nominal fire time."""
    schedule_id: str
    task_ref: str
    task_revision: str
    cadence: Cadence
    reliability: Reliability = field(default_factory=Reliability)
    governance: Governance = field(default_factory=Governance)
    verification: Verification = field(default_factory=Verification)
    generation: int = 1

    def __post_init__(self) -> None:
        if not self.schedule_id or not self.task_ref:
            raise ValueError("schedule_id and task_ref are required")

    def edited(self, **changes: Any) -> "CronOutSchedule":
        """Produce a new generation. Bumps generation automatically unless
        the caller passes one explicitly."""
        changes.setdefault("generation", self.generation + 1)
        return replace(self, **changes)

    def next_fire_after(self, after: datetime) -> datetime:
        """Next nominal fire time strictly after ``after``, in the schedule's
        own timezone. Interval cadence only in this module -- cron-expression
        cadence delegates next-fire computation to whatever adapter compiles
        it (this module does not implement a cron parser; see
        CronExpressionAdapter, which is a compiler, not a scheduler)."""
        if self.cadence.kind != "interval":
            raise CronOutError("next_fire_after is only implemented for interval cadence in this "
                              "module; cron-kind cadences are computed by their backend adapter")
        tz = ZoneInfo(self.cadence.timezone)
        step = _parse_interval(self.cadence.every)
        after = after.astimezone(tz)
        # Anchor to epoch-in-zone so restarts land on the same grid regardless
        # of when the process happened to start.
        epoch = datetime(1970, 1, 1, tzinfo=tz)
        elapsed = after - epoch
        steps = int(elapsed / step) + 1
        return epoch + steps * step


def run_key(schedule: CronOutSchedule, nominal_fire_time: datetime) -> str:
    """Deterministic logical run identity, exactly per the leg's spec:
    HASH(schedule_id + nominal_fire_time + schedule_generation). A retry
    keeps this key and increments attempt_id; it is NEVER a new logical run."""
    if nominal_fire_time.tzinfo is None:
        raise ValueError("nominal_fire_time must be timezone-aware")
    blob = json.dumps({
        "schedule_id": schedule.schedule_id,
        "nominal_fire_time": nominal_fire_time.astimezone(timezone.utc).isoformat(),
        "generation": schedule.generation,
    }, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


# ------------------------------------------------------------------- receipts
@dataclass(frozen=True)
class RunAttempt:
    attempt_id: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    outcome: Optional[str] = None       # "success" | "failure" | "timeout" | "quarantined"
    executor: Optional[str] = None      # machine/agent that actually ran it


@dataclass(frozen=True)
class RunReceipt:
    """The provenance-bearing receipt required by done-when (6). One receipt
    per logical run (run_key), carrying every attempt made under it -- a
    retry never gets its own receipt, it extends this one."""
    schedule_id: str
    run_key: str
    nominal_fire_time: datetime
    generation: int
    attempts: Tuple[RunAttempt, ...]
    final_outcome: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schedule_id": self.schedule_id, "run_key": self.run_key,
            "nominal_fire_time": self.nominal_fire_time.astimezone(timezone.utc).isoformat(),
            "generation": self.generation,
            "attempts": [
                {"attempt_id": a.attempt_id,
                 "started_at": a.started_at.astimezone(timezone.utc).isoformat(),
                 "finished_at": a.finished_at.astimezone(timezone.utc).isoformat() if a.finished_at else None,
                 "outcome": a.outcome, "executor": a.executor}
                for a in self.attempts
            ],
            "final_outcome": self.final_outcome,
        }


# --------------------------------------------------------------- run tracking
class ScheduleState:
    """Mutable run-tracking for one CronOutSchedule: current lifecycle state,
    the logical run currently in flight (if any), and every receipted run.
    This is the idempotency and overlap enforcement point -- not the schedule
    itself, which stays an immutable value."""

    def __init__(self, schedule: CronOutSchedule):
        self.schedule = schedule
        self.state = LifecycleState.CRONNED
        self._current_run_key: Optional[str] = None
        self._current_attempts: Dict[str, List[RunAttempt]] = {}
        self._nominal_fire_times: Dict[str, datetime] = {}  # run_key -> nominal fire time
        self.receipts: Dict[str, RunReceipt] = {}   # run_key -> receipt
        self._governor_level = "NORMAL"

    # -- state machine -----------------------------------------------------
    def transition(self, to: LifecycleState) -> None:
        allowed = _ALLOWED_EDGES.get(self.state, ())
        if to not in allowed:
            raise InvalidTransition(f"{self.state.value} -> {to.value} is not a legal edge "
                                   f"(allowed: {[s.value for s in allowed]})")
        self.state = to

    def apply_governor_level(self, level: str) -> None:
        """CoachGovernor integration point (leg: 'integrate ... rather than
        creating a second safety system'). A THROTTLE-or-worse level forces
        this schedule out of RUNNING/DUE regardless of its own edges."""
        self._governor_level = level
        if level in ("CONTAINMENT", "CHECKPOINT", "KILL") and self.state not in (
                LifecycleState.SUSPENDED, LifecycleState.TERMINATED):
            self.state = LifecycleState.SUSPENDED
        elif level == "THROTTLE" and self.state is LifecycleState.DUE:
            self.state = LifecycleState.THROTTLED

    # -- governance ----------------------------------------------------------
    def _check_governance(self) -> None:
        g = self.schedule.governance
        if g.killed:
            raise GovernanceRefused(f"{self.schedule.schedule_id}: kill switch engaged")
        if g.lease_required and not g.lease_token:
            raise GovernanceRefused(f"{self.schedule.schedule_id}: lease required, none granted")
        if g.budget_required and not g.budget_token:
            raise GovernanceRefused(f"{self.schedule.schedule_id}: budget required, none granted")
        if self._governor_level in ("CONTAINMENT", "CHECKPOINT", "KILL"):
            raise GovernanceRefused(f"{self.schedule.schedule_id}: governor level "
                                   f"{self._governor_level} refuses new runs")

    # -- the fire path -------------------------------------------------------
    def begin_run(self, nominal_fire_time: datetime, executor: str,
                 now: Optional[datetime] = None) -> Tuple[str, int]:
        """Start (or retry) the logical run for ``nominal_fire_time``.
        Returns (run_key, attempt_id). Overlap=FORBID refuses a second
        concurrent logical run; a second call with the SAME run_key while one
        is in flight is a retry (new attempt, same run_key), never a new run.
        """
        now = now or datetime.now(timezone.utc)
        key = run_key(self.schedule, nominal_fire_time)

        if key in self.receipts and self.receipts[key].final_outcome == "success":
            raise IdempotencyViolation(
                f"{self.schedule.schedule_id}: run_key {key} already succeeded; "
                f"refusing to re-run the same logical occurrence")

        if self._current_run_key is not None and self._current_run_key != key:
            if self.schedule.reliability.overlap is OverlapPolicy.FORBID:
                raise CronOutError(f"{self.schedule.schedule_id}: overlap=forbid, "
                                  f"run {self._current_run_key} still in flight")
            if self.schedule.reliability.overlap is OverlapPolicy.REPLACE:
                self._current_attempts.pop(self._current_run_key, None)
            # ALLOW: fall through, both proceed independently

        self._check_governance()

        attempts = self._current_attempts.setdefault(key, [])
        if len(attempts) >= self.schedule.reliability.max_attempts:
            raise CronOutError(f"{self.schedule.schedule_id}: run_key {key} exhausted "
                              f"max_attempts={self.schedule.reliability.max_attempts}")
        attempt_id = len(attempts) + 1
        attempts.append(RunAttempt(attempt_id=attempt_id, started_at=now, executor=executor))
        self._current_run_key = key
        self._nominal_fire_times[key] = nominal_fire_time
        if self.state in (LifecycleState.DUE, LifecycleState.THROTTLED):
            self.transition(LifecycleState.LEASED)
        if self.state is LifecycleState.LEASED:
            self.transition(LifecycleState.RUNNING)
        return key, attempt_id

    def finish_run(self, run_key_: str, attempt_id: int, outcome: str,
                  now: Optional[datetime] = None) -> RunReceipt:
        """Close out an attempt. outcome in {"success","failure","timeout","quarantined"}.
        Emits/updates the run's receipt. Retries happen by calling begin_run
        again with the same nominal_fire_time (same run_key) after a
        "failure" outcome, per the schedule's retry policy -- callers, not
        this method, decide whether to retry."""
        now = now or datetime.now(timezone.utc)
        attempts = self._current_attempts.get(run_key_)
        if not attempts or attempts[-1].attempt_id != attempt_id:
            raise CronOutError(f"no in-flight attempt {attempt_id} for run_key {run_key_}")
        attempts[-1] = replace(attempts[-1], finished_at=now, outcome=outcome)

        if self.state is LifecycleState.RUNNING:
            self.transition(LifecycleState.VERIFYING)
        if outcome == "success":
            if self.state is LifecycleState.VERIFYING:
                self.transition(LifecycleState.RECEIPTED)
            final = "success"
        elif outcome == "quarantined":
            self.state = LifecycleState.QUARANTINED
            final = "quarantined"
        else:
            final = outcome  # failure/timeout: receipt records it; caller decides retry vs give up

        receipt = RunReceipt(
            schedule_id=self.schedule.schedule_id, run_key=run_key_,
            nominal_fire_time=self._nominal_fire_times[run_key_],
            generation=self.schedule.generation,
            attempts=tuple(attempts), final_outcome=final)
        self.receipts[run_key_] = receipt

        if self.state is LifecycleState.RECEIPTED:
            self.transition(LifecycleState.SLEEPING)
            self.transition(LifecycleState.DUE)
            self._current_run_key = None
        return receipt


# ----------------------------------------------------------------- adapters
class CronExpressionAdapter:
    """Compiles interval cadence to a standard 5-field cron expression --
    the portable text syntax underneath Unix cron, systemd timers (via
    OnCalendar's cron-compatible form), Kubernetes CronJob's `schedule:`
    field, and most cloud managed schedulers. This adapter does not install
    or run anything; it is a pure compiler, satisfying the leg's 'fleet/
    cloud-style adapter' with the one syntax nearly every such backend
    already accepts, rather than writing five thin wrappers around each
    platform's SDK.
    """
    name = "cron_expression"

    @staticmethod
    def compile(schedule: CronOutSchedule) -> str:
        if schedule.cadence.kind == "cron":
            return schedule.cadence.every
        step = _parse_interval(schedule.cadence.every)
        total_minutes = int(step.total_seconds() // 60)
        if step.total_seconds() % 60:
            raise CronOutError("cron expression compiler only supports whole-minute intervals; "
                              f"{schedule.cadence.every!r} is sub-minute")
        if total_minutes < 60:
            return f"*/{total_minutes} * * * *"
        if total_minutes % 60 == 0 and total_minutes < 1440:
            return f"0 */{total_minutes // 60} * * *"
        if total_minutes % 1440 == 0:
            return f"0 0 */{total_minutes // 1440} * *"
        raise CronOutError(f"{schedule.cadence.every!r} has no clean 5-field cron representation; "
                          f"use cadence.kind='cron' and supply the expression directly")


class LocalLoopAdapter:
    """The local backend: drives a ScheduleState directly in-process,
    computing due fire times and invoking the operation. This is the 'at
    least one local adapter' from done-when (3) -- no external scheduler
    dependency, suitable for a single node or as the reference
    implementation every other adapter is tested against.

    Sleeps are real time.sleep() calls; callers driving tests should call
    ``tick()`` directly instead of ``run_forever()``.
    """

    def __init__(self, schedule: CronOutSchedule, operation: Callable[[], str],
                executor_name: str = "local"):
        self.schedule = schedule
        self.state = ScheduleState(schedule)
        self.operation = operation
        self.executor_name = executor_name
        self._last_fire: Optional[datetime] = None
        self.state.transition(LifecycleState.ARMED)

    def tick(self, now: Optional[datetime] = None) -> Optional[RunReceipt]:
        """Check whether a fire is due and, if so, run one logical
        occurrence synchronously. Returns the receipt if a run happened,
        else None. Applies jitter as a pre-run sleep, misfire policy when
        more than one nominal fire time has been missed since the last tick,
        and honours overlap/governance via ScheduleState."""
        now = now or datetime.now(timezone.utc)
        if self.state.state is LifecycleState.ARMED:
            self.state.transition(LifecycleState.DUE)

        anchor = self._last_fire or now
        due_times = self._missed_fires(anchor, now)
        if not due_times:
            return None
        fire_times = self._apply_misfire_policy(due_times)
        self._last_fire = due_times[-1]

        receipt = None
        for nominal in fire_times:
            if self.schedule.reliability.jitter_seconds:
                time.sleep(random.uniform(0, self.schedule.reliability.jitter_seconds))
            key, attempt_id = self.state.begin_run(nominal, self.executor_name, now=now)
            try:
                outcome = self.operation()
                receipt = self.state.finish_run(key, attempt_id, "success" if outcome == "success" else outcome,
                                               now=datetime.now(timezone.utc))
            except Exception:
                receipt = self.state.finish_run(key, attempt_id, "failure", now=datetime.now(timezone.utc))
                if self.schedule.reliability.dead_letter:
                    pass  # dead-lettering sink is an integration point for the lane that owns storage
                raise
        return receipt

    def _missed_fires(self, anchor: datetime, now: datetime) -> List[datetime]:
        """Every nominal fire strictly after ``anchor`` (the last fire we
        already ran) up to and including ``now``. Must never re-include
        ``anchor`` itself -- it was already run."""
        out: List[datetime] = []
        nxt = self.schedule.next_fire_after(anchor)
        while nxt <= now and len(out) < 10_000:  # bounded: never spin forever on a bad clock
            out.append(nxt)
            nxt = self.schedule.next_fire_after(nxt)
        return out

    def _apply_misfire_policy(self, due: List[datetime]) -> List[datetime]:
        policy = self.schedule.reliability.misfire
        if len(due) <= 1 or policy is MisfirePolicy.ALL:
            return due
        if policy is MisfirePolicy.SKIP:
            return []
        if policy is MisfirePolicy.COALESCE_LATEST:
            return [due[-1]]
        if policy is MisfirePolicy.EARLIEST:
            return [due[0]]
        return due


# ------------------------------------------------------------------ grammar
_KEYWORDS = ("EVERY", "TZ", "OVERLAP", "MISFIRE", "JITTER", "RETRY", "BUDGET", "UNTIL", "RECEIPT")


def parse_cron_out_command(text: str) -> Dict[str, Any]:
    """Parse the leg's normalized operator grammar:

        CRON OUT <operation>
        EVERY <cadence>
        TZ <timezone>
        OVERLAP <forbid|replace|allow>
        MISFIRE <skip|latest|earliest|all>
        JITTER <window>
        RETRY <policy>
        BUDGET <lease>
        UNTIL <boundary>
        RECEIPT <sink>

    Also accepts the loose natural-speech forms the leg requires stay valid
    ("Cron out the tracker reconciliation every hour.", "Cron this out
    nightly.") by degrading gracefully: whatever cannot be parsed as a
    keyword clause is folded into the operation name, so speech never
    crashes the parser -- it just produces a schedule with fewer explicit
    clauses, and the caller supplies sane defaults for the rest.

    Returns a dict of raw clause values; callers turn that into a
    CronOutSchedule with their own operation/task lookup. This function does
    not itself construct a CronOutSchedule because the operation name here is
    free text, not yet a resolved task_ref/task_revision.
    """
    stripped = text.strip().rstrip(".")
    upper = stripped.upper()
    if not upper.startswith("CRON OUT") and not upper.startswith("CRON THIS OUT") and \
       not upper.startswith("CRON THAT") and "CRON" not in upper.split()[:1]:
        raise CronOutError(f"not a CRON OUT command: {text!r}")

    # Strip the leading verb phrase.
    for lead in ("CRON OUT ", "CRON THIS OUT", "CRON THAT ", "CRON "):
        if upper.startswith(lead):
            stripped = stripped[len(lead):].strip()
            break
    # "cron THAT <op> OUT ..." / "cron THIS <op> OUT ...": the trailing "out"
    # (the second half of the split verb, e.g. "Cron that sweep out every
    # fifteen minutes") belongs to the verb, not the operation name.
    tail_words = stripped.split()
    if tail_words and tail_words[0].upper() != "OUT":
        for i, w in enumerate(tail_words[1:], start=1):
            if w.upper() == "OUT":
                stripped = " ".join(tail_words[:i] + tail_words[i + 1:])
                break
            if w.upper() in _KEYWORDS or w.upper() == "EVERY":
                break

    clauses: Dict[str, Any] = {"operation": stripped, "raw": text}
    upper_words = stripped.upper().split()
    cut = len(stripped)
    for kw in _KEYWORDS:
        idx = upper_words.count(kw)
        if not idx:
            continue
        pos = stripped.upper().find(" " + kw + " ")
        if pos == -1 and stripped.upper().startswith(kw + " "):
            pos = -1 + 1  # keyword at the very start (rare)
        if pos == -1:
            continue
        cut = min(cut, pos)
    if cut < len(stripped):
        clauses["operation"] = stripped[:cut].strip().rstrip(",")

    def _extract(keyword: str) -> Optional[str]:
        u = stripped.upper()
        marker = f" {keyword} "
        start = u.find(marker)
        if start == -1:
            return None
        start += len(marker)
        end = len(stripped)
        for other in _KEYWORDS:
            if other == keyword:
                continue
            p = u.find(f" {other} ", start)
            if p != -1:
                end = min(end, p)
        return stripped[start:end].strip().rstrip(",")

    for kw in _KEYWORDS:
        val = _extract(kw)
        if val:
            clauses[kw.lower()] = val

    # "every hour" / "nightly" / "every fifteen minutes" -> a best-effort
    # interval string. Ambiguous or unrecognised phrasing is left as raw text
    # under 'every_phrase' for the caller to resolve -- never guessed into a
    # wrong cadence.
    if "every" in clauses:
        try:
            _parse_interval(clauses["every"])
            clauses["every_interval"] = clauses["every"]  # already raw interval syntax, e.g. "15m"
        except ValueError:
            clauses["every_interval"] = _phrase_to_interval(clauses["every"])
    elif "nightly" in stripped.lower():
        clauses["every_interval"] = "1d"
    return clauses


_WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10,
                 "fifteen": 15, "twenty": 20, "thirty": 30, "forty-five": 45, "sixty": 60}


def _phrase_to_interval(phrase: str) -> Optional[str]:
    p = phrase.lower().strip()
    unit = "m" if "minute" in p else "h" if "hour" in p else "d" if ("day" in p or p == "nightly") else None
    if unit is None:
        return None
    words = p.split()
    n = None
    for w in words:
        if w.isdigit():
            n = int(w)
            break
        if w in _WORD_NUMBERS:
            n = _WORD_NUMBERS[w]
            break
    if n is None:
        n = 1  # "every hour" with no number -> every 1 hour
    return f"{n}{unit}"


# --------------------------------------------------------------- entry point
def cron_out(operation: str, task_revision: str, temporal_policy: Cadence,
            execution_policy: Optional[Reliability] = None,
            governance: Optional[Governance] = None,
            verification: Optional[Verification] = None,
            schedule_id: Optional[str] = None) -> CronOutSchedule:
    """The recommended abstract function from the leg, realised:

        CRON_OUT(operation, temporal_policy, execution_policy,
                 governance, backend, verification) -> persistent schedule

    ``backend`` is deliberately not a parameter here: this function returns
    the backend-neutral schedule object; the CALLER picks an adapter
    (CronExpressionAdapter to compile, LocalLoopAdapter to run) precisely
    because the leg's semantic layer must not know about scheduler syntax.
    """
    return CronOutSchedule(
        schedule_id=schedule_id or operation.strip().lower().replace(" ", "_"),
        task_ref=operation, task_revision=task_revision, cadence=temporal_policy,
        reliability=execution_policy or Reliability(),
        governance=governance or Governance(),
        verification=verification or Verification(),
    )



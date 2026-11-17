"""Closed-loop relentless execution contract for NouGenShards.

Implements the governed execution invariants (31224@db6 / 31502@db8 / 32512@db7):
- Machine-checkable success criteria (refuses prose-only goals).
- Per-task append-only hash-chained JSONL ledger + global LOOP_STOP kill switch.
- Single-owner TTL lease with in-step heartbeat (crash-resumable, no duplicate runners).
- Failure classification (transient / deterministic / permanent) with mandatory
  strategy_hash + what_we_learned change on deterministic repair.
- Budget & circuit-breaker enforcement ($0 paid ceiling, 64K call cap, 70%/90%/100% gates).
- Independent verifier (`verify_task`) as the sole path to `done`.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

VALID_CRITERION_KINDS = ("cmd", "ci", "review", "http", "assert", "policy", "shard")
FREE_ROUTES = ("nvidia_nim_free", "openrouter_free", "ollama_local")

_TRANSIENT_MARKERS = ("429", "502", "503", "504", "timeout", "timed out", "rate limit", "rate_limit", "connection")
_PERMANENT_MARKERS = ("401", "403", "unauthorized", "forbidden", "insufficient_quota", "invalid_api_key", "billing")


class LoopContractError(RuntimeError):
    """Base error for closed-loop contract violations."""


class ProseGoalError(LoopContractError):
    """Raised when a task has no machine-checkable success criteria (AT-01)."""


class LeaseConflictError(LoopContractError):
    """Raised when another active owner holds a valid lease (AT-07)."""


class StrategyRepeatError(LoopContractError):
    """Raised when a deterministic retry repeats strategy_hash or omits what_we_learned (AT-03)."""


class BudgetTrippedError(LoopContractError):
    """Raised when a budget, kill switch, or circuit breaker trips (AT-09, AT-12)."""


class NoFreeRouteError(LoopContractError):
    """Raised when all free drafting routes are exhausted (AT-10)."""


def state_root() -> Path:
    env = os.environ.get("NOUGEN_LOOP_STATE_DIR", "").strip()
    return Path(env) if env else (Path.home() / ".nougen" / "state")


def ledger_dir() -> Path:
    env = os.environ.get("NOUGEN_LOOP_LEDGER_DIR", "").strip()
    return Path(env) if env else (state_root() / "loop_ledger")


def ledger_path(task_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in task_id.strip()) or "task"
    return ledger_dir() / f"{safe}.jsonl"


def kill_switch_path() -> Path:
    env = os.environ.get("NOUGEN_LOOP_STOP", "").strip()
    return Path(env) if env else (state_root() / "LOOP_STOP")


def is_stopped() -> bool:
    return kill_switch_path().exists()


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _hash_entry(payload: dict[str, Any], prev_hash: str) -> str:
    body = json.dumps({"prev_hash": prev_hash, **payload}, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass
class SuccessCriterion:
    kind: str
    target: str
    expected: Any = None
    fn: Optional[Callable[[], tuple[bool, str]]] = field(default=None, repr=False)

    def validate(self) -> None:
        if self.kind not in VALID_CRITERION_KINDS:
            raise ProseGoalError(f"Unsupported criterion kind {self.kind!r}; expected one of {VALID_CRITERION_KINDS}")
        if not (self.target or "").strip() and self.fn is None:
            raise ProseGoalError(f"Criterion {self.kind!r} requires a non-empty target")


@dataclass
class Budget:
    max_attempts: int = 3
    max_transient_retries: int = 3
    max_tokens: int = 50_000
    max_wall_s: float = 3600.0
    max_call_tokens: int = 64_000
    max_paid_usd: float = 0.0
    warn_ratio: float = 0.70
    throttle_ratio: float = 0.90
    repeat_failure_stop: int = 3


def validate_criteria(criteria: list[SuccessCriterion]) -> None:
    """Refuse prose-only goals without machine-checkable success criteria (AT-01)."""
    if not criteria:
        raise ProseGoalError("Refusing task without machine-checkable success criteria (AT-01)")
    for c in criteria:
        c.validate()


def read_ledger(task_id: str) -> list[dict[str, Any]]:
    path = ledger_path(task_id)
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        entries.append(json.loads(line))
    return entries


def verify_ledger_chain(task_id: str) -> bool:
    entries = read_ledger(task_id)
    prev = "GENESIS"
    for entry in entries:
        recorded_prev = entry.get("prev_hash")
        recorded_hash = entry.get("entry_hash")
        if recorded_prev != prev:
            return False
        body = {k: v for k, v in entry.items() if k not in ("prev_hash", "entry_hash")}
        if _hash_entry(body, prev) != recorded_hash:
            return False
        prev = recorded_hash
    return True


def append_ledger(task_id: str, event: str, data: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    path = ledger_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = read_ledger(task_id)
    prev_hash = entries[-1]["entry_hash"] if entries else "GENESIS"
    payload: dict[str, Any] = {
        "ts": _utc_now(),
        "epoch": time.time(),
        "task_id": task_id,
        "event": event,
        "data": data or {},
    }
    entry_hash = _hash_entry(payload, prev_hash)
    record = {**payload, "prev_hash": prev_hash, "entry_hash": entry_hash}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=True) + "\n")
    return record


def current_status(task_id: str) -> str:
    """Return latest authoritative task status. Only `verify_done` yields `done` (AT-02)."""
    for entry in reversed(read_ledger(task_id)):
        ev = entry.get("event")
        if ev == "verify_done":
            return "done"
        if ev in ("verify_failed", "aborted", "recovered"):
            return ev
        if ev == "init":
            return "open"
    return "new"


def _active_lease(entries: list[dict[str, Any]], now: float) -> Optional[dict[str, Any]]:
    lease: Optional[dict[str, Any]] = None
    for entry in entries:
        ev = entry.get("event")
        d = entry.get("data") or {}
        if ev in ("lease_acquired", "heartbeat"):
            lease = {"owner": d.get("owner"), "expires_at": float(d.get("expires_at", 0.0))}
        elif ev == "lease_released":
            if lease and lease.get("owner") == d.get("owner"):
                lease = None
    if lease and lease["expires_at"] > now:
        return lease
    return None


def acquire_lease(task_id: str, owner: str, ttl_s: float = 900.0, *, now: Optional[float] = None) -> dict[str, Any]:
    """Acquire single-owner lease; second runner stands down while fresh (AT-07)."""
    ts_now = time.time() if now is None else now
    entries = read_ledger(task_id)
    active = _active_lease(entries, ts_now)
    if active and active["owner"] != owner:
        raise LeaseConflictError(f"Task {task_id!r} lease held by {active['owner']!r} until {active['expires_at']:.0f}")
    return append_ledger(task_id, "lease_acquired", {"owner": owner, "ttl_s": ttl_s, "expires_at": ts_now + ttl_s})


def heartbeat(task_id: str, owner: str, ttl_s: float = 900.0, *, now: Optional[float] = None) -> dict[str, Any]:
    """Extend active lease during long-running steps (AT-08)."""
    ts_now = time.time() if now is None else now
    entries = read_ledger(task_id)
    active = _active_lease(entries, ts_now)
    if active and active["owner"] != owner:
        raise LeaseConflictError(f"Cannot heartbeat: lease held by {active['owner']!r}")
    return append_ledger(task_id, "heartbeat", {"owner": owner, "ttl_s": ttl_s, "expires_at": ts_now + ttl_s})


def release_lease(task_id: str, owner: str) -> dict[str, Any]:
    return append_ledger(task_id, "lease_released", {"owner": owner})


def classify_failure(error_text: str) -> str:
    """Classify failure as permanent, transient, or deterministic."""
    low = (error_text or "").lower()
    if any(m in low for m in _PERMANENT_MARKERS):
        return "permanent"
    if any(m in low for m in _TRANSIENT_MARKERS):
        return "transient"
    return "deterministic"


def compute_strategy_hash(strategy_desc: str) -> str:
    return hashlib.sha256((strategy_desc or "").strip().encode("utf-8")).hexdigest()[:16]


def validate_retry_strategy(task_id: str, strategy_hash: str, what_we_learned: str) -> None:
    """Refuse deterministic retries with identical strategy_hash or empty what_we_learned (AT-03)."""
    if not (what_we_learned or "").strip():
        raise StrategyRepeatError("Deterministic retry requires non-empty what_we_learned (AT-03)")
    if not (strategy_hash or "").strip():
        raise StrategyRepeatError("Deterministic retry requires non-empty strategy_hash (AT-03)")
    seen = {
        (e.get("data") or {}).get("strategy_hash")
        for e in read_ledger(task_id)
        if e.get("event") == "attempt"
    }
    if strategy_hash in seen:
        raise StrategyRepeatError(f"Refusing repeated strategy_hash {strategy_hash!r} for {task_id!r} (AT-03)")


def check_budget(
    task_id: str,
    budget: Budget,
    *,
    call_tokens: int = 0,
    paid_usd: float = 0.0,
    started_epoch: Optional[float] = None,
) -> str:
    """Enforce kill switch, call ceiling, zero-paid rule, and circuit breaker (AT-09, AT-12)."""
    if is_stopped():
        raise BudgetTrippedError(f"Kill switch active at {kill_switch_path()}")
    if paid_usd > budget.max_paid_usd:
        raise BudgetTrippedError(f"Paid spend ${paid_usd:.4f} exceeds cap ${budget.max_paid_usd:.4f}")
    if call_tokens > budget.max_call_tokens:
        raise BudgetTrippedError(f"Single call tokens {call_tokens} exceeds cap {budget.max_call_tokens} (AT-09)")

    entries = read_ledger(task_id)
    attempts = [e for e in entries if e.get("event") == "attempt"]
    total_tokens = sum(int((e.get("data") or {}).get("tokens", 0)) for e in attempts) + call_tokens
    if total_tokens >= budget.max_tokens:
        raise BudgetTrippedError(f"Task tokens {total_tokens} reached cap {budget.max_tokens}")
    if len(attempts) >= budget.max_attempts:
        raise BudgetTrippedError(f"Task attempts {len(attempts)} reached cap {budget.max_attempts}")
    if started_epoch is not None and (time.time() - started_epoch) >= budget.max_wall_s:
        raise BudgetTrippedError(f"Wall clock exceeded {budget.max_wall_s}s")

    # Consecutive same-class failures breaker (AT-12)
    fail_classes = [
        (e.get("data") or {}).get("failure_class")
        for e in entries
        if e.get("event") == "attempt_failed" and (e.get("data") or {}).get("failure_class")
    ]
    if len(fail_classes) >= budget.repeat_failure_stop:
        tail = fail_classes[-budget.repeat_failure_stop :]
        if len(set(tail)) == 1:
            raise BudgetTrippedError(
                f"Circuit breaker tripped: {budget.repeat_failure_stop} consecutive {tail[0]!r} failures (AT-12)"
            )

    ratio = total_tokens / max(budget.max_tokens, 1)
    if ratio >= budget.throttle_ratio:
        return "throttle"
    if ratio >= budget.warn_ratio:
        return "warn"
    return "ok"


def select_free_route(throttled: set[str] | None = None, routes: tuple[str, ...] = FREE_ROUTES) -> str:
    """Return first available free route; fail closed if none remain (AT-04, AT-10)."""
    blocked = throttled or set()
    for r in routes:
        if r not in blocked:
            return r
    raise NoFreeRouteError("All free drafting routes exhausted; failing closed (AT-10)")


def _eval_criterion(c: SuccessCriterion, cwd: Path) -> tuple[bool, str]:
    if c.fn is not None:
        return c.fn()
    if c.kind == "cmd":
        proc = subprocess.run(c.target, cwd=cwd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        ok = proc.returncode == 0
        tail = "\n".join((proc.stdout + "\n" + proc.stderr).strip().splitlines()[-8:])
        return ok, f"rc={proc.returncode} {tail}".strip()
    if c.kind == "http":
        expected = int(c.expected or 200)
        try:
            with urllib.request.urlopen(c.target, timeout=15) as resp:
                ok = resp.status == expected
                return ok, f"http {resp.status} (expected {expected})"
        except urllib.error.HTTPError as exc:
            return exc.code == expected, f"http {exc.code} (expected {expected})"
        except Exception as exc:
            return False, f"http error: {exc}"
    if c.kind in ("assert", "policy", "ci", "review", "shard"):
        # Explicit callable or file/command check; non-executable bare prose fails closed.
        target_path = Path(c.target)
        if target_path.exists():
            return True, f"exists: {target_path}"
        return False, f"unverified {c.kind}: {c.target}"
    return False, f"unknown criterion kind: {c.kind}"


def verify_task(
    task_id: str,
    criteria: list[SuccessCriterion],
    *,
    cwd: Optional[Path] = None,
    verifier: str = "nougen-verify",
) -> dict[str, Any]:
    """Independent verifier: sole path that marks a task `done` (AT-02)."""
    validate_criteria(criteria)
    work_dir = cwd or Path.cwd()
    checks: list[dict[str, Any]] = []
    all_ok = True
    for c in criteria:
        ok, detail = _eval_criterion(c, work_dir)
        checks.append({"kind": c.kind, "target": c.target, "ok": ok, "detail": detail[:400]})
        if not ok:
            all_ok = False
    event = "verify_done" if all_ok else "verify_failed"
    append_ledger(task_id, event, {"verifier": verifier, "checks": checks})
    return {"task_id": task_id, "status": "done" if all_ok else "verify_failed", "checks": checks}


def run_relentless(
    task_id: str,
    owner: str,
    criteria: list[SuccessCriterion],
    step_fn: Callable[[int, str, str], tuple[bool, str, int]],
    *,
    repair_fn: Optional[Callable[[int, str, str], tuple[str, str]]] = None,
    recovery_fn: Optional[Callable[[str, str], str]] = None,
    budget: Optional[Budget] = None,
    cwd: Optional[Path] = None,
    initial_strategy: str = "baseline",
) -> dict[str, Any]:
    """Execute a bounded, relentless closed loop until verified done, killed, or tripped."""
    validate_criteria(criteria)
    cfg = budget or Budget()
    started = time.time()
    acquire_lease(task_id, owner)
    if not read_ledger(task_id) or current_status(task_id) == "new":
        append_ledger(task_id, "init", {"owner": owner, "criteria": [asdict(c) for c in criteria if c.fn is None]})

    strategy = initial_strategy
    strategy_hash = compute_strategy_hash(strategy)
    what_we_learned = "initial attempt"
    throttled_routes: set[str] = set()
    transient_retries = 0
    attempt_num = 0

    try:
        while True:
            route = select_free_route(throttled_routes)
            gate_state = check_budget(task_id, cfg, started_epoch=started)
            attempt_num += 1
            if attempt_num > 1 and what_we_learned != "transient retry":
                validate_retry_strategy(task_id, strategy_hash, what_we_learned)

            append_ledger(
                task_id,
                "attempt",
                {
                    "attempt": attempt_num,
                    "owner": owner,
                    "route": route,
                    "gate": gate_state,
                    "strategy_hash": strategy_hash,
                    "what_we_learned": what_we_learned,
                },
            )
            heartbeat(task_id, owner)
            ok, output, tokens = step_fn(attempt_num, route, strategy)
            check_budget(task_id, cfg, call_tokens=tokens, started_epoch=started)

            if ok:
                v = verify_task(task_id, criteria, cwd=cwd)
                if v["status"] == "done":
                    return {"status": "done", "attempts": attempt_num, "verify": v}
                output = json.dumps(v["checks"])

            fclass = classify_failure(output)
            append_ledger(
                task_id,
                "attempt_failed",
                {"attempt": attempt_num, "failure_class": fclass, "tokens": tokens, "output": output[:500]},
            )

            if fclass == "permanent":
                note = recovery_fn("permanent", output) if recovery_fn else "quarantined on permanent failure"
                append_ledger(task_id, "recovered", {"reason": "permanent", "note": note})
                return {"status": "aborted", "reason": "permanent", "attempts": attempt_num, "note": note}

            if fclass == "transient":
                transient_retries += 1
                if "429" in output:
                    throttled_routes.add(route)
                if transient_retries > cfg.max_transient_retries:
                    note = recovery_fn("transient_exhausted", output) if recovery_fn else "transient retries exhausted"
                    append_ledger(task_id, "aborted", {"reason": "transient_exhausted", "note": note})
                    return {"status": "aborted", "reason": "transient_exhausted", "attempts": attempt_num, "note": note}
                what_we_learned = "transient retry"
                continue

            # Deterministic failure: must change strategy_hash + record what_we_learned
            if repair_fn is None:
                note = recovery_fn("deterministic_no_repair", output) if recovery_fn else "deterministic failure without repair_fn"
                append_ledger(task_id, "aborted", {"reason": "deterministic_no_repair", "note": note})
                return {"status": "aborted", "reason": "deterministic_no_repair", "attempts": attempt_num, "note": note}
            new_strategy, learned = repair_fn(attempt_num, output, strategy_hash)
            strategy = new_strategy
            strategy_hash = compute_strategy_hash(new_strategy)
            what_we_learned = learned
    except (BudgetTrippedError, NoFreeRouteError, StrategyRepeatError) as exc:
        note = recovery_fn("breaker", str(exc)) if recovery_fn else str(exc)
        append_ledger(task_id, "aborted", {"reason": type(exc).__name__, "note": note})
        return {"status": "aborted", "reason": type(exc).__name__, "attempts": attempt_num, "note": note}
    finally:
        release_lease(task_id, owner)

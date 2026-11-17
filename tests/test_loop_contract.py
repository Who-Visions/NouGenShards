"""Acceptance tests AT-01..AT-12 for nougen_shards.loop_contract and relentless nougen_loop."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from nougen_shards import loop_contract as lc

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
import nougen_loop  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_loop_state(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NOUGEN_LOOP_STATE_DIR", str(state))
    monkeypatch.setenv("NOUGEN_LOOP_LEDGER_DIR", str(state / "loop_ledger"))
    monkeypatch.setenv("NOUGEN_LOOP_STOP", str(state / "LOOP_STOP"))
    return state


def test_at01_refuses_prose_only_goal():
    with pytest.raises(lc.ProseGoalError):
        lc.validate_criteria([])
    with pytest.raises(lc.ProseGoalError):
        lc.validate_criteria([lc.SuccessCriterion(kind="cmd", target="   ")])


def test_at02_only_verify_moves_to_done():
    c = [lc.SuccessCriterion(kind="assert", target="check", fn=lambda: (False, "still red"))]
    lc.append_ledger("t-verify", "init", {"owner": "lane-a"})
    lc.append_ledger("t-verify", "attempt", {"attempt": 1, "strategy_hash": "h1", "what_we_learned": "init"})
    assert lc.current_status("t-verify") == "open"
    res = lc.verify_task("t-verify", c)
    assert res["status"] == "verify_failed"
    assert lc.current_status("t-verify") == "verify_failed"

    c_ok = [lc.SuccessCriterion(kind="assert", target="check", fn=lambda: (True, "green"))]
    res2 = lc.verify_task("t-verify", c_ok)
    assert res2["status"] == "done"
    assert lc.current_status("t-verify") == "done"
    assert lc.verify_ledger_chain("t-verify")


def test_at03_refuses_repeated_strategy_or_empty_learning():
    lc.append_ledger("t-strat", "attempt", {"attempt": 1, "strategy_hash": "abc123", "what_we_learned": "initial"})
    with pytest.raises(lc.StrategyRepeatError):
        lc.validate_retry_strategy("t-strat", "abc123", "changed note")
    with pytest.raises(lc.StrategyRepeatError):
        lc.validate_retry_strategy("t-strat", "def456", "   ")
    lc.validate_retry_strategy("t-strat", "def456", "switched parser")


def test_at04_transient_429_retries_and_routes_fallback():
    seen_routes: list[str] = []

    def step(attempt: int, route: str, strategy: str):
        seen_routes.append(route)
        if attempt == 1:
            return False, "HTTP 429 rate_limit", 100
        return True, "ok", 100

    res = lc.run_relentless(
        "t-429",
        "lane-a",
        [lc.SuccessCriterion(kind="assert", target="ok", fn=lambda: (True, "pass"))],
        step,
        budget=lc.Budget(max_attempts=4, max_transient_retries=3),
    )
    assert res["status"] == "done"
    assert seen_routes == ["nvidia_nim_free", "openrouter_free"]


def test_at05_permanent_403_no_retry_straight_to_recovery():
    calls = {"n": 0, "recovered": False}

    def step(attempt: int, route: str, strategy: str):
        calls["n"] += 1
        return False, "HTTP 403 forbidden", 50

    def recover(kind: str, output: str) -> str:
        calls["recovered"] = True
        return f"rolled back after {kind}"

    res = lc.run_relentless(
        "t-403",
        "lane-a",
        [lc.SuccessCriterion(kind="assert", target="ok", fn=lambda: (True, "pass"))],
        step,
        recovery_fn=recover,
    )
    assert res["status"] == "aborted"
    assert res["reason"] == "permanent"
    assert calls == {"n": 1, "recovered": True}


def test_at06_at07_at08_lease_conflict_heartbeat_and_expiry():
    lc.acquire_lease("t-lease", "runner-1", ttl_s=60, now=1000.0)
    with pytest.raises(lc.LeaseConflictError):
        lc.acquire_lease("t-lease", "runner-2", ttl_s=60, now=1010.0)
    lc.heartbeat("t-lease", "runner-1", ttl_s=60, now=1050.0)
    # Still held at 1070 because heartbeat extended to 1110 (AT-08)
    with pytest.raises(lc.LeaseConflictError):
        lc.acquire_lease("t-lease", "runner-2", ttl_s=60, now=1070.0)
    # Expired after 1110 -> runner-2 can resume after crash (AT-06)
    lc.acquire_lease("t-lease", "runner-2", ttl_s=60, now=1115.0)
    lc.release_lease("t-lease", "runner-2")


def test_at09_call_ceiling_and_kill_switch_trip_breaker(isolated_loop_state):
    with pytest.raises(lc.BudgetTrippedError):
        lc.check_budget("t-cap", lc.Budget(), call_tokens=80_000)
    with pytest.raises(lc.BudgetTrippedError):
        lc.check_budget("t-cap", lc.Budget(), paid_usd=0.01)

    (isolated_loop_state / "LOOP_STOP").write_text("stop", encoding="utf-8")
    with pytest.raises(lc.BudgetTrippedError):
        lc.check_budget("t-cap", lc.Budget(), call_tokens=100)


def test_at10_no_free_route_fails_closed():
    with pytest.raises(lc.NoFreeRouteError):
        lc.select_free_route(set(lc.FREE_ROUTES))


def test_at11_at12_repair_loop_and_consecutive_failure_stop():
    state = {"fixed": False}

    def step(attempt: int, route: str, strategy: str):
        if not state["fixed"]:
            return False, "AssertionError: test_foo failed", 200
        return True, "green", 200

    def repair(attempt: int, output: str, prev_hash: str):
        state["fixed"] = True
        return f"fix-v{attempt}", "patched assertion root cause"

    res = lc.run_relentless(
        "t-repair",
        "lane-a",
        [lc.SuccessCriterion(kind="assert", target="x", fn=lambda: (state["fixed"], "ok" if state["fixed"] else "fail"))],
        step,
        repair_fn=repair,
        budget=lc.Budget(max_attempts=3),
    )
    assert res["status"] == "done"
    assert res["attempts"] == 2
    assert lc.verify_ledger_chain("t-repair")

    # AT-12: 3 consecutive same-class failures trip circuit breaker
    for i in range(1, 4):
        lc.append_ledger("t-trip", "attempt_failed", {"attempt": i, "failure_class": "deterministic"})
    with pytest.raises(lc.BudgetTrippedError):
        lc.check_budget("t-trip", lc.Budget(max_attempts=10, repeat_failure_stop=3))


def test_nougen_loop_relentless_repairs_then_passes(tmp_path):
    flag = tmp_path / "fixed.txt"
    verify_py = f'"{sys.executable}" -c "import pathlib,sys; sys.exit(0 if pathlib.Path({str(flag)!r}).exists() else 1)"'
    repair_py = f'"{sys.executable}" -c "import pathlib; pathlib.Path({str(flag)!r}).write_text(\'ok\')"'
    rc = nougen_loop.main([
        "--goal", "fix failing check relentlessly",
        "--repo", str(tmp_path),
        "--relentless",
        "--task-id", "cli-relentless-test",
        "--max-attempts", "3",
        "--verify-cmd", verify_py,
        "--repair-cmd", repair_py,
        "--skip", "recall", "harden", "commit", "pr", "shard", "dream", "evolve", "handoff",
    ])
    assert rc == 0
    assert flag.exists()
    assert lc.current_status("cli-relentless-test") == "done"

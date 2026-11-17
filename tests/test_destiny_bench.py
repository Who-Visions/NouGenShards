"""Regression tests for the destiny benchmark fault injection (evals/destiny_bench.py).

Covers the Codex P2 on #1105: route timeouts must be injected independently
of route health. The old code fired the injected ``RouteTimeout`` on whichever
route the reconciler tried first -- i.e. the first *healthy* route. Once the
first route was cooling down from an earlier injected timeout, the next
flagged task's timeout landed on the failover route instead, knocked out the
last healthy lane, and the task stranded in ``all_routes_down`` until a crash
advanced the bench clock. The Nov 17 bench run shows the same coupling in
production: only 11 of the 20 flagged tasks ever got a timeout injected.

The fixed code injects the timeout only on the first configured route, so a
flagged task attempted while that route cools down runs unfaulted on the
failover route, and only fired faults count as faulted.

The test runs ``run_arm`` offline with a stubbed lane: the stub answers every
task exactly, so any task that does not finish DONE is a fault-injection
failure, not a model miss. Eleven tasks give two flagged tasks with no crash
between them (tasks 5 and 10; the crash at task 3 clears the first route's
cooldown before task 5, then task 5's timeout cools it down again before
task 10): on old code task 10's timeout leaks onto the failover route and
the task never finishes; on new code it runs clean.
"""
import pytest

import evals.destiny_bench as destiny_bench
from evals.destiny_bench import build_world, run_arm


@pytest.fixture
def isolated_bench_env(monkeypatch, tmp_path):
    """run_arm overwrites these in os.environ and never restores them."""
    for name in ("NOUGEN_DESTINY_DB", "NOUGEN_RECONCILER_DB",
                 "NOUGEN_RECEIPTS_DIR", "NOUGEN_TENANT"):
        monkeypatch.setenv(name, str(tmp_path / name))


def _stub_chat(expected_by_goal):
    """A lane that always answers exactly: failures are the bench's, not the model's."""
    def fake_chat(model, system, user, max_tokens=2048, timeout=180.0):
        goal = user.split("Task: ", 1)[1].replace(
            "Break into the smallest steps, then solve: ", "")
        expected = expected_by_goal[goal]
        return {"text": f"```python\ndef answer():\n    return {expected!r}\n```",
                "tokens": 10, "prompt_tokens": 10}
    return fake_chat


def test_route_timeout_injected_on_first_route_only(monkeypatch, isolated_bench_env):
    """Timeouts fire on the first configured route only, never the failover route."""
    facts, tasks = build_world()
    tasks = tasks[:11]  # flagged: 0, 5, 10; crash: 3 (clears cooldown before 5)
    monkeypatch.setattr(
        destiny_bench, "chat",
        _stub_chat({t["goal"]: t["expected"] for t in tasks}))
    res = run_arm("no_memory", facts, tasks, log=lambda *a: None)

    # Task 10 is attempted while the first route cools down from task 5's
    # timeout: it must run unfaulted on the failover route and finish.
    assert res["done"] == len(tasks)
    assert res["faults_injected"]["route_timeout"] == 2  # tasks 0 and 5 only
    assert res["recovery_rate"] == 1.0
    assert res["faulted_tasks_lost"] == 0
    assert res["rollback_violations"] == 0

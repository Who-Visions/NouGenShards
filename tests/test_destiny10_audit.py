"""Destiny 10 audit: Rescue/Harm are exact from done_goals, bounds otherwise."""
import contextlib
import importlib.util
import io
import os

_spec = importlib.util.spec_from_file_location(
    "destiny10_audit", os.path.join(os.path.dirname(__file__), "..", "evals", "destiny10_audit.py"))
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)


def _row(goals=None, done=None):
    r = {"done": len(goals) if goals is not None else done, "tasks": 4, "tokens_total": 10,
         "tokens_per_success": 5, "faulted_done": 0, "faulted_tasks": 0,
         "rollback_violations": 0, "_file": "f.json"}
    if goals is not None:
        r["done_goals"] = goals
    return r


def _report(arms):
    audit.load = lambda: (arms, [])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        audit.main()
    return buf.getvalue()


def test_exact_rescue_and_harm_with_offsetting_outcomes():
    # equal totals (2 vs 2) but disjoint sets: the old bound said 0/0, truth is 2/2
    out = _report({"shards_first": {1: _row(["a", "b"])}, "no_memory": {1: _row(["c", "d"])},
                   "prompt_only": {1: _row(["a", "b"])}})
    assert "| 1 | no_memory | 2 | 2 | exact |" in out
    assert "| 1 | prompt_only | 0 | 0 | exact |" in out


def test_falls_back_to_bound_when_a_run_predates_done_goals():
    out = _report({"shards_first": {1: _row(["a", "b", "c"])}, "no_memory": {1: _row(done=1)},
                   "prompt_only": {1: _row(done=3)}})
    assert "| 1 | no_memory | at least 2 | at least 0 | bound from totals |" in out
    assert "bound from totals" in out and "rerun those arms" in out

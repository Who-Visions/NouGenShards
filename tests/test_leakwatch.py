"""leakwatch: retained-type detection, leak trace to a module root, fingerprint grouping."""
import sys
import types

from nougen_shards import leakwatch


class _Leaky:
    pass


class _Steady:
    pass


def _fake_module(name):
    mod = types.ModuleType(name)
    mod.REQUEST_LOG = []          # the classic leak: a module-level list nobody trims
    sys.modules[name] = mod
    return mod


def test_growing_type_is_retained_and_traced_to_its_module_global():
    mod = _fake_module("lw_fake_server")
    steady = [_Steady() for _ in range(300)]   # big but flat: must NOT be flagged
    w = leakwatch.LeakWatch(window=3, min_growth=100, top=3, trace_depth=6, log_path=None)
    try:
        for _ in range(3):
            mod.REQUEST_LOG.extend(_Leaky() for _ in range(150))   # "requests" that never get freed
            w.check()
        report = w.last_report
        types_flagged = [r["type"] for r in report["retained"]]
        key = f"{__name__}._Leaky"
        assert key in types_flagged
        assert f"{__name__}._Steady" not in types_flagged
        leak = next(item for item in report["leaks"] if item["type"] == key)
        assert leak["root"] == "module lw_fake_server . REQUEST_LOG"
        assert leak["trace"][-1].startswith("list[")
        assert leak["fingerprint"] and len(leak["fingerprint"]) == 12
        assert steady  # keep alive
    finally:
        sys.modules.pop("lw_fake_server", None)


def test_fingerprint_is_stable_across_instances_of_the_same_bug():
    mod = _fake_module("lw_fake_server2")
    try:
        w = leakwatch.LeakWatch(window=2, min_growth=10, trace_depth=6, log_path=None)
        mod.REQUEST_LOG.extend(_Leaky() for _ in range(20))
        a = w.leak_trace(f"{__name__}._Leaky")
        mod.REQUEST_LOG.extend(_Leaky() for _ in range(20))
        b = w.leak_trace(f"{__name__}._Leaky")
        assert a["fingerprint"] == b["fingerprint"]
    finally:
        sys.modules.pop("lw_fake_server2", None)


def test_not_retained_before_window_fills_and_off_by_default(monkeypatch):
    w = leakwatch.LeakWatch(window=4, min_growth=1, log_path=None)
    w.check()
    assert w.last_report["retained"] == []
    monkeypatch.delenv("NOUGEN_LEAKWATCH", raising=False)
    assert leakwatch.start_from_env() is None


def test_report_is_logged_as_jsonl(tmp_path):
    log = tmp_path / "lw.jsonl"
    w = leakwatch.LeakWatch(window=2, min_growth=1, log_path=log)
    w.check()
    w.check()
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2 and '"samples": 2' in lines[1]


def test_debug_routes_are_owner_gated_and_report(monkeypatch):
    import pytest as _pt
    _pt.importorskip("fastapi")
    _pt.importorskip("gradio")
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
    from fastapi.testclient import TestClient
    import app as node

    token = "leakwatch-owner-token"
    monkeypatch.setattr(node, "NODE_TOKEN", token)
    c = TestClient(node.app, raise_server_exceptions=False)
    assert c.get("/debug/leakwatch").status_code == 401
    h = {"X-NGS-Token": token}
    monkeypatch.setattr(leakwatch, "_instance", None)
    off = c.get("/debug/leakwatch", headers=h).json()
    assert off["enabled"] is False
    w = leakwatch.LeakWatch(window=2, min_growth=1, log_path=None)
    monkeypatch.setattr(leakwatch, "_instance", w)
    r = c.post("/debug/leakwatch/check", headers=h)
    assert r.status_code == 200 and r.json()["enabled"] is True
    assert c.get("/debug/leakwatch", headers=h).json()["report"]["samples"] == 1


def test_trace_respects_its_budget_instead_of_hanging():
    mod = _fake_module("lw_fake_budget")
    try:
        mod.REQUEST_LOG.extend(_Leaky() for _ in range(5))
        w = leakwatch.LeakWatch(trace_depth=10, trace_budget_calls=1, log_path=None)
        t = w.leak_trace(f"{__name__}._Leaky")
        assert t["root"] is None and "budget" in t["note"]
    finally:
        sys.modules.pop("lw_fake_budget", None)

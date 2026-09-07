"""reach_matrix names the answering node from /health fields and refuses to trust a run whose control row is not RED."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _module():
    path = Path(__file__).parents[1] / "tools" / "reach_matrix.py"
    spec = importlib.util.spec_from_file_location("reach_matrix", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


SIGS = [
    {"node": "fleet-store", "persistent_storage": True, "storage": "/data"},
    {"node": "blade-local", "persistent_storage": False, "storage_endswith": ".nougen"},
]


def test_answering_node_reads_health_fields_not_hostname():
    m = _module()
    assert m.answering_node(json.dumps({"storage": "/data", "persistent_storage": True}), SIGS) == "fleet-store"
    assert m.answering_node(json.dumps({"storage": "C:\\x\\.nougen", "persistent_storage": False}), SIGS) == "blade-local"
    assert m.answering_node("not json", SIGS) == "unknown"
    assert m.answering_node(json.dumps({"status": "ignited"}), SIGS) == "unknown"


def test_false_green_is_amber_when_expected_node_differs():
    m = _module()
    surface = {"name": "blade", "kind": "http", "target": "x", "expect": {"status": [200], "node": "blade-local"}}
    state, node, note = m.classify(surface, 200, json.dumps({"storage": "/data", "persistent_storage": True}), None, SIGS)
    assert state == "AMBER" and node == "fleet-store" and "false-green" in note


def test_no_answer_is_red_and_unexpected_status_is_amber():
    m = _module()
    surface = {"name": "s", "kind": "http", "target": "x", "expect": {"status": [200]}}
    assert m.classify(surface, None, "", "URLError: dns", SIGS)[0] == "RED"
    assert m.classify(surface, 530, "", None, SIGS)[0] == "AMBER"
    assert m.classify(surface, 200, "{}", None, SIGS)[0] == "GREEN"


def test_control_row_not_red_marks_every_green_untrusted(monkeypatch):
    m = _module()
    manifest = {"node_signatures": SIGS, "surfaces": [
        {"name": "live", "kind": "http", "target": "https://a/health", "expect": {"status": [200]}},
        {"name": "control", "kind": "control", "target": "https://dead.invalid/", "expect": {"status": [200]}},
    ]}
    monkeypatch.setattr(m, "http", lambda url, *a, **k: (200, "{}", None))  # even the dead host "answers"
    res = m.run(manifest, None, here="blade")
    assert res["control_ok"] is False and res["exit"] == 2
    assert [r["state"] for r in res["rows"]] == ["UNTRUSTED", "GREEN"]


def test_control_row_red_lets_green_stand_and_skips_search_without_token(monkeypatch):
    m = _module()
    manifest = {"node_signatures": SIGS, "surfaces": [
        {"name": "live", "kind": "http", "target": "https://a/health", "expect": {"status": [200]}},
        {"name": "search", "kind": "search", "target": "https://a/search", "expect": {"status": [200]}},
        {"name": "control", "kind": "control", "target": "https://dead.invalid/", "expect": {"status": [200]}},
    ]}
    monkeypatch.setattr(m, "http", lambda url, *a, **k: (None, "", "URLError: dns") if "invalid" in url else (200, "{}", None))
    res = m.run(manifest, None, here="phoebus")
    assert res["control_ok"] is True and res["exit"] == 0
    assert [r["state"] for r in res["rows"]] == ["GREEN", "SKIPPED", "RED"]


def test_expand_resolves_env_with_default(monkeypatch):
    m = _module()
    monkeypatch.delenv("NGS_PORT", raising=False)
    assert m.expand("http://127.0.0.1:${NGS_PORT:-4444}/health") == "http://127.0.0.1:4444/health"
    monkeypatch.setenv("NGS_PORT", "5555")
    assert m.expand("http://127.0.0.1:${NGS_PORT:-4444}/health") == "http://127.0.0.1:5555/health"


def test_row_carries_token_fp_for_authenticated_surface():
    m = _module()
    surface = {"name": "search", "kind": "search", "target": "https://a/search"}
    row = m.probe(surface, SIGS, token="mock_token_fixture", here="whoart")
    assert row["token_fp"] is not None
    assert len(row["token_fp"]) == 12


def test_reconcile_vantages_asserts_combo_breaker_on_shared_credential():
    m = _module()
    import hashlib
    fp_a = hashlib.sha256(b"probe_alpha").hexdigest()[:12]
    fp_b = hashlib.sha256(b"probe_beta").hexdigest()[:12]

    run_whoart = {"vantage": "whoart", "token_fp": fp_a}
    run_blade = {"vantage": "blade", "token_fp": fp_a}
    run_phoebus = {"vantage": "phoebus", "token_fp": fp_a}

    # All three vantages sharing the same credential collapse to 1 observation -> COMBO BREAKER
    rec = m.reconcile_vantages([run_whoart, run_blade, run_phoebus])
    assert rec["verdict"] == "COMBO BREAKER"
    assert rec["announcer_call"] == "COMBO BREAKER"
    assert rec["independent_observations"] == 1

    # Distinct credentials corroborate -> GODLIKE
    run_blade_distinct = {"vantage": "blade", "token_fp": fp_b}
    rec_distinct = m.reconcile_vantages([run_whoart, run_blade_distinct])
    assert rec_distinct["verdict"] == "CORROBORATED"
    assert rec_distinct["announcer_call"] == "GODLIKE"
    assert rec_distinct["independent_observations"] == 2

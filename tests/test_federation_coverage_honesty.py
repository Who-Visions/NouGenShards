"""Recall must never go blind: a degraded sweep cannot look like an empty one.

`federated_retrieve` fans out to four lanes and merges what comes back. Every
failure path -- a lane raising, a lane missing the shared deadline -- used to
collapse to `[]` with nothing but a log line, and the merged result was a bare
list. So the caller could not tell "nothing matched" from "three of four lanes
failed", and an agent instructed to recall before reasoning would read the empty
list as absence and reason from scratch.

Measured consequence, 2026-09-04: every federated search through the gateway
returned `complete: false` with one node timed out, for six hours, and nobody
was told -- the incompleteness was in the envelope but nothing surfaced it.

These tests pin the property that makes that impossible: **a lane that did not
report is visible to whoever asked.**
"""

from __future__ import annotations

import pytest

from nougen_shards import federation


@pytest.fixture(autouse=True)
def _isolate_lanes(monkeypatch):
    """Owner tenant with no external/cloud/vault configs, so only 'local' runs.

    Each test then breaks exactly the lane it is about.
    """
    monkeypatch.setattr(federation.core, "active_tenant_id", lambda: "owner")
    monkeypatch.setattr(federation.keymaker, "list_external_dbs", lambda: [])
    monkeypatch.setattr(federation.keymaker, "list_cloud_nodes", lambda: [])
    monkeypatch.setattr(federation.keymaker, "list_local_vaults", lambda: [])


def test_clean_sweep_reports_complete(monkeypatch):
    monkeypatch.setattr(federation.core, "retrieve",
                        lambda *a, **k: [{"id": 1, "title": "hit"}])
    out = federation.federated_retrieve("q", limit=3)
    assert out.complete is True
    assert out.lane_failures == []


def test_empty_corpus_is_still_complete(monkeypatch):
    """A genuinely empty result is COMPLETE. This is the control."""
    monkeypatch.setattr(federation.core, "retrieve", lambda *a, **k: [])
    out = federation.federated_retrieve("q", limit=3)
    assert list(out) == []
    assert out.complete is True


def test_failed_lane_is_not_complete_even_though_it_looks_empty(monkeypatch):
    """The whole point: same empty list, different truth."""
    def boom(*a, **k):
        raise RuntimeError("db locked")
    monkeypatch.setattr(federation.core, "retrieve", boom)

    out = federation.federated_retrieve("q", limit=3)

    assert list(out) == []          # indistinguishable by content...
    assert out.complete is False    # ...but NOT by coverage
    assert len(out.lane_failures) == 1
    assert out.lane_failures[0]["store"] == "lane:local"
    assert "RuntimeError" in out.lane_failures[0]["error"]
    assert "db locked" in out.lane_failures[0]["error"]


def test_failure_reaches_sweep_report_for_the_http_trailer(monkeypatch):
    """/search renders sweep_report['errored'] as a FEDERATION_STATUS trailer.

    Recording into that existing contract is what makes the hole visible over
    HTTP without touching the endpoint.
    """
    def boom(*a, **k):
        raise ValueError("corrupt index")
    monkeypatch.setattr(federation.core, "retrieve", boom)

    report: dict = {}
    federation.federated_retrieve("q", limit=3, sweep_report=report)

    assert [e["store"] for e in report["errored"]] == ["lane:local"]
    assert "corrupt index" in report["errored"][0]["error"]


def test_clean_sweep_leaves_sweep_report_untouched(monkeypatch):
    """The common path must be unchanged: no trailer on a healthy sweep."""
    monkeypatch.setattr(federation.core, "retrieve", lambda *a, **k: [])
    report: dict = {}
    federation.federated_retrieve("q", limit=3, sweep_report=report)
    assert "errored" not in report


def test_deadline_miss_is_reported_not_just_logged(monkeypatch):
    """A lane that overruns the shared deadline is a hole, not an empty lane."""
    import time

    monkeypatch.setenv("NOUGEN_RECALL_DEADLINE_S", "0.2")

    def slow(*a, **k):
        time.sleep(5)
        return [{"id": 1}]
    monkeypatch.setattr(federation.core, "retrieve", slow)

    out = federation.federated_retrieve("q", limit=3)

    assert out.complete is False
    assert out.lane_failures[0]["store"] == "lane:local"
    assert "deadline" in out.lane_failures[0]["error"]


def test_result_is_still_an_ordinary_list_for_existing_callers(monkeypatch):
    """Backward compatibility: cli, rhea_noir and shadow_xoah iterate/slice it.

    Deliberately does NOT assert a row count -- rank fusion decides that, and
    pinning it here would make this test fail for reasons unrelated to the
    property it guards.
    """
    rows = [{"id": i, "title": f"shard {i}", "content": f"body {i}"}
            for i in range(5)]
    monkeypatch.setattr(federation.core, "retrieve", lambda *a, **k: rows)

    out = federation.federated_retrieve("q", limit=5)

    assert isinstance(out, list)
    assert len(out) >= 1
    assert all(isinstance(r, dict) for r in out)
    assert isinstance(out[:2], list)       # slicing works (returns a plain list)
    assert list(iter(out)) == list(out)    # iteration works
    assert out.complete is True            # and it was a clean sweep


def test_complete_is_never_inferred_from_length(monkeypatch):
    """A degraded sweep that still returns rows must report incomplete.

    The dangerous case is not the empty one -- it is the sweep that returns
    plausible rows from the lanes that survived, which reads as a successful
    recall while a whole corpus is missing.
    """
    monkeypatch.setattr(federation.keymaker, "list_local_vaults",
                        lambda: [{"name": "sibling"}])

    def vault_boom(*a, **k):
        raise OSError("vault unreachable")
    monkeypatch.setattr(federation, "query_local_vaults", vault_boom)
    monkeypatch.setattr(federation.core, "retrieve",
                        lambda *a, **k: [{"id": 1, "title": "a real hit"}])

    out = federation.federated_retrieve("q", limit=3)

    assert len(out) == 1          # rows came back
    assert out.complete is False  # and it is STILL not a complete answer
    assert out.lane_failures[0]["store"] == "lane:vaults"

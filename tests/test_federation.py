"""Federation resilience: local results must survive remote source failures."""
from nougen_shards import federation


LOCAL = [{"id": "local_1", "title": "Local Shard", "final_score": 0.9}]


def _patch_local(monkeypatch):
    """Stub local retrieval + keymaker so both remote lanes are exercised."""
    monkeypatch.setattr(federation.core, "retrieve", lambda *a, **k: list(LOCAL))
    monkeypatch.setattr(
        federation.core,
        "reciprocal_rank_fusion",
        lambda lists, k=60, weights=None: [s for sub in lists for s in sub],
    )
    monkeypatch.setattr(federation.keymaker, "list_external_dbs",
                        lambda: [{"id": 1, "name": "ext"}])
    monkeypatch.setattr(federation.keymaker, "list_cloud_nodes",
                        lambda: [{"id": 1, "name": "cloud"}])


def test_external_failure_preserves_local(monkeypatch, caplog):
    _patch_local(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("external DB down")

    monkeypatch.setattr(federation, "query_external_dbs", boom)
    monkeypatch.setattr(federation, "query_cloud_shards", lambda *a, **k: [])

    results = federation.federated_retrieve("q", limit=5)
    assert any(r["id"] == "local_1" for r in results)


def test_cloud_failure_preserves_local(monkeypatch, caplog):
    _patch_local(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("cloud node unreachable")

    monkeypatch.setattr(federation, "query_external_dbs", lambda *a, **k: [])
    monkeypatch.setattr(federation, "query_cloud_shards", boom)

    results = federation.federated_retrieve("q", limit=5)
    assert any(r["id"] == "local_1" for r in results)


def test_both_remotes_fail_local_survives(monkeypatch):
    _patch_local(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("remote down")

    monkeypatch.setattr(federation, "query_external_dbs", boom)
    monkeypatch.setattr(federation, "query_cloud_shards", boom)

    results = federation.federated_retrieve("q", limit=5)
    assert [r["id"] for r in results] == ["local_1"]


def test_a_lane_that_misses_the_deadline_is_recorded_not_silent(monkeypatch):
    """A skipped lane must be observable to the caller, not only to our logs.

    Measured on phoebus 2026-09-04: a recall that overran
    NOUGEN_RECALL_DEADLINE_S returned HTTP 200 with a 2-byte body. The lane
    timeout was caught, logged, and converted to that lane's empty default,
    which merges exactly like a lane that genuinely matched nothing. Status
    said healthy, latency said slow, and nothing anywhere said "this answer is
    missing shards" - silent recall loss no caller could detect in principle.

    The per-store layer already got this right (a timed-out store is reported
    errored, never silently skipped); this is the same rule one level up.
    """
    _patch_local(monkeypatch)
    monkeypatch.setenv("NOUGEN_RECALL_DEADLINE_S", "0.15")

    import time

    def slow(*a, **k):
        time.sleep(5)
        return []

    monkeypatch.setattr(federation, "query_external_dbs", slow)
    monkeypatch.setattr(federation, "query_cloud_shards", slow)

    report = {}
    federation.federated_retrieve("q", limit=5, sweep_report=report)

    assert report.get("deadline_exceeded") is True
    assert report.get("deadline_s") == 0.15
    # The lanes that were dropped are named, so a caller can say which corpus
    # is missing rather than only that something is.
    assert set(report.get("lanes_timed_out", [])) & {"external", "cloud"}


def test_no_deadline_key_is_set_when_every_lane_answers(monkeypatch):
    """The flag must mean something. Setting it unconditionally would make a
    healthy recall indistinguishable from a degraded one all over again."""
    _patch_local(monkeypatch)
    monkeypatch.setattr(federation, "query_external_dbs", lambda *a, **k: [])
    monkeypatch.setattr(federation, "query_cloud_shards", lambda *a, **k: [])

    report = {}
    federation.federated_retrieve("q", limit=5, sweep_report=report)

    assert "deadline_exceeded" not in report
    assert "lanes_timed_out" not in report


def test_sweep_report_stays_optional(monkeypatch):
    """Every existing caller passes nothing; a missing report must not raise."""
    _patch_local(monkeypatch)
    monkeypatch.setenv("NOUGEN_RECALL_DEADLINE_S", "0.15")

    import time

    def slow(*a, **k):
        time.sleep(5)
        return []

    monkeypatch.setattr(federation, "query_external_dbs", slow)
    monkeypatch.setattr(federation, "query_cloud_shards", slow)

    results = federation.federated_retrieve("q", limit=5)
    assert any(r["id"] == "local_1" for r in results)

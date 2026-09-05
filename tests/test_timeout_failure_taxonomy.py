"""A no-response timeout must remain distinguishable from auth failure."""

import socket
import urllib.error

from nougen_shards import federation
from nougen_shards.connectors import cloud


def test_cloud_timeout_is_reported_as_transport_not_auth(monkeypatch):
    report = {}
    monkeypatch.setattr(
        cloud, "_open_cloud",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            urllib.error.URLError(socket.timeout("timed out"))))

    rows = cloud.query_cloud_shards(
        "probe", [{"id": "p", "name": "phoebus", "url": "https://example.com"}],
        sweep_report=report,
    )

    assert rows == []
    assert report["errored"][0]["store"] == "cloud:phoebus"
    assert report["errored"][0]["failure_class"] == "transport_timeout"


def test_http_failure_class_header_is_preserved():
    error = urllib.error.HTTPError(
        "https://example.com", 503, "busy",
        {"X-NouGen-Failure-Class": "local_resource_exhaustion"}, None,
    )
    assert cloud._failure_class(error) == "local_resource_exhaustion"


def test_federation_deadline_surfaces_transport_timeout(monkeypatch):
    class TimedOut:
        def result(self, timeout=None):
            raise federation.concurrent.futures.TimeoutError

        def cancel(self):
            return True

    class Executor:
        def submit(self, *_args, **_kwargs):
            return TimedOut()

    monkeypatch.setattr(federation, "_lane_executor", lambda: Executor())
    monkeypatch.setattr(federation.keymaker, "list_external_dbs", lambda: [])
    monkeypatch.setattr(federation.keymaker, "list_cloud_nodes", lambda: [])
    monkeypatch.setattr(federation.keymaker, "list_local_vaults", lambda: [])
    monkeypatch.setenv("NOUGEN_RECALL_DEADLINE_S", "0.1")
    report = {}

    assert federation.federated_retrieve("probe", sweep_report=report) == []
    assert report["errored"]
    assert {entry["failure_class"] for entry in report["errored"]} == {
        "transport_timeout"
    }

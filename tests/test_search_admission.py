"""Over the concurrency cap, /search answers from the fast local lane at once (200, X-NouGen-Busy)
instead of queueing behind full recalls until every caller misses the deadline (WhoArt 2026-11-13)."""
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("gradio")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _client(monkeypatch, seen):
    import app as node
    from fastapi.testclient import TestClient
    from nougen_shards import core
    monkeypatch.setattr(node, "NODE_TOKEN", "tok")

    def fake_fed(query, limit=3, sweep_report=None, **kw):
        seen.append(core.FAST_LOCAL.get())
        return []
    monkeypatch.setattr(node, "federated_retrieve", fake_fed)
    return node, TestClient(node.app, raise_server_exceptions=False)


def test_admitted_search_runs_full_recall(monkeypatch):
    seen = []
    node, c = _client(monkeypatch, seen)
    r = c.post("/search", json={"query": "x", "limit": 3}, headers={"X-NGS-Token": "tok"})
    assert r.status_code == 200 and "X-NouGen-Busy" not in r.headers
    assert seen == [False]


def test_saturated_search_is_served_fast_not_queued(monkeypatch):
    seen = []
    node, c = _client(monkeypatch, seen)
    monkeypatch.setenv("NOUGEN_SEARCH_QUEUE_S", "0")
    held = 0
    while node._SEARCH_SLOTS.acquire(blocking=False):
        held += 1
    try:
        r = c.post("/search", json={"query": "x", "limit": 3}, headers={"X-NGS-Token": "tok"})
    finally:
        for _ in range(held):
            node._SEARCH_SLOTS.release()
    assert r.status_code == 200 and r.headers.get("X-NouGen-Busy") == "1"
    assert seen == [True]


def test_slot_is_released_after_each_search(monkeypatch):
    seen = []
    node, c = _client(monkeypatch, seen)
    for _ in range(10):
        c.post("/search", json={"query": "x"}, headers={"X-NGS-Token": "tok"})
    assert seen == [False] * 10

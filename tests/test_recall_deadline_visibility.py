"""A timed-out recall must never be indistinguishable from an empty substrate.

Measured on phoebus 2026-09-04, against the live node: 1 query in 10 came back
``HTTP 200`` with a 2-byte body (``[]``) after 24.5s, while the other 9 returned
real shards. Nothing in the status line, the body, or the headers said which of
the two had happened. PR #208 made the federation layer *record* the dropped
lane; these tests cover the half that makes the record reach a caller, because
a field nobody reads fixes nothing.

The invariant under test is not "recall is fast". It is: **absence in a result
set must never be reported as absence in the substrate unless the sweep
actually finished.**
"""
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("gradio")

from fastapi.testclient import TestClient  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as node  # noqa: E402
from nougen_shards import mcp as shards_mcp  # noqa: E402

TOKEN = "deadline-visibility-token"
DROPPED = {"lanes_timed_out": ["local", "cloud"], "deadline_s": 20.0,
           "deadline_exceeded": True}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(node, "NODE_TOKEN", TOKEN)
    return TestClient(node.app)


def _stub_retrieve(rows, report):
    def _fake(query, limit=3, query_embedding=None, domain_key=None, sweep_report=None):
        if sweep_report is not None:
            sweep_report.update(report)
        return list(rows)
    return _fake


def test_timed_out_empty_search_is_not_reported_as_no_matches(client, monkeypatch):
    """The exact production shape: every lane dropped, zero rows to show."""
    monkeypatch.setattr(node, "federated_retrieve", _stub_retrieve([], DROPPED))
    r = client.post("/search", json={"query": "anything", "limit": 3},
                    headers={"X-NGS-Token": TOKEN})
    assert r.status_code == 200

    # The body must not be byte-identical to a genuine empty result.
    body = r.json()
    assert body != [], "a timed-out sweep still returns a bare [] — the defect"
    trailer = body[-1]
    assert trailer["event_type"] == "FEDERATION_STATUS"
    assert "INCOMPLETE" in trailer["title"]
    detail = json.loads(trailer["content"])
    assert detail["lanes_timed_out"] == ["local", "cloud"]
    assert detail["deadline_exceeded"] is True

    # And for clients that read the envelope rather than the rows.
    assert r.headers["X-NouGen-Degraded"] == "1"
    assert r.headers["X-NouGen-Lanes-Timed-Out"] == "local,cloud"


def test_partial_answer_is_flagged_too(client, monkeypatch):
    """A partial answer that looks whole is the same defect with camouflage."""
    row = {"id": 7, "title": "t", "content": "c", "final_score": 1.0,
           "_db_index": 1, "utility_score": 0}
    monkeypatch.setattr(node, "federated_retrieve", _stub_retrieve([row], DROPPED))
    r = client.post("/search", json={"query": "q", "limit": 3},
                    headers={"X-NGS-Token": TOKEN})
    body = r.json()
    assert body[0]["id"] == 7, "real rows still ship first"
    assert body[-1]["event_type"] == "FEDERATION_STATUS"
    assert r.headers["X-NouGen-Degraded"] == "1"


def test_clean_sweep_is_unchanged(client, monkeypatch):
    """The marker must mean something: a healthy empty recall stays a bare []
    with no degraded headers, or callers learn to ignore it."""
    monkeypatch.setattr(node, "federated_retrieve", _stub_retrieve([], {}))
    r = client.post("/search", json={"query": "q", "limit": 3},
                    headers={"X-NGS-Token": TOKEN})
    assert r.json() == []
    assert "X-NouGen-Degraded" not in r.headers
    assert "X-NouGen-Lanes-Timed-Out" not in r.headers


def test_node_mcp_recall_lane_carries_the_marker(monkeypatch):
    """The connector lane, not just REST: this is how the fleet recalls."""
    monkeypatch.setattr(node, "federated_retrieve", _stub_retrieve([], DROPPED))
    out = node.recall_memory.fn("q", limit=5) if hasattr(node.recall_memory, "fn") \
        else node.recall_memory("q", limit=5)
    assert out and out[-1]["event_type"] == "FEDERATION_STATUS"


def test_shards_mcp_recall_refuses_to_claim_an_empty_substrate(monkeypatch):
    """nougen_shards.mcp.recall_memory used to answer 'No relevant shards found
    in the memory substrate' — a positive claim the substrate never made."""
    monkeypatch.setattr(shards_mcp, "federated_retrieve", _stub_retrieve([], DROPPED))
    fn = getattr(shards_mcp.recall_memory, "fn", shards_mcp.recall_memory)
    answer = fn("q", limit=3)
    assert "No relevant shards found" not in answer
    assert "INCOMPLETE" in answer
    assert "local" in answer and "cloud" in answer


def test_shards_mcp_recall_still_says_empty_when_the_sweep_finished(monkeypatch):
    monkeypatch.setattr(shards_mcp, "federated_retrieve", _stub_retrieve([], {}))
    fn = getattr(shards_mcp.recall_memory, "fn", shards_mcp.recall_memory)
    assert "No relevant shards found" in fn("q", limit=3)

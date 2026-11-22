"""The top-level ``delivered`` flag must not claim delivery that no lane verified."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


@pytest.fixture()
def node(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_NODE_NAME", "whoart")
    monkeypatch.setenv("NOUGEN_AGY_INBOX", str(tmp_path / "inbox"))
    monkeypatch.setenv("NOUGEN_MSG_STATE", str(tmp_path / "state.json"))
    for name in [m for m in sys.modules if m.startswith(("nougenmsg_node", "_agy_live"))]:
        del sys.modules[name]
    return importlib.import_module("nougenmsg_node")


# Shape observed live on 2026-11-22: every lane unverified, yet delivered:true.
UNVERIFIED = {"phoebus": {
    "claude_pipes": {"delivered": [], "registered": 0, "delivery_verified": False},
    "antigravity": {"status": "dropped", "pipe_delivered": False},
    "codex": {"queue_accepted": False, "delivery_verified": False,
              "error": "queue cannot contain more than 100 submissions"},
}}


def test_all_lanes_unverified_is_not_delivered(node):
    body = node._receipt({"delivered": True, "routed": True, "results": UNVERIFIED})
    assert body["delivered"] is False
    assert body["routed"] is True
    assert body["status"] == "unverified"
    assert body["delivery_verified"] is False


def test_one_verified_lane_is_delivered(node):
    res = {"phoebus": dict(UNVERIFIED["phoebus"],
                           claude_pipes={"delivered": ["4936"], "delivery_verified": True})}
    body = node._receipt({"delivered": True, "routed": True, "results": res})
    assert body["delivered"] is True
    assert body["delivery_verified"] is True
    assert "status" not in body


def test_no_lane_reports_stays_unknown(node):
    body = node._receipt({"delivered": True, "routed": True, "results": {"queued": "background"}})
    assert body["delivered"] is True
    assert body["delivery_verified"] is None
    assert body["status"] == "queued"


def test_queue_accepted_alone_is_not_verified(node):
    res = {"phoebus": {"codex": {"queue_accepted": True, "delivery_verified": False}}}
    body = node._receipt({"delivered": True, "routed": True, "results": res})
    assert body["delivered"] is False and body["status"] == "queued"


def test_foreign_dispatch_uses_honest_flag(node, monkeypatch):
    class Bus:
        @staticmethod
        def emit_node(**_kw):
            return UNVERIFIED

    monkeypatch.setattr(node, "_get_fleet_bus", lambda: Bus)
    msg = {"target": "@phoebus", "text": "hi", "message_id": "m1", "sender": "t"}
    status, body = node._dispatch_foreign_target(msg, ("phoebus", "claude"))
    assert status == 200
    assert body["delivered"] is False and body["status"] == "unverified"


def test_queue_only_receipt_says_queued_not_unverified(node):
    body = node._receipt({"delivered": True, "routed": True,
                       "results": {"codex": {"queue_accepted": True}}})
    assert body["delivered"] is False
    assert body["delivery_verified"] is False
    assert body["status"] == "queued"


def test_nested_unrelated_keys_do_not_count_as_lane_verdicts(node):
    results = {"antigravity": {"pipe_delivered": False,
                               "meta": {"delivered": ["x"], "pipe_delivered": True}}}
    assert node._lanes_verified(results) is False

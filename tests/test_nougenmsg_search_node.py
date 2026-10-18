"""nougenmsg read path must not depend on a node-label helper that does not exist on machine.

Relay 20261013T104414: nougenmsg_search failed for every query. _nougenmsg_read looked up
get_current_node on the machine module, but it lives in nougen_shards.nougenmsg, so every
read raised AttributeError after the inbox was scanned.
"""
import json

import pytest

import app


@pytest.fixture
def inbox(tmp_path, monkeypatch):
    msg = {
        "message_id": "m-1",
        "sender": "blade",
        "target": "phoebus",
        "text": "relay check for the search tool",
        "timestamp": "2026-10-13T10:00:00Z",
    }
    (tmp_path / "m-1.json").write_text(json.dumps(msg), encoding="utf-8")
    monkeypatch.setattr(app, "_nougenmsg_inbox_dirs", lambda: [str(tmp_path)])
    monkeypatch.delenv("NOUGEN_NODE_NAME", raising=False)
    return tmp_path


def test_read_returns_messages_and_a_node_label(inbox):
    res = app._nougenmsg_read(None, limit=5)
    assert res["complete"] is True
    assert res["returned"] == 1
    assert res["messages"][0]["body"].startswith("relay check")
    assert isinstance(res["node"], str) and res["node"]


def test_env_node_name_overrides_the_helper(inbox, monkeypatch):
    monkeypatch.setenv("NOUGEN_NODE_NAME", "phoebus-test")
    assert app._nougenmsg_read(None, limit=5)["node"] == "phoebus-test"


def test_missing_helper_falls_back_instead_of_raising(inbox, monkeypatch):
    import nougen_shards.nougenmsg as bus

    def boom():
        raise RuntimeError("bus unavailable")

    monkeypatch.setattr(bus, "get_current_node", boom)
    res = app._nougenmsg_read(None, limit=5)
    assert res["node"] == "unknown"
    assert res["returned"] == 1

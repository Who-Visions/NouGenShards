"""The node's destiny MCP wrappers must call destiny.* with its real signatures.

create_destiny passed required=/forbidden=/variance= and update_destiny passed
status=, none of which destiny.py accepts, so every call raised TypeError and the
MCP tool was unusable. tests/test_mcp_destiny_nougenmsg.py covers a different
module (nougen_shards.mcp), not these wrappers.
"""
import app


def _call(tool, **kw):
    return app._unwrap_sync(tool)(**kw)


def test_create_and_update_destiny_through_the_node_wrappers(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_DESTINY_DB", str(tmp_path / "d.db"))
    made = _call(app.create_destiny, title="Morph: example", goal="Turn the page into shards",
                 trigger="url:https://example.com", required="shards captured",
                 forbidden="stale copy", variance="none", verification="shards linked")
    assert "error" not in made, made
    assert made["status"] == "dormant"
    did = made["id"]
    upd = _call(app.update_destiny, destiny_id=did, status="active", actor="test", evidence="started")
    assert "error" not in upd, upd
    assert upd["status"] == "active"


def test_update_destiny_still_rejects_an_illegal_transition(tmp_path, monkeypatch):
    # negative control: the wrapper must surface destiny.py's own refusal, not mask it
    monkeypatch.setenv("NOUGEN_DESTINY_DB", str(tmp_path / "d.db"))
    did = _call(app.create_destiny, title="Another one", goal="Reach a state")["id"]
    out = _call(app.update_destiny, destiny_id=did, status="not-a-status")
    assert "error" in out

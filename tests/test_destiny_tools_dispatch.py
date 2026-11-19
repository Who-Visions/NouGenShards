"""The destiny tools the node lists must answer through the node's MCP dispatch.

The fleet connector forwards a destiny call to the node as MCP ``tools/call``, so
these tests go through ``app.node_mcp.call_tool`` and never call the Python
functions directly. ``search_destinies`` used to ignore its query and return every
active destiny; the round trip here would not have caught that, test 3 does.
"""
import asyncio
import json
import os

import app
import pytest
from nougen_shards import core, destiny


def _call(name: str, **args) -> dict:
    result = asyncio.run(app.node_mcp.call_tool(name, args))
    assert not result.is_error, f"tool {name} returned error: {result}"
    return json.loads(result.content[0].text)


@pytest.fixture(autouse=True)
def _env_db(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_DESTINY_DB", str(tmp_path / "destinies.db"))


def test_listed_destiny_tools_all_dispatch():
    """Every destiny tool the node lists answers through tools/call."""
    tools = asyncio.run(app.node_mcp.list_tools())
    names = {t.name for t in tools}
    expected = {
        "unfinished_destinies",
        "create_destiny",
        "get_destiny",
        "update_destiny",
        "link_destiny",
        "search_destinies",
    }
    assert expected.issubset(names)

    created = _call(
        "create_destiny",
        title="Probe",
        goal="Check dispatch",
        trigger="manual",
        required="",
        forbidden="",
        verification="done",
        actor="tester",
    )
    did = created["id"]

    _call("unfinished_destinies")
    _call("get_destiny", destiny_id=did)
    _call("update_destiny", destiny_id=did, status="active", actor="tester", evidence="go")
    _call("link_destiny", destiny_id=did, kind="shard", ref="1@db", role="evidence", note="x")
    _call("search_destinies", query="Probe")


def test_create_get_update_link_round_trip(tmp_path):
    """Create, get, update and link through dispatch, against the temporary store."""
    created = _call(
        "create_destiny",
        title="Round trip",
        goal="Full cycle",
        trigger="start",
        required="a;b",
        forbidden="x;y",
        verification="check",
        actor="operator",
    )
    assert created["status"] == "dormant"
    assert created["required_events"] == ["a", "b"]
    assert created["forbidden_outcomes"] == ["x", "y"]
    did = created["id"]

    got = _call("get_destiny", destiny_id=did)
    assert got["title"] == "Round trip"
    assert got["status"] == "dormant"
    assert len(got["events"]) == 1
    assert got["events"][0]["from_status"] is None
    assert got["events"][0]["to_status"] == "dormant"
    assert got["events"][0]["actor"] == "operator"

    upd = _call("update_destiny", destiny_id=did, status="active", actor="operator", evidence="begin")
    assert upd["status"] == "active"

    linked = _call("link_destiny", destiny_id=did, kind="shard", ref="123@db1", role="evidence", note="linked")
    assert linked["id"] == did
    assert any(lk["ref"] == "123@db1" and lk["kind"] == "shard" for lk in linked["links"])

    got2 = _call("get_destiny", destiny_id=did)
    assert got2["status"] == "active"
    assert any(lk["ref"] == "123@db1" and lk["note"] == "linked" for lk in got2["links"])
    ev = [e for e in got2["events"] if e["to_status"] == "active"]
    assert ev and ev[0]["from_status"] == "dormant" and ev[0]["actor"] == "operator"

    done = _call("update_destiny", destiny_id=did, status="fulfilled", actor="operator", evidence="done")
    assert done["status"] == "fulfilled"

    db_path = os.environ["NOUGEN_DESTINY_DB"]
    assert db_path == str(tmp_path / "destinies.db") and os.path.exists(db_path)


def test_search_destinies_uses_the_query():
    """The query filters; finished destinies appear only when asked for."""
    _call(
        "create_destiny",
        title="Alpha lantern",
        goal="Shine",
        trigger="t1",
        required="",
        forbidden="",
        verification="v1",
        actor="a",
    )
    _call(
        "create_destiny",
        title="Beta harbor",
        goal="Dock",
        trigger="t2",
        required="",
        forbidden="",
        verification="v2",
        actor="a",
    )

    res = _call("search_destinies", query="lantern")
    assert res["count"] == 1
    assert res["destinies"][0]["title"] == "Alpha lantern"

    res = _call("search_destinies", query="zzz-no-match")
    assert res["count"] == 0

    alpha_id = _call("search_destinies", query="Alpha")["destinies"][0]["id"]
    _call("update_destiny", destiny_id=alpha_id, status="active", actor="a", evidence="go")
    _call("update_destiny", destiny_id=alpha_id, status="fulfilled", actor="a", evidence="done")

    res = _call("search_destinies", query="lantern")
    assert res["count"] == 0

    res = _call("search_destinies", query="lantern", include_finished=True)
    assert res["count"] == 1


def test_errors_come_back_as_errors():
    """A failed call says so: error dicts for bad input, Unknown tool for a missing name."""
    got = _call("get_destiny", destiny_id=999)
    assert "error" in got

    created = _call(
        "create_destiny",
        title="Error case",
        goal="Reach a state",
        trigger="t",
        required="",
        forbidden="",
        verification="v",
        actor="a",
    )
    assert "error" in _call("create_destiny", title="No", goal="G")  # too short: refused, nothing stored
    upd = _call("update_destiny", destiny_id=created["id"], status="not-a-status", actor="a", evidence="x")
    assert "error" in upd

    with pytest.raises(Exception, match="Unknown tool"):
        asyncio.run(app.node_mcp.call_tool("destroy_destiny", {}))


def test_tenant_calls_stay_in_the_tenant_store(tmp_path):
    """A tenant call lands in the tenant vault, never the operator env store."""
    tenant_dir = tmp_path / "tenant"
    tenant_dir.mkdir()
    tokens = core.bind_active_vault(tenant_dir, "tenant-x")
    try:
        assert destiny.db_path() == tenant_dir / "destinies.db"
        created = _call(
            "create_destiny",
            title="Tenant only",
            goal="Isolated",
            trigger="t",
            required="",
            forbidden="",
            verification="v",
            actor="tenant-user",
        )
        assert created["status"] == "dormant"
        assert _call("search_destinies", query="Tenant")["count"] == 1
    finally:
        core.reset_active_vault(tokens)

    assert (tenant_dir / "destinies.db").exists()

    # back in the owner context the env store is used, and the tenant record is not in it
    res = _call("search_destinies", query="Tenant")
    assert res["count"] == 0

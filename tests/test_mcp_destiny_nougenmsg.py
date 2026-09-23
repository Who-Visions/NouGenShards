import json
from nougen_shards import mcp
from nougen_shards.nougenmsg import NouGenMsgBus


def test_destiny_mcp_tools(tmp_path, monkeypatch):
    test_db = tmp_path / "test_destinies.db"
    monkeypatch.setenv("NOUGEN_DESTINY_DB", str(test_db))

    # Test create_destiny
    res_str = mcp.create_destiny(
        title="Test prospective goal",
        goal="Reach 100% test coverage for MCP tools",
        branch="U0",
        trigger="on test run",
        required_events=["pass all tests", "verify MCP schemas"],
        status="dormant"
    )
    res = json.loads(res_str)
    assert res["id"] > 0
    assert res["title"] == "Test prospective goal"
    assert res["status"] == "dormant"

    # Test unfinished_destinies
    unf_str = mcp.unfinished_destinies()
    unf = json.loads(unf_str)
    assert unf["count"] >= 1
    assert any(d["id"] == res["id"] for d in unf["destinies"])

    # Test search_destinies
    search_str = mcp.search_destinies("prospective")
    search_res = json.loads(search_str)
    assert search_res["count"] >= 1
    assert search_res["destinies"][0]["id"] == res["id"]


def test_nougenmsg_search_mcp_tool(tmp_path, monkeypatch):
    inbox_dir = tmp_path / "agy_inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    msg_file = inbox_dir / "msg_test.json"
    msg_file.write_text(json.dumps({
        "message_id": "test-msg-123",
        "sender": "apollo",
        "text": "Hurricane kick execution live on stadium",
        "timestamp": 1234567890
    }), encoding="utf-8")

    # Monkeypatch home
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    # Test NouGenMsgBus.search_messages
    res = NouGenMsgBus.search_messages("Hurricane kick")
    assert isinstance(res, list)

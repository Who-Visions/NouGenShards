import asyncio
import json

from nougen_shards.mcp_host_scope import HostScopedMCP, load_scopes

ALL_TOOLS = ["nougenmsg", "nougenmsg_inbox", "shard_forget", "vault_put", "dav1d_exec", "node_status"]


class FakeMCP:
    """Stands in for the stateless-JSON MCP app and records what reached it."""

    def __init__(self):
        self.seen = []

    async def __call__(self, scope, receive, send):
        body = (await receive())["body"]
        msg = json.loads(body)
        self.seen.append(msg)

        def answer(m):
            if m["method"] == "tools/list":
                return {"jsonrpc": "2.0", "id": m["id"], "result": {"tools": [{"name": n} for n in ALL_TOOLS]}}
            if m["method"] == "initialize":
                return {"jsonrpc": "2.0", "id": m["id"], "result": {"serverInfo": {"name": "NouGenShards"}}}
            return {"jsonrpc": "2.0", "id": m["id"], "result": {"called": m["params"]["name"]}}

        out = json.dumps([answer(m) for m in msg] if isinstance(msg, list) else answer(msg)).encode()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(out)).encode())]})
        await send({"type": "http.response.body", "body": out})


def call(app, host, payload):
    scope = {"type": "http", "method": "POST", "headers": [(b"host", host.encode())]}
    got = {}

    async def receive():
        return {"type": "http.request", "body": json.dumps(payload).encode(), "more_body": False}

    async def send(event):
        if event["type"] == "http.response.start":
            got["headers"] = dict(event["headers"])
        else:
            got["body"] = event["body"]

    asyncio.run(app(scope, receive, send))
    assert int(got["headers"][b"content-length"]) == len(got["body"])
    return json.loads(got["body"])


def make():
    inner = FakeMCP()
    return HostScopedMCP(inner, load_scopes({"NOUGEN_MCP_MSG_HOSTS": "msgs.example.test"})), inner


def test_msgs_host_lists_only_messaging_tools():
    app, _ = make()
    res = call(app, "msgs.example.test", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert [t["name"] for t in res["result"]["tools"]] == ["nougenmsg", "nougenmsg_inbox", "node_status"]


def test_other_hosts_pass_through_untouched():
    app, _ = make()
    res = call(app, "shards.example.test", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert [t["name"] for t in res["result"]["tools"]] == ALL_TOOLS


def test_blocked_tool_call_never_reaches_the_server():
    app, inner = make()
    res = call(app, "msgs.example.test",
               {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "shard_forget", "arguments": {}}})
    assert res["id"] == 7 and res["error"]["code"] == -32601
    assert inner.seen == []


def test_allowed_tool_call_passes():
    app, inner = make()
    res = call(app, "msgs.example.test",
               {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "nougenmsg", "arguments": {}}})
    assert res["result"] == {"called": "nougenmsg"} and len(inner.seen) == 1


def test_initialize_renames_server_on_scoped_host_only():
    app, _ = make()
    init = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}}
    assert call(app, "msgs.example.test", init)["result"]["serverInfo"]["name"] == "NouGenMsg"
    assert call(app, "mcp.example.test", init)["result"]["serverInfo"]["name"] == "NouGenShards"


def test_forwarded_host_and_port_are_honoured():
    app, _ = make()
    scope_host = "MSGS.example.test:443"
    res = call(app, scope_host, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert all(t["name"] in ("nougenmsg", "nougenmsg_inbox", "node_status") for t in res["result"]["tools"])


def test_batch_with_one_blocked_call_is_refused_whole():
    app, inner = make()
    batch = [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "nougenmsg"}},
             {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "vault_put"}}]
    res = call(app, "msgs.example.test", batch)
    assert isinstance(res, list) and res[0]["id"] == 2 and inner.seen == []


def test_malformed_override_keeps_messaging_hosts_scoped():
    scopes = load_scopes({"NOUGEN_MCP_MSG_HOSTS": "msgs.example.test", "NOUGEN_MCP_HOST_SCOPES": "{not json"})
    assert "shard_forget" not in scopes["msgs.example.test"]["tools"]
    scopes = load_scopes({"NOUGEN_MCP_HOST_SCOPES": json.dumps({"X.test": {"name": "X", "tools": ["a"]}})})
    assert set(scopes) == {"x.test"} and scopes["x.test"]["tools"] == frozenset({"a"})


def test_nothing_configured_scopes_nothing():
    assert load_scopes({}) == {}
    inner = FakeMCP()
    res = call(HostScopedMCP(inner, load_scopes({})), "msgs.example.test",
               {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert [t["name"] for t in res["result"]["tools"]] == ALL_TOOLS

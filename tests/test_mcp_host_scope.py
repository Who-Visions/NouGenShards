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


def call(app, host, payload, extra_headers=()):
    scope = {"type": "http", "method": "POST", "headers": [(b"host", host.encode()), *extra_headers]}
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


def test_real_mcp_server_end_to_end():
    """Same transport settings as app.py, driven through a real ASGI stack:
    allowed calls run, blocked calls refused, list filtered, other hosts untouched."""
    import contextlib

    from mcp.server.mcpserver import MCPServer
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from starlette.testclient import TestClient

    srv = MCPServer("NouGenShards")

    @srv.tool()
    def nougenmsg(message: str) -> str:
        return "sent:" + message

    @srv.tool()
    def shard_forget(shard_id: int) -> str:
        return "forgot"

    inner = srv.streamable_http_app(
        stateless_http=True, json_response=True, streamable_http_path="/",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with srv.session_manager.run():
            yield

    app = Starlette(routes=[Mount("/mcp", HostScopedMCP(inner, load_scopes({"NOUGEN_MCP_MSG_HOSTS": "msgs.example.test"})))],
                    lifespan=lifespan)
    hdr = {"accept": "application/json, text/event-stream", "content-type": "application/json"}

    def rpc(client, host, method, params=None):
        r = client.post("/mcp/", headers={**hdr, "host": host},
                        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
        assert r.status_code == 200, r.text
        return r.json()

    with TestClient(app) as c:
        init = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}
        assert rpc(c, "msgs.example.test", "initialize", init)["result"]["serverInfo"]["name"] == "NouGenMsg"
        names = [t["name"] for t in rpc(c, "msgs.example.test", "tools/list")["result"]["tools"]]
        assert names == ["nougenmsg"]
        ok = rpc(c, "msgs.example.test", "tools/call", {"name": "nougenmsg", "arguments": {"message": "hi"}})
        assert "sent:hi" in json.dumps(ok["result"])
        blocked = rpc(c, "msgs.example.test", "tools/call", {"name": "shard_forget", "arguments": {"shard_id": 1}})
        assert blocked["error"]["code"] == -32601
        assert sorted(t["name"] for t in rpc(c, "shards.example.test", "tools/list")["result"]["tools"]) == ["nougenmsg", "shard_forget"]


def test_bad_tool_entries_never_crash_startup():
    bad = json.dumps({"a.test": {"name": 5, "tools": [{"x": 1}, ["y"], "ok_tool", 7]},
                      "b.test": {"tools": "not-a-list"}, "c.test": "nope"})
    scopes = load_scopes({"NOUGEN_MCP_MSG_HOSTS": "msgs.example.test", "NOUGEN_MCP_HOST_SCOPES": bad})
    assert scopes["a.test"] == {"name": None, "tools": frozenset({"ok_tool"})}
    assert "b.test" not in scopes and "c.test" not in scopes
    assert "nougenmsg" in scopes["msgs.example.test"]["tools"]


def test_malformed_tool_call_names_are_refused_not_crashed():
    app, inner = make()
    for params in ({"name": None}, {"name": {"x": 1}}, {"name": ["nougenmsg"]}, {}, ["nougenmsg"], None):
        res = call(app, "msgs.example.test", {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": params})
        assert res["id"] == 9 and res["error"]["code"] == -32601, params
    assert inner.seen == []


def test_spoofed_forwarded_host_cannot_unscope_msgs_host():
    app, inner = make()
    xfh = [(b"x-forwarded-host", b"mcp.example.test")]
    res = call(app, "msgs.example.test", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, xfh)
    assert [t["name"] for t in res["result"]["tools"]] == ["nougenmsg", "nougenmsg_inbox", "node_status"]
    res = call(app, "msgs.example.test",
               {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "vault_put"}}, xfh)
    assert res["error"]["code"] == -32601 and len(inner.seen) == 1


def test_forwarded_msgs_host_behind_proxy_is_scoped():
    app, _ = make()
    xfh = [(b"x-forwarded-host", b"msgs.example.test, edge.example.test")]
    res = call(app, "127.0.0.1:4444", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, xfh)
    assert [t["name"] for t in res["result"]["tools"]] == ["nougenmsg", "nougenmsg_inbox", "node_status"]


def raw_call(app, host, payload, extra_headers=()):
    scope = {"type": "http", "method": "POST", "headers": [(b"host", host.encode()), *extra_headers]}
    got = {}

    async def receive():
        return {"type": "http.request", "body": json.dumps(payload).encode(), "more_body": False}

    async def send(event):
        if event["type"] == "http.response.start":
            got["status"] = event.get("status", 200)
        else:
            got["body"] = event["body"]

    asyncio.run(app(scope, receive, send))
    return got["status"], json.loads(got["body"])


def test_trailing_dot_and_port_still_scoped():
    app, inner = make()
    for host in ("msgs.example.test.", "MSGS.example.test.:443", "msgs.example.test:8443"):
        res = call(app, host, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "vault_put"}})
        assert res["error"]["code"] == -32601, host
    assert inner.seen == []


def test_scope_keys_normalised():
    scopes = load_scopes({"NOUGEN_MCP_MSG_HOSTS": " Msgs.Example.Test. "})
    assert list(scopes) == ["msgs.example.test"]


def fail_closed():
    inner = FakeMCP()
    app = HostScopedMCP(inner, load_scopes({"NOUGEN_MCP_MSG_HOSTS": "msgs.example.test"}),
                        open_hosts=["mcp.example.test", "127.0.0.1"])
    return app, inner


def test_fail_closed_refuses_unrecognised_host():
    app, inner = fail_closed()
    # Proxy rewrote Host to an internal name; client sent its own X-Forwarded-Host.
    status, body = raw_call(app, "internal.svc", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                            [(b"x-forwarded-host", b"evil.example.test")])
    assert status == 403 and body == {"error": "host not recognised"}
    assert inner.seen == []


def test_fail_closed_lets_open_hosts_through():
    app, _ = fail_closed()
    for host in ("mcp.example.test", "127.0.0.1:4444"):
        res = call(app, host, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert len(res["result"]["tools"]) == len(ALL_TOOLS), host


def test_fail_closed_still_scopes_msgs_host():
    app, _ = fail_closed()
    res = call(app, "msgs.example.test.", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert [t["name"] for t in res["result"]["tools"]] == ["nougenmsg", "nougenmsg_inbox", "node_status"]


def test_open_hosts_unset_keeps_pass_through():
    app, _ = make()
    res = call(app, "anything.example.test", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert len(res["result"]["tools"]) == len(ALL_TOOLS)

"""Rhea's gateway proxy: dav1d/agy and the generic "gateway" tool must hop to
blade's node over HTTP, never call dav1d_executor in-process.

2026-09-01: calling run_dav1d_agy() directly from inside the Space always hit
its simulated fallback, since the real AGY binary only exists on blade's
Stadium node. Confirmed live via Rhea's own dav1d bridge before this fix.
"""
import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import rhea_noir


class _FakeResponse:
    def __init__(self, body: dict):
        self._raw = json.dumps(body).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _rpc_result(result):
    return {"jsonrpc": "2.0", "id": 2, "result": result}


class TestGatewayCall:
    def test_missing_url_returns_clean_error(self, monkeypatch):
        monkeypatch.delenv("SHARD_GATEWAY_URL", raising=False)
        out = rhea_noir._gateway_call("dav1d_exec", {})
        assert "error" in out
        assert "SHARD_GATEWAY_URL" in out["error"]

    def test_two_step_initialize_then_tools_call(self, monkeypatch):
        monkeypatch.setenv("SHARD_GATEWAY_URL", "https://blade.nougenai.com")
        monkeypatch.setenv("SHARD_GATEWAY_TOKEN", "test-token")
        responses = [
            _FakeResponse({"jsonrpc": "2.0", "id": 1, "result": {}}),
            _FakeResponse(_rpc_result({"structuredContent": {"status": "ok"}})),
        ]
        seen = []

        def fake_urlopen(req, timeout):
            seen.append(json.loads(req.data.decode()))
            return responses.pop(0)

        with patch("rhea_noir.urllib.request.urlopen", side_effect=fake_urlopen):
            out = rhea_noir._gateway_call("recall_memory", {"query": "x"})

        assert out == {"status": "ok"}
        assert seen[0]["method"] == "initialize"
        assert seen[1]["method"] == "tools/call"
        assert seen[1]["params"] == {"name": "recall_memory", "arguments": {"query": "x"}}

    def test_is_error_result_surfaces_as_error(self, monkeypatch):
        monkeypatch.setenv("SHARD_GATEWAY_URL", "https://blade.nougenai.com")
        monkeypatch.setenv("SHARD_GATEWAY_TOKEN", "test-token")
        responses = [
            _FakeResponse({"jsonrpc": "2.0", "id": 1, "result": {}}),
            _FakeResponse(_rpc_result({"isError": True, "content": [{"type": "text", "text": "boom"}]})),
        ]
        with patch("rhea_noir.urllib.request.urlopen", side_effect=lambda req, timeout: responses.pop(0)):
            out = rhea_noir._gateway_call("dav1d_exec", {})
        assert out == {"error": "boom"}


class TestRunToolRouting:
    def test_dav1d_tool_routes_through_gateway_not_in_process(self, monkeypatch):
        calls = {}

        def fake_gateway_call(name, arguments):
            calls["name"] = name
            calls["arguments"] = arguments
            return {"status": "ok", "exit_code": 0}

        monkeypatch.setattr(rhea_noir, "_gateway_call", fake_gateway_call)
        out = rhea_noir._run_tool({"tool": "dav1d", "subcommand": "mcp list", "timeout": 20})

        assert out == {"status": "ok", "exit_code": 0}
        assert calls["name"] == "dav1d_exec"
        assert calls["arguments"]["subcommand"] == "mcp list"
        assert calls["arguments"]["timeout"] == 20

    def test_generic_gateway_tool_requires_name(self, monkeypatch):
        out = rhea_noir._run_tool({"tool": "gateway", "arguments": {}})
        assert "error" in out

    def test_generic_gateway_tool_forwards_name_and_arguments(self, monkeypatch):
        calls = {}
        monkeypatch.setattr(
            rhea_noir, "_gateway_call",
            lambda name, arguments: calls.update(name=name, arguments=arguments) or {"ok": True},
        )
        out = rhea_noir._run_tool({"tool": "gateway", "name": "vault_list", "arguments": {"foo": "bar"}})
        assert out == {"ok": True}
        assert calls == {"name": "vault_list", "arguments": {"foo": "bar"}}

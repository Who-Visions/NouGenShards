"""File-read, URL-fetch, and worker-deploy MCP tools are opt-in (WG-1175/WG-1777)."""
import pytest

from nougen_shards import mcp as mcp_mod


@pytest.mark.parametrize("env_var,call", [
    ("NOUGEN_ENABLE_FILE_TOOLS", lambda: mcp_mod.analyze_file_sandboxed("/etc/hosts")),
    ("NOUGEN_ENABLE_FILE_TOOLS", lambda: mcp_mod.fetch_web_sandboxed("https://example.invalid/")),
    ("NOUGEN_ENABLE_CF_TOOLS", lambda: mcp_mod.cf_deploy_worker("/nonexistent")),
])
def test_tool_refuses_by_default(monkeypatch, env_var, call):
    monkeypatch.delenv(env_var, raising=False)
    out = call()
    assert out.startswith("Error:") and "disabled by default" in out
    assert env_var in out


def test_gate_opens_with_env(monkeypatch):
    monkeypatch.setenv("NOUGEN_ENABLE_FILE_TOOLS", "1")
    assert mcp_mod._tool_gate("NOUGEN_ENABLE_FILE_TOOLS", "x") is None


def test_gate_rejects_falsey_values(monkeypatch):
    monkeypatch.setenv("NOUGEN_ENABLE_CF_TOOLS", "0")
    assert mcp_mod._tool_gate("NOUGEN_ENABLE_CF_TOOLS", "x") is not None

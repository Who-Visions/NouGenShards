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


def test_cf_run_ai_refuses_by_default(monkeypatch):
    monkeypatch.delenv("NOUGEN_ENABLE_CF_TOOLS", raising=False)
    out = mcp_mod.cf_run_ai("hi")
    assert out.startswith("Error:") and "NOUGEN_ENABLE_CF_TOOLS" in out


def test_file_read_outside_root_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_ENABLE_FILE_TOOLS", "1")
    monkeypatch.setenv("NOUGEN_FILE_TOOLS_ROOT", str(tmp_path))
    out = mcp_mod.analyze_file_sandboxed("/etc/hosts")
    assert out.startswith("Error:") and "outside the allowed root" in out


def test_file_read_via_dotdot_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_ENABLE_FILE_TOOLS", "1")
    monkeypatch.setenv("NOUGEN_FILE_TOOLS_ROOT", str(tmp_path))
    out = mcp_mod.analyze_file_sandboxed(str(tmp_path / ".." / "escape.txt"))
    assert "outside the allowed root" in out


def test_file_read_inside_root_passes_the_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_FILE_TOOLS_ROOT", str(tmp_path))
    assert mcp_mod._file_root_gate(str(tmp_path / "a.py")) is None

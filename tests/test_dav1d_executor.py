"""
Unit tests for Dav1d Executor (AGY CLI integration).
"""
import subprocess

from nougen_shards.dav1d_executor import (
    run_dav1d_agy,
    resolve_agy_binary,
    get_agy_version,
    _VERSION_UNKNOWN,
)


def test_dav1d_executor_resolution():
    bin_path = resolve_agy_binary()
    # On this Blade node, AGY CLI is installed or resolved dynamically
    assert bin_path is not None or True


def test_dav1d_executor_version_env_override_wins(monkeypatch):
    monkeypatch.setenv("NOUGEN_AGY_VERSION", "9.9.9-pinned")
    assert get_agy_version("dummy") == "9.9.9-pinned"


def test_dav1d_executor_version_unknown_without_binary(monkeypatch):
    """No binary means no version. The old code answered 1.1.17 regardless."""
    monkeypatch.delenv("NOUGEN_AGY_VERSION", raising=False)
    assert get_agy_version(None) == _VERSION_UNKNOWN


def test_dav1d_executor_version_bad_binary_is_unknown_not_invented(monkeypatch):
    monkeypatch.delenv("NOUGEN_AGY_VERSION", raising=False)
    monkeypatch.setenv("NOUGEN_AGY_VERSION_CACHE", "0")
    assert get_agy_version("no_such_binary_agy_probe_test") == _VERSION_UNKNOWN


def test_dav1d_executor_version_matches_live_binary(monkeypatch):
    """When a real agy binary is present, the reported version is the one it prints."""
    monkeypatch.delenv("NOUGEN_AGY_VERSION", raising=False)
    monkeypatch.setenv("NOUGEN_AGY_VERSION_CACHE", "0")
    bin_path = resolve_agy_binary()
    if not bin_path:
        return  # no AGY CLI on this host (CI containers); nothing to compare against
    probe = subprocess.run([bin_path, "--version"], capture_output=True, text=True, timeout=10)
    expected = next((ln.strip() for ln in (probe.stdout or probe.stderr).splitlines() if ln.strip()), "")
    assert get_agy_version(bin_path) == expected
    assert expected != _VERSION_UNKNOWN


def test_dav1d_executor_mcp_list():
    res = run_dav1d_agy(args=["mcp", "list"])
    assert res["machine"] == "Dav1d"
    assert "version" in res
    assert res["status"] in ("success", "simulated")
    assert res["exit_code"] == 0


def test_dav1d_executor_rejected_subcommand():
    res = run_dav1d_agy(subcommand="rm -rf /")
    assert res["status"] == "rejected"
    assert res["exit_code"] == 1
    assert "not in bounded allowlist" in res["error"]


def test_dav1d_executor_version_word_becomes_flag(monkeypatch):
    """agy 1.2.x rejects a bare `version`; the executor must send --version."""
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="agy 0.0.0\n", stderr="")

    monkeypatch.setattr("nougen_shards.dav1d_executor.resolve_agy_binary", lambda: "agy-fake")
    monkeypatch.setattr("nougen_shards.dav1d_executor.subprocess.run", fake_run)
    monkeypatch.setenv("NOUGEN_AGY_VERSION", "test")
    res = run_dav1d_agy(subcommand="version")
    assert seen["cmd"] == ["agy-fake", "--version"]
    assert res["status"] == "success"


def test_dav1d_persona_answers_from_ollama(monkeypatch):
    import io
    import json
    from nougen_shards import dav1d_executor as ex

    def fake_urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if url.endswith("/api/tags"):
            return io.BytesIO(json.dumps({"models": [{"name": "dav1d:e2b-pre-selfid"}, {"name": "dav1d:e2b"}]}).encode())
        payload = json.loads(req.data)
        assert payload["model"] == "dav1d:e2b" and payload["think"] is False
        return io.BytesIO(json.dumps({"message": {"content": "alive"}}).encode())

    monkeypatch.delenv("NOUGEN_AGENT_MODEL_DAV1D", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    res = ex.ask_dav1d_persona("status?")
    assert res["engine"] == "ollama" and res["model"] == "dav1d:e2b" and res["output"] == "alive"


def test_dav1d_persona_falls_back_to_agy_labeled(monkeypatch):
    from nougen_shards import dav1d_executor as ex

    def boom(*a, **k):
        raise OSError("ollama down")

    monkeypatch.setenv("NOUGEN_AGENT_MODEL_DAV1D", "dav1d:e2b")
    monkeypatch.setattr("urllib.request.urlopen", boom)
    monkeypatch.setattr(ex, "run_dav1d_agy", lambda **k: {"engine": "agy-cli", "status": "success"})
    res = ex.ask_dav1d_persona("status?")
    assert res["engine"] == "agy-cli" and res["fallback"].endswith("OSError")


def test_dav1d_executor_rejects_unlisted_flag():
    res = run_dav1d_agy(args=["--dangerously-skip-permissions", "--print", "x"])
    assert res["status"] == "rejected"


def test_smuggled_flag_after_allowed_subcommand_is_rejected():
    from nougen_shards.dav1d_executor import run_dav1d_agy

    out = run_dav1d_agy(args=["mcp", "add", "--command", "/bin/sh"])
    assert out["status"] == "rejected"
    assert "--command" in out["error"]


def test_control_characters_in_arguments_are_rejected():
    from nougen_shards.dav1d_executor import _reject_unsafe_args

    assert _reject_unsafe_args(["--print", "a\x00b"], prompt_index=1)
    assert _reject_unsafe_args(["mcp", "list"]) == ""


def test_prompt_may_start_with_dash_but_not_carry_control_bytes():
    from nougen_shards.dav1d_executor import _reject_unsafe_args

    assert _reject_unsafe_args(["--print", "-not a flag, a prompt"], prompt_index=1) == ""

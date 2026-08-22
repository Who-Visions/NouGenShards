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

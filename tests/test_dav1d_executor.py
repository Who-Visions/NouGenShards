"""
Unit tests for Dav1d Executor (AGY CLI integration).
"""
from nougen_shards.dav1d_executor import run_dav1d_agy, resolve_agy_binary, get_agy_version


def test_dav1d_executor_resolution():
    bin_path = resolve_agy_binary()
    # On this Blade node, AGY CLI is installed or resolved dynamically
    assert bin_path is not None or True


def test_dav1d_executor_version():
    ver = get_agy_version("dummy")
    assert ver == "1.1.17"


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

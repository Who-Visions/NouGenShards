"""Unit tests for Keymaker Perimeter Guard (`~/.nougen/tools/keymaker_guard.py`)
and Stitch MCP Keymaker-first resolution (`stitch_mcp_bridge.py` / `stitch_headers.py`).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_guard():
    guard_path = Path.home() / ".nougen" / "tools" / "keymaker_guard.py"
    if not guard_path.exists():
        pytest.skip("~/.nougen/tools/keymaker_guard.py not installed on this runner")
    spec = importlib.util.spec_from_file_location("keymaker_guard", guard_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_blocks_gcloud_print_access_token():
    guard = _load_guard()
    allowed, reason = guard.check_payload(
        {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "gcloud auth print-access-token"},
            }
        }
    )
    assert not allowed
    assert "gcloud auth print-access-token is forbidden" in (reason or "")


def test_blocks_gcloud_adc_print_access_token_in_claude_code_format():
    guard = _load_guard()
    allowed, reason = guard.check_payload(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "TOKEN=$(gcloud auth application-default print-access-token)"},
        }
    )
    assert not allowed
    assert "print-access-token" in (reason or "")


def test_blocks_gh_auth_token_and_keychain_dump():
    guard = _load_guard()
    allowed1, _ = guard.check_payload(
        {"toolCall": {"name": "run_command", "args": {"CommandLine": "gh auth token"}}}
    )
    allowed2, _ = guard.check_payload(
        {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "security find-generic-password -s nougenshards-vault -w"},
            }
        }
    )
    assert not allowed1
    assert not allowed2


def test_blocks_raw_credential_file_reads():
    guard = _load_guard()
    for fname in (
        "~/.config/gcloud/application_default_credentials.json",
        "~/.gemini/mcp-oauth-tokens.json",
        "~/.nougen/.keyring_cache.json",
        "~/.nougen/secrets/shards_secrets.db",
    ):
        allowed, reason = guard.check_payload(
            {"toolCall": {"name": "read_file", "args": {"Path": fname}}}
        )
        assert not allowed, f"expected {fname} read to be blocked"
        assert "forbidden" in (reason or "")


def test_blocks_writing_live_tokens_but_allows_synthetic_padding():
    guard = _load_guard()
    # Non-synthetic (no 16-char repeat) token shape constructed dynamically -> blocked
    fake_live_oauth = "ya" + "29" + "." + "a0" + "".join(f"x{i % 9}y" for i in range(14))
    allowed_live, reason_live = guard.check_payload(
        {
            "toolCall": {
                "name": "write_file",
                "args": {"Path": "/tmp/test.json", "Content": f'{{"token": "{fake_live_oauth}"}}'},
            }
        }
    )
    assert not allowed_live
    assert "Google OAuth2 access token" in (reason_live or "")

    # Synthetic test fixture with >=16 identical chars -> allowed
    synthetic = "ya" + "29" + "." + "a0" + ("K" * 32)
    allowed_syn, _ = guard.check_payload(
        {
            "toolCall": {
                "name": "write_file",
                "args": {"Path": "/tmp/test_fixture.py", "Content": f'SAMPLE = "{synthetic}"'},
            }
        }
    )
    assert allowed_syn


def test_allows_ordinary_commands_and_files():
    guard = _load_guard()
    allowed, reason = guard.check_payload(
        {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "pytest tests/test_keymaker_security.py -q"},
            }
        }
    )
    assert allowed
    assert reason is None


def test_stitch_bridge_never_calls_gcloud():
    bridge_path = Path.home() / ".gemini" / "antigravity" / "bin" / "stitch_mcp_bridge.py"
    if not bridge_path.exists():
        pytest.skip("stitch_mcp_bridge.py not installed on this runner")
    source = bridge_path.read_text(encoding="utf-8")
    assert '["gcloud", "auth", "print-access-token"]' not in source
    assert "resolve_stitch_headers" in source

"""
Unit tests for fleet usage ledger capture in tools/fleet_test.py.
"""
import json
import logging
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SPEC = spec_from_file_location(
    "fleet_test", Path(__file__).resolve().parents[1] / "tools" / "fleet_test.py"
)
fleet_test = module_from_spec(SPEC)
SPEC.loader.exec_module(fleet_test)


def test_resolve_ledger_path_env_override(monkeypatch, tmp_path):
    custom_ledger = tmp_path / "custom" / "fleet_usage.jsonl"
    monkeypatch.setenv("FLEET_USAGE_LEDGER", str(custom_ledger))
    assert fleet_test.resolve_ledger_path() == custom_ledger


def test_resolve_ledger_path_sol_vault_env(monkeypatch, tmp_path):
    monkeypatch.delenv("FLEET_USAGE_LEDGER", raising=False)
    vault_dir = tmp_path / "sol_vault"
    monkeypatch.setenv("SOL_VAULT_DIR", str(vault_dir))
    assert fleet_test.resolve_ledger_path() == vault_dir / "fleet_usage.jsonl"


def test_resolve_ledger_path_tracker_dir_env(monkeypatch, tmp_path):
    monkeypatch.delenv("FLEET_USAGE_LEDGER", raising=False)
    monkeypatch.delenv("SOL_VAULT_DIR", raising=False)
    tracker_dir = tmp_path / "custom_tracker"
    monkeypatch.setenv("NOUGEN_TRACKER_DIR", str(tracker_dir))
    assert fleet_test.resolve_ledger_path() == tracker_dir / "vault" / "fleet_usage.jsonl"


def test_resolve_ledger_path_sister_or_fallback(monkeypatch):
    monkeypatch.delenv("FLEET_USAGE_LEDGER", raising=False)
    monkeypatch.delenv("SOL_VAULT_DIR", raising=False)
    monkeypatch.delenv("NOUGEN_TRACKER_DIR", raising=False)
    resolved = fleet_test.resolve_ledger_path()
    assert isinstance(resolved, Path)
    assert resolved.name == "fleet_usage.jsonl"


@patch.object(fleet_test, "_post_json")
@patch.object(fleet_test.keymaker, "get_secret", return_value="sk-real-secret-12345")
def test_call_openrouter_writes_exact_ledger_row(mock_secret, mock_post, tmp_path, monkeypatch):
    ledger_path = tmp_path / "ledger" / "fleet_usage.jsonl"
    monkeypatch.setenv("FLEET_USAGE_LEDGER", str(ledger_path))

    mock_post.return_value = {
        "model": "deepseek/deepseek-chat",
        "choices": [{"message": {"content": "Parity looks good."}}],
        "usage": {
            "prompt_tokens": 125,
            "completion_tokens": 42,
            "prompt_tokens_details": {"cached_tokens": 15},
            "completion_tokens_details": {"reasoning_tokens": 10},
        },
    }

    res = fleet_test.call_openrouter(
        key_name="OPENROUTER_TEST_KEY",
        system="Audit system prompt",
        prompt="Audit user prompt",
        model="deepseek/deepseek-chat",
    )

    assert "error" not in res
    assert res["model"] == "deepseek/deepseek-chat"
    assert res["content"] == "Parity looks good."

    assert ledger_path.exists()
    lines = [ln.strip() for ln in ledger_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1

    row = json.loads(lines[0])
    assert row["provider"] == "openrouter"
    assert row["lane"] == "OPENROUTER_TEST_KEY"
    assert "sk-real-secret-12345" not in json.dumps(row)
    assert row["model"] == "deepseek/deepseek-chat"
    assert row["input_tokens"] == 125
    assert row["output_tokens"] == 42
    assert row["cached_tokens"] == 15
    assert row["reasoning_tokens"] == 10
    assert row["source"] == "fleet_test"
    assert row["exact"] is True
    assert row["estimated"] is False
    assert "timestamp" in row


@patch.object(fleet_test, "_post_json")
@patch.object(fleet_test.keymaker, "get_secret", return_value="ollama-secret-value-abc")
def test_call_ollama_cloud_writes_exact_ledger_row(mock_secret, mock_post, tmp_path, monkeypatch):
    ledger_path = tmp_path / "ledger" / "fleet_usage.jsonl"
    monkeypatch.setenv("FLEET_USAGE_LEDGER", str(ledger_path))

    mock_post.return_value = {
        "model": "gemma4:31b-cloud",
        "message": {"content": "Ollama cloud answer."},
        "prompt_eval_count": 310,
        "eval_count": 85,
    }

    res = fleet_test.call_ollama_cloud(
        key_name="OLLAMA_AIWITHDAV3",
        system="System instructions",
        prompt="User question",
        model="gemma4:31b-cloud",
    )

    assert "error" not in res
    assert res["model"] == "gemma4:31b-cloud"
    assert res["content"] == "Ollama cloud answer."

    lines = [ln.strip() for ln in ledger_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1

    row = json.loads(lines[0])
    assert row["provider"] == "ollama-cloud"
    assert row["lane"] == "OLLAMA_AIWITHDAV3"
    assert "ollama-secret-value-abc" not in json.dumps(row)
    assert row["model"] == "gemma4:31b-cloud"
    assert row["input_tokens"] == 310
    assert row["output_tokens"] == 85
    assert row["exact"] is True
    assert row["estimated"] is False


@patch.object(fleet_test, "_post_json")
@patch.object(fleet_test.keymaker, "get_secret", return_value="secret-key")
def test_missing_counts_estimates_and_marks_estimated_ollama(mock_secret, mock_post, tmp_path, monkeypatch):
    ledger_path = tmp_path / "ledger" / "fleet_usage.jsonl"
    monkeypatch.setenv("FLEET_USAGE_LEDGER", str(ledger_path))

    mock_post.return_value = {
        "model": "gemma4:31b-cloud",
        "message": {"content": "A" * 80},  # 80 chars -> ~20 estimated tokens
    }

    sys_text = "S" * 40
    user_text = "U" * 60  # total in 100 chars -> ~25 estimated tokens

    res = fleet_test.call_ollama_cloud(
        key_name="OLLAMA_CONTACTWHO",
        system=sys_text,
        prompt=user_text,
        model="gemma4:31b-cloud",
    )

    assert "error" not in res
    lines = [ln.strip() for ln in ledger_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1

    row = json.loads(lines[0])
    assert row["provider"] == "ollama-cloud"
    assert row["lane"] == "OLLAMA_CONTACTWHO"
    assert row["input_tokens"] == 25
    assert row["output_tokens"] == 20
    assert row["exact"] is False
    assert row["estimated"] is True


@patch.object(fleet_test, "_post_json")
@patch.object(fleet_test.keymaker, "get_secret", return_value="secret-key")
def test_missing_counts_estimates_and_marks_estimated_openrouter(mock_secret, mock_post, tmp_path, monkeypatch):
    ledger_path = tmp_path / "ledger" / "fleet_usage.jsonl"
    monkeypatch.setenv("FLEET_USAGE_LEDGER", str(ledger_path))

    mock_post.return_value = {
        "model": "deepseek/deepseek-chat",
        "choices": [{"message": {"content": "B" * 40}}],
        # No usage dictionary
    }

    res = fleet_test.call_openrouter(
        key_name="OPENROUTER_DAVE",
        system="S" * 20,
        prompt="P" * 20,
        model="deepseek/deepseek-chat",
    )

    assert "error" not in res
    lines = [ln.strip() for ln in ledger_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1

    row = json.loads(lines[0])
    assert row["provider"] == "openrouter"
    assert row["lane"] == "OPENROUTER_DAVE"
    assert row["input_tokens"] == 10
    assert row["output_tokens"] == 10
    assert row["exact"] is False
    assert row["estimated"] is True


@patch.object(fleet_test, "_post_json")
@patch.object(fleet_test.keymaker, "get_secret", return_value="secret-key")
def test_failing_ledger_write_does_not_raise(mock_secret, mock_post, monkeypatch, caplog):
    # Point ledger at an invalid path or make resolve_ledger_path raise
    def bad_resolve():
        raise OSError("Disk write failed intentionally")

    monkeypatch.setattr(fleet_test, "resolve_ledger_path", bad_resolve)

    mock_post.return_value = {
        "model": "deepseek/deepseek-chat",
        "choices": [{"message": {"content": "Response succeeded"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }

    with caplog.at_level(logging.WARNING):
        res = fleet_test.call_openrouter(
            key_name="OPENROUTER_TEST",
            system="sys",
            prompt="usr",
            model="deepseek/deepseek-chat",
        )

    # Dispatch MUST succeed
    assert "error" not in res
    assert res["content"] == "Response succeeded"
    assert "Failed to record fleet usage to ledger" in caplog.text


def test_concurrent_ledger_logging(tmp_path, monkeypatch):
    import concurrent.futures

    ledger_path = tmp_path / "ledger" / "fleet_usage.jsonl"
    monkeypatch.setenv("FLEET_USAGE_LEDGER", str(ledger_path))

    def write_one(i):
        fleet_test.log_fleet_usage(
            provider="ollama-cloud",
            lane=f"OLLAMA_WORKER_{i}",
            model="gemma4:31b-cloud",
            input_tokens=100 + i,
            output_tokens=50 + i,
            exact=True,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(write_one, range(50)))

    lines = [ln.strip() for ln in ledger_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 50
    lanes = {json.loads(ln)["lane"] for ln in lines}
    assert len(lanes) == 50

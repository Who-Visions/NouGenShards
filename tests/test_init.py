"""Unit tests for NouGen adaptive onboarding and architecture compiler."""
import json
import pytest
from pathlib import Path
from nougen_shards import init
from nougen_shards import cli


def test_discover_hardware():
    hw = init.discover_hardware()
    assert "os" in hw
    assert "arch" in hw
    assert "python" in hw
    assert isinstance(hw.get("vram_mb"), int)


def test_discover_local_ai():
    ai = init.discover_local_ai()
    assert "ollama_alive" in ai
    assert isinstance(ai.get("ollama_models"), list)


def test_run_adaptive_onboarding_non_interactive(tmp_path, monkeypatch):
    fake_nougen_root = tmp_path / ".nougen"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    res = init.run_adaptive_onboarding(
        interactive=False,
        defaults={
            "operator_name": "TestOperator",
            "mission": "engineering",
            "priority": "local_first",
            "autonomy": "safe_autonomous",
            "expose_mcp": True,
        }
    )

    assert res["profile_name"] == "TestOperator-engineering"
    assert res["routing_policy"] == "local_first"
    assert (fake_nougen_root / "profile.json").exists()

    with open(fake_nougen_root / "profile.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["operator"]["name"] == "TestOperator"
        assert data["routing_policy"] == "local_first"


def test_cmd_init_no_onboarding(capsys):
    class Args:
        defaults = False
        no_onboarding = True
        json = True
        command = "init"

    cli.cmd_init(Args())
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["status"] == "ok"

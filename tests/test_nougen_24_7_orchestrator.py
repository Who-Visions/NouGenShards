from types import SimpleNamespace
import json

import pytest

from tools import nougen_24_7_orchestrator as orchestrator


def test_run_nougen_hi_probe_returns_identity_and_fleet_pulse(monkeypatch):
    report = {
        "identity": {"host": "WhoArt", "machine_id": "f673bc418baf"},
        "fleet_pulse": {"blade1tb": True, "whoart": True},
    }
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps(report), stderr="")

    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)

    assert orchestrator.run_nougen_hi_probe() == report
    args, kwargs = calls[0]
    assert args[1:] == ["-m", "nougen_shards.cli", "hi", "--json"]
    assert kwargs["timeout"] == 30
    assert kwargs["cwd"] == str(orchestrator.WORKSPACE_ROOT)


def test_run_nougen_hi_probe_rejects_invalid_json(monkeypatch):
    monkeypatch.setattr(
        orchestrator.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="not json", stderr=""),
    )

    with pytest.raises(RuntimeError, match="invalid JSON"):
        orchestrator.run_nougen_hi_probe()

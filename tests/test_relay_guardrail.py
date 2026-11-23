import json
import re
import sys

import pytest

from nougen_shards import relay_guardrail as rg


def test_strict_default_and_bypass(monkeypatch):
    monkeypatch.delenv(rg.HARDCADE_STRICT_ENV, raising=False)
    assert rg.is_hardcade_strict() is True
    for off in ("0", "false", "OFF", "disabled"):
        monkeypatch.setenv(rg.HARDCADE_STRICT_ENV, off)
        assert rg.is_hardcade_strict() is False
    monkeypatch.setenv(rg.HARDCADE_STRICT_ENV, "0")
    ok, msg = rg.verify_closure_evidence("x")
    assert ok and "BYPASS" in msg


def test_verify_rejects_missing_artifact(monkeypatch, tmp_path):
    monkeypatch.delenv(rg.HARDCADE_STRICT_ENV, raising=False)
    assert rg.verify_closure_evidence("x")[0] is False
    ok, msg = rg.verify_closure_evidence("x", str(tmp_path / "nope.txt"))
    assert not ok and "does not exist" in msg


def test_verify_runs_test_command(monkeypatch, tmp_path):
    monkeypatch.delenv(rg.HARDCADE_STRICT_ENV, raising=False)
    art = tmp_path / "a.txt"
    art.write_text("x")
    good = f'"{sys.executable}" -c "raise SystemExit(0)"'
    bad = f'"{sys.executable}" -c "raise SystemExit(3)"'
    assert rg.verify_closure_evidence("x", str(art), good)[0] is True
    ok, msg = rg.verify_closure_evidence("x", str(art), bad)
    assert not ok and "exit 3" in msg


def test_safe_ack_leg_writes_evidence(monkeypatch, tmp_path):
    monkeypatch.delenv(rg.HARDCADE_STRICT_ENV, raising=False)
    monkeypatch.setattr(rg, "RELAY_ROOT", tmp_path)
    (tmp_path / "leg1.json").write_text(json.dumps({"status": "open"}))
    art = tmp_path / "a.txt"
    art.write_text("x")
    assert rg.safe_ack_leg("leg1", str(art), "done") is True
    data = json.loads((tmp_path / "leg1.json").read_text())
    assert data["status"] == "acked"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", data["resolved_at"])
    assert data["evidence_tuple"]["observer"] == "Phoebus"


def test_safe_ack_leg_refuses_without_evidence(monkeypatch, tmp_path):
    monkeypatch.delenv(rg.HARDCADE_STRICT_ENV, raising=False)
    monkeypatch.setattr(rg, "RELAY_ROOT", tmp_path)
    (tmp_path / "leg1.json").write_text(json.dumps({"status": "open"}))
    with pytest.raises(rg.HardcadeViolationError):
        rg.safe_ack_leg("leg1", str(tmp_path / "missing"), "n")
    assert json.loads((tmp_path / "leg1.json").read_text())["status"] == "open"
    with pytest.raises(FileNotFoundError):
        rg.safe_ack_leg("ghost", "x", "n")

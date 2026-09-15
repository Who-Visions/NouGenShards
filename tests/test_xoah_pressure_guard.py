"""/xoah/pressure and /xoah/throne answer a logged, structured 503 instead of a
bare 500 (fleet verification 9/14/2026: xoah_pressure threw a bare 500 after #379
guarded only /xoah/ask)."""
import json
import os
import tempfile

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("gradio")
pytest.importorskip("mcp")

_tmp = tempfile.mkdtemp(prefix="ngs_xoah_pressure_")
os.environ.setdefault("NGS_NODE_TOKEN", "test-xoah-token")
os.environ.setdefault("NOUGEN_HOME", _tmp)
os.environ.setdefault("NOUGEN_VAULT_DIR", os.path.join(_tmp, ".vault"))

import app as node  # noqa: E402


def _boom(*_a, **_k):
    raise RuntimeError("grid offline")


def test_pressure_failure_is_a_structured_503(monkeypatch):
    monkeypatch.setattr(node.canon_pressure, "pressure", _boom)
    out = node.xoah_pressure_endpoint(node.XoahPressureRequest(candidate="the ferry sails at night"))
    assert out.status_code == 503
    assert json.loads(out.body) == {"verdict": "UNAVAILABLE", "errors": ["pressure: RuntimeError"]}


def test_pressure_success_passes_through(monkeypatch):
    monkeypatch.setattr(node.canon_pressure, "pressure", lambda *_a, **_k: {"verdict": "UNKNOWN"})
    out = node.xoah_pressure_endpoint(node.XoahPressureRequest(candidate="the ferry sails at night"))
    assert out == {"verdict": "UNKNOWN"}


def test_guard_logs_the_traceback(monkeypatch, caplog):
    caplog.set_level("ERROR")
    out = node._xoah_guarded("throne", _boom)
    assert out.status_code == 503 and json.loads(out.body)["errors"] == ["throne: RuntimeError"]
    assert any("xoah/throne failed" in r.getMessage() and r.exc_info for r in caplog.records)

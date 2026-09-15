"""/xoah/ask degrades with a logged, reported error instead of a bare 500,
and hands Rhea the real pressure verdict (the key is `verdict`, not `primary`)."""
import asyncio
import os
import tempfile

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("gradio")
pytest.importorskip("mcp")

_tmp = tempfile.mkdtemp(prefix="ngs_xoah_ask_")
os.environ.setdefault("NGS_NODE_TOKEN", "test-xoah-token")
os.environ.setdefault("NOUGEN_HOME", _tmp)
os.environ.setdefault("NOUGEN_VAULT_DIR", os.path.join(_tmp, ".vault"))

import app as node  # noqa: E402


@pytest.fixture
def rhea(monkeypatch):
    seen = {}

    async def fake(prompt):
        seen["prompt"] = prompt
        return {"answer": "ok", "brain": "stub"}

    monkeypatch.setattr(node, "_ask_rhea_bounded", fake)
    monkeypatch.setattr(node.throne_governance, "evaluate", lambda *_a, **_k: {"mode": "OBSERVE"})
    return seen


def _ask(prompt="does the ferry sail at night"):
    return asyncio.run(node.xoah_ask_endpoint(node.XoahAskRequest(prompt=prompt)))


def test_pressure_failure_is_reported_not_raised(rhea, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("grid offline")
    monkeypatch.setattr(node.canon_pressure, "pressure", boom)
    out = _ask()
    assert out["answer"] == "ok"
    assert out["errors"] == ["pressure: RuntimeError"]
    assert "Canon Verdict: UNKNOWN" in rhea["prompt"]


def test_rhea_failure_is_reported_not_raised(monkeypatch):
    async def down(_prompt):
        raise ConnectionError("lane refused")
    monkeypatch.setattr(node, "_ask_rhea_bounded", down)
    monkeypatch.setattr(node.throne_governance, "evaluate", lambda *_a, **_k: {})
    monkeypatch.setattr(node.canon_pressure, "pressure", lambda *_a, **_k: {"verdict": "UNKNOWN"})
    out = _ask()
    assert out["answer"] is None and out["errors"] == ["rhea: ConnectionError"]


def test_rhea_sees_the_pressure_verdict(rhea, monkeypatch):
    monkeypatch.setattr(node.canon_pressure, "pressure", lambda *_a, **_k: {"verdict": "FACT_CONFLICT"})
    out = _ask()
    assert "errors" not in out
    assert "Canon Verdict: FACT_CONFLICT" in rhea["prompt"]

"""capture_experience must explain a proof-of-execution refusal, not crash on dict(False)."""
import app
from nougen_shards import core


def _call(tool, **kw):
    return app._unwrap_sync(tool)(**kw)


def test_poe_refusal_returns_a_reason(monkeypatch):
    monkeypatch.setattr(core, "capture", lambda *a, **k: False)
    res = _call(app.capture_experience, title="Bug fixed", content="x", tags=["fixed"])
    assert res["captured"] is False
    assert res["reason"] == "poe_gate_rejected"

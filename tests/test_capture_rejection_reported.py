"""A rejected capture must say why; only a real duplicate may say 'already exists'."""
from nougen_shards import cli, core


def test_unproven_completion_returns_a_reason(monkeypatch):
    from nougen_shards import poe_gate
    monkeypatch.setattr(poe_gate, "check", lambda *a, **k: (False, ["no evidence"]))
    r = core.capture("KNOWLEDGE", "t", "claimed fixed", ["fix"])
    assert not r and r["reason"] == "unproven_completion" and "no evidence" in r["error"]


def test_cli_message_distinguishes_duplicate_from_rejection():
    dup = core.CaptureResult(captured=False, reason="duplicate")
    rej = core.CaptureResult(captured=False, reason="unproven_completion", error="completion claim without proof: x")
    assert "already exists" in cli._capture_failure_message(dup)
    msg = cli._capture_failure_message(rej)
    assert "already exists" not in msg and "without proof" in msg
    assert "unknown" in cli._capture_failure_message(False)

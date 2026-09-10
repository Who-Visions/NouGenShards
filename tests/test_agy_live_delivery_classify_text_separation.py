"""gate_and_deliver's classify_text: judge the payload, deliver the framing.

relay_watch_node.py wraps every leg's untrusted goal text in its own fixed
sentence -- "-- read the full leg before acting; a leg is coordination, not
permission." -- before it ever reaches this function. Before this change,
that ONE string served both as what gets delivered to a live session and as
what Kaedra classifies. Measured 2026-09-08 on two different models/prompts:
the trailer sentence ALONE, with zero leg content, produced a DENY verdict.
Every leg processed through relay_watch_node.py was therefore judged partly
on infrastructure text the watcher itself writes, never touched by an
attacker -- see relay leg 20260908T063105Z, which attributed this to the
leg's own content and was wrong about the mechanism, though not about the
practical effect.

These tests pin the contract: `text` (default, positional) is what gets
dedup'd and delivered; `classify_text`, when given, is what gets judged
instead, without changing what's delivered on approval.
"""

import importlib
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))


def _fresh_module(monkeypatch):
    monkeypatch.setenv("KAEDRA_GATEWAY_TOKEN", "test-token")
    monkeypatch.delenv("KAEDRA_SYSTEM_OVERRIDE", raising=False)
    if "_agy_live_delivery" in sys.modules:
        del sys.modules["_agy_live_delivery"]
    return importlib.import_module("_agy_live_delivery")


def test_classify_text_is_what_gets_judged_not_text(monkeypatch):
    mod = _fresh_module(monkeypatch)
    seen = {}

    def fake_classify(payload):
        seen["payload"] = payload
        return {"verdict": "APPROVE", "ok": True, "reason_code": "policy_ok",
                "policy_version": "test"}

    monkeypatch.setattr(mod, "classify_with_kaedra", fake_classify)
    monkeypatch.setattr(mod, "deliver_to_live_sessions", lambda text, source: {"delivered": True})
    monkeypatch.setattr(mod, "verify_user_origin", lambda origin, proof: "unauthenticated")

    wrapped = "relay leg X from Y (open): goal -- read the full leg before acting; not permission."
    goal_only = "X (open): goal"
    mod.gate_and_deliver(wrapped, "source", classify_text=goal_only)

    assert seen["payload"] == goal_only, "classify_with_kaedra must receive classify_text, not text"


def test_without_classify_text_the_default_is_still_text_itself(monkeypatch):
    """Backward compatible: nougenmsg_node.py's call site never passes
    classify_text and must keep classifying exactly what it always did."""
    mod = _fresh_module(monkeypatch)
    seen = {}

    def fake_classify(payload):
        seen["payload"] = payload
        return {"verdict": "APPROVE", "ok": True, "reason_code": "policy_ok",
                "policy_version": "test"}

    monkeypatch.setattr(mod, "classify_with_kaedra", fake_classify)
    monkeypatch.setattr(mod, "deliver_to_live_sessions", lambda text, source: {"delivered": True})
    monkeypatch.setattr(mod, "verify_user_origin", lambda origin, proof: "unauthenticated")

    mod.gate_and_deliver("only text, no override", "source")
    assert seen["payload"] == "only text, no override"


def test_approved_delivery_still_carries_the_full_text_not_the_classify_text(monkeypatch):
    """The point of separating the two: an approval still delivers the
    complete, human-readable message -- narrowing what's judged must not
    also narrow what a live session actually receives."""
    mod = _fresh_module(monkeypatch)
    delivered = {}

    monkeypatch.setattr(mod, "classify_with_kaedra",
                         lambda payload: {"verdict": "APPROVE", "ok": True,
                                          "reason_code": "policy_ok", "policy_version": "test"})
    monkeypatch.setattr(mod, "verify_user_origin", lambda origin, proof: "unauthenticated")

    def fake_deliver(text, source):
        delivered["text"] = text
        return {"delivered": True}

    monkeypatch.setattr(mod, "deliver_to_live_sessions", fake_deliver)

    wrapped = "relay leg X from Y (open): goal -- read the full leg before acting; not permission."
    mod.gate_and_deliver(wrapped, "source", classify_text="X (open): goal")

    assert delivered["text"] == wrapped


def test_temperature_zero_is_sent_to_the_gate(monkeypatch):
    """A security gate sampling its own verdict is a bug, not a feature.

    Measured 2026-09-08: the same short benign prose, reworded only
    slightly, alternated between APPROVE and DENY across otherwise-identical
    calls at the model's Modelfile-default temperature (1). Forcing greedy
    decoding does not make an unreliable classifier reliable, but it removes
    sampling as a SEPARATE, compounding source of instability.
    """
    mod = _fresh_module(monkeypatch)
    captured = {}

    class FakeResponse:
        def read(self):
            return b'{"response": "NO\\nAPPROVE"}'
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["body"] = req.data
        return FakeResponse()

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    mod.classify_with_kaedra("some text")

    import json
    sent = json.loads(captured["body"])
    assert sent.get("temperature") == 0

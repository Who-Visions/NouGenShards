"""Sender identity resolves at runtime: session id, session title, lane by surface,
the display label, and forwarded envelopes that keep their upstream session."""
import json

import pytest

from nougen_shards import nougenmsg
from nougen_shards.nougenmsg import NouGenMsgBus, display_sender, resolve_session_title

_SID = "0123abcd-1111-2222-3333-444455556666"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for var in ("NOUGEN_LANE", "NOUGEN_AGENT", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT",
                "NOUGEN_SESSION", "CLAUDE_CODE_SESSION_ID", "NOUGEN_SESSION_TITLE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NOUGEN_CLAUDE_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("NOUGEN_CC_SESSIONS", str(tmp_path / "cc_sessions.json"))
    monkeypatch.setattr(nougenmsg, "get_current_node", lambda: "node-a")


def _write_session(tmp_path, sid, name):
    d = tmp_path / "sessions"
    d.mkdir(exist_ok=True)
    (d / "100.json").write_text(json.dumps({"sessionId": sid, "name": name}), encoding="utf-8")


def test_session_id_resolves_from_env_without_being_supplied(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", _SID)
    env = NouGenMsgBus._origin_envelope({})
    assert env["session_id"] == _SID
    assert env["provenance_state"] == "asserted"
    assert env["unknown_reason"] is None


def test_no_session_anywhere_stays_unknown():
    env = NouGenMsgBus._origin_envelope({})
    assert env["session_id"] is None
    assert env["unknown_reason"] == "session_identity_not_supplied"


def test_title_from_env_beats_registry(monkeypatch, tmp_path):
    _write_session(tmp_path, _SID, "From Registry")
    monkeypatch.setenv("NOUGEN_SESSION_TITLE", "From Env")
    assert resolve_session_title(_SID) == "From Env"


def test_title_from_claude_session_registry(monkeypatch, tmp_path):
    _write_session(tmp_path, _SID, "Planner Session")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", _SID)
    env = NouGenMsgBus._origin_envelope({})
    assert env["session_title"] == "Planner Session"


def test_missing_title_is_empty_not_a_guess(monkeypatch, tmp_path):
    _write_session(tmp_path, "some-other-session", "Other")
    assert resolve_session_title(_SID) == ""
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", _SID)
    assert NouGenMsgBus._origin_envelope({})["session_title"] is None


@pytest.mark.parametrize("entry,lane", [
    ("claude-desktop", "claude-app"), ("cli", "claude-cli"),
    ("sdk-py", "claude-sdk"), ("sdk-ts", "claude-sdk"), ("mystery", "claude"),
])
def test_lane_splits_by_claude_code_surface(monkeypatch, entry, lane):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", entry)
    assert NouGenMsgBus._sender_lane({}) == lane


def test_agy_and_codex_aliases_survive(monkeypatch):
    assert NouGenMsgBus._sender_lane({"lane": "antigravity"}) == "agy"
    assert NouGenMsgBus._sender_lane({"lane": "codex"}) == "codex"
    assert NouGenMsgBus._sender_lane({"lane": "claude-cli"}) == "claude-cli"


def test_display_sender_format_title_and_machine_id():
    origin = {"original_sender": "node-a-claude-app", "machine": "node-a",
              "session_title": "Planner Session", "session_id": _SID,
              "machine_id": "deadbeefcafef00d", "origin_trust": "stamped"}
    assert display_sender(origin) == "node-a-claude-app · Planner Session [deadbeef]"


def test_display_sender_uses_sid8_without_title_and_keeps_asserted_suffix():
    origin = {"original_sender": "x", "machine": "m", "session_id": _SID,
              "machine_id": "unknown", "origin_trust": "forwarded-unverified"}
    assert display_sender(origin) == f"m/x · {_SID[:8]} (asserted)"


def test_forwarded_envelope_keeps_upstream_session(monkeypatch, tmp_path):
    _write_session(tmp_path, _SID, "Receiver Local Title")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", _SID)
    supplied = {"machine": "node-b", "relay_path": ["node-b"], "session_id": "up-stream-sid",
                "session_title": "Upstream Title", "original_sender": "node-b-claude-app"}
    env = NouGenMsgBus._origin_envelope(supplied, forwarded=True)
    assert env["session_id"] == "up-stream-sid"
    assert env["session_title"] == "Upstream Title"


def test_forwarded_envelope_without_session_is_not_stamped_with_receivers(monkeypatch, tmp_path):
    _write_session(tmp_path, _SID, "Receiver Local Title")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", _SID)
    env = NouGenMsgBus._origin_envelope({"machine": "node-b", "relay_path": ["node-b"]}, forwarded=True)
    assert env["session_id"] is None
    assert env["session_title"] is None


# --- review fixes: tenant scope and the banner/authorization split ----------

def test_tenant_request_never_reads_owner_session_title(monkeypatch, tmp_path):
    _write_session(tmp_path, _SID, "Owner Private Title")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", _SID)
    monkeypatch.setenv("NOUGEN_SESSION_TITLE", "Owner Env Title")
    monkeypatch.setattr(nougenmsg, "_tenant_scope", lambda: True)
    assert resolve_session_title(_SID) == ""
    env = NouGenMsgBus._origin_envelope({})
    assert env["session_id"] is None
    assert env["session_title"] is None


def _delivery_module(monkeypatch):
    import sys
    from pathlib import Path
    tools = str(Path(__file__).resolve().parents[1] / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import _agy_live_delivery as mod
    return mod


def test_banner_label_never_feeds_origin_authorization(monkeypatch):
    """A session title containing "chatgpt" must not trip verify_user_origin."""
    mod = _delivery_module(monkeypatch)
    calls = {"classified": 0, "delivered": []}

    def fake_classify(_text):
        calls["classified"] += 1
        return {"verdict": "DENY", "ok": True, "reason_code": "t", "detail": "", "policy_version": "1"}

    monkeypatch.setattr(mod, "classify_with_kaedra", fake_classify)
    monkeypatch.setattr(mod, "deliver_to_live_sessions",
                        lambda text, label: calls["delivered"].append(label) or {})
    out = mod.gate_and_deliver("unique payload one", "peer-node-claude",
                               label="peer-node-claude · Debug ChatGPT integration")
    assert calls["classified"] == 1          # judged by Kaedra: no user_verified bypass
    assert out["kaedra_approved"] is False
    assert calls["delivered"] == []


def test_banner_label_is_what_the_session_sees(monkeypatch):
    mod = _delivery_module(monkeypatch)
    seen = []
    monkeypatch.setattr(mod, "classify_with_kaedra",
                        lambda _t: {"verdict": "APPROVE", "ok": True, "reason_code": "t", "policy_version": "1"})
    monkeypatch.setattr(mod, "deliver_to_live_sessions", lambda text, label: seen.append(label) or {})
    mod.gate_and_deliver("unique payload two", "raw-sender", label="node-a-claude-app · Planner [deadbeef]")
    assert seen == ["node-a-claude-app · Planner [deadbeef]"]
    mod.gate_and_deliver("unique payload three", "raw-sender")
    assert seen[-1] == "raw-sender"

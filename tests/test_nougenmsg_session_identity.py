"""Sender identity extras on top of resolve_session (PR 1187)."""
import pytest
from nougen_shards import nougenmsg as nm


@pytest.mark.parametrize("var", ["CODEX_SESSION_ID", "GEMINI_SESSION_ID", "ANTIGRAVITY_SESSION_ID", "NOUGEN_SESSION_ID"])
def test_other_agents_session_ids_resolve(monkeypatch, var):
    for v in nm._SESSION_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv(var, "sid-xyz")
    assert nm.resolve_session() == "sid-xyz"


def test_claude_id_still_wins_over_codex(monkeypatch):
    for v in nm._SESSION_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "claude-1")
    monkeypatch.setenv("CODEX_SESSION_ID", "codex-1")
    assert nm.resolve_session() == "claude-1"


def test_unknown_machine_is_not_a_prefix():
    label = nm.display_sender({"original_sender": "claude-app/g-x", "machine": "unknown",
                               "origin_trust": "forwarded-unverified"})
    assert not label.startswith("unknown/")
    assert "machine unstamped" in label and label.endswith("(asserted)")


def test_known_machine_unchanged():
    label = nm.display_sender({"original_sender": "claude", "machine": "blade", "origin_trust": "stamped"})
    assert label.startswith("blade/claude") and "unstamped" not in label

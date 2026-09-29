import pytest

from nougen_shards import nougenmsg
from nougen_shards.nougenmsg import NouGenMsgBus


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("NOUGEN_LANE", "NOUGEN_AGENT", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(nougenmsg, "get_current_node", lambda: "blade")


def test_explicit_lane_labels_sender_node_lane():
    env = NouGenMsgBus._origin_envelope({"lane": "codex"})
    assert env["lane"] == "codex"
    assert env["original_sender"] == "blade-codex"


@pytest.mark.parametrize("raw,short", [
    ("antigravity", "agy"), ("nougen-agy", "agy"), ("claude-cli", "claude"), ("Ollama", "ollama"),
])
def test_lane_is_normalised_without_nougen_prefix(raw, short):
    env = NouGenMsgBus._origin_envelope({"lane": raw})
    assert env["original_sender"] == f"blade-{short}"


def test_lane_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("NOUGEN_AGENT", "antigravity")
    assert NouGenMsgBus._origin_envelope()["original_sender"] == "blade-agy"
    monkeypatch.setenv("NOUGEN_LANE", "ollama")  # NOUGEN_LANE wins over NOUGEN_AGENT
    assert NouGenMsgBus._origin_envelope()["original_sender"] == "blade-ollama"


def test_claude_code_marker_beats_machine_wide_agent(monkeypatch):
    monkeypatch.setenv("NOUGEN_AGENT", "antigravity")  # set box-wide on whoart
    monkeypatch.setenv("CLAUDECODE", "1")
    assert NouGenMsgBus._origin_envelope()["original_sender"] == "blade-claude"


def test_unknown_lane_keeps_legacy_label():
    env = NouGenMsgBus._origin_envelope()
    assert env["lane"] is None
    assert env["original_sender"] == "nougen-blade"


def test_supplied_sender_is_never_overwritten_on_a_hop():
    env = NouGenMsgBus._origin_envelope({"lane": "codex", "original_sender": "whoart-agy"})
    assert env["original_sender"] == "whoart-agy"

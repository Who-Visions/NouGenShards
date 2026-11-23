"""Discovery failure must not pick a model too big for the node's card."""
import pytest

from nougen_shards import nougenmsg
from nougen_shards.nougenmsg import AgentPinger


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_OLLAMA_PICKS_FILE", str(tmp_path / "picks.json"))
    monkeypatch.delenv("NOUGEN_LOCAL_E2B_MODEL", raising=False)
    monkeypatch.setattr(nougenmsg, "get_current_node", lambda: "thisnode")
    monkeypatch.setattr(AgentPinger, "_PICK_CACHE", {})
    yield


def _inventory(monkeypatch, tags):
    calls = []

    def fake(node, is_local):
        calls.append(node)
        return [{"name": t} for t in tags] if tags is not None else []
    monkeypatch.setattr(AgentPinger, "_ollama_installed", staticmethod(fake))
    return calls


def test_ssh_outage_reuses_last_good_pick_not_the_oversized_fallback(monkeypatch):
    _inventory(monkeypatch, ["gemma4:e2b-qat", "gemma4:e2b"])
    assert AgentPinger._default_ollama_model("whoart") == "gemma4:e2b-qat"
    AgentPinger._PICK_CACHE.clear()          # TTL expired
    _inventory(monkeypatch, None)            # ssh down: no tags
    assert AgentPinger._default_ollama_model("whoart") == "gemma4:e2b-qat"


def test_never_reached_node_still_gets_the_generic_fallback(monkeypatch):
    _inventory(monkeypatch, None)
    assert AgentPinger._default_ollama_model("brand-new") == AgentPinger._OLLAMA_FALLBACK


def test_pick_is_cached_so_repeat_pings_skip_the_ssh_round_trip(monkeypatch):
    calls = _inventory(monkeypatch, ["gemma4:e2b"])
    for _ in range(3):
        assert AgentPinger._default_ollama_model("blade") == "gemma4:e2b"
    assert calls == ["blade"]


def test_last_good_is_per_node(monkeypatch):
    _inventory(monkeypatch, ["gemma4:e2b-qat"])
    AgentPinger._default_ollama_model("whoart")
    AgentPinger._PICK_CACHE.clear()
    _inventory(monkeypatch, None)
    assert AgentPinger._default_ollama_model("blade") == AgentPinger._OLLAMA_FALLBACK

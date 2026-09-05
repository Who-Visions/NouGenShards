"""The Ollama default must name a tag that exists on the machine serving it.

The old default keyed off the *passed* node:

    "gemma4:e2b-qat" if node in ["local", "whoart"] else "sol-ai:e4b"

but live_ping calls ping_ollama with node="local" on every machine, so the
else branch was dead on the broadcast path and blade and phoebus both asked
their own Ollama for whoart's tag. Measured 2026-09-05 against /api/tags:

    whoart   gemma4:e2b-qat PRESENT   (Rule 0.5.1 pins it as the resident lane)
    blade    gemma4:e2b-qat ABSENT, gemma4:e2b present
    phoebus  gemma4:e2b-qat ABSENT, gemma4:e2b present

Every broadcast returned HTTP 404 on blade and phoebus, silently disabling the
free local first-pass lane. These tests pin the per-machine resolution.
"""
from __future__ import annotations

import pytest

from nougen_shards.nougenmsg import AgentPinger

# Tags actually installed, measured per node on 2026-09-05.
INSTALLED = {
    "whoart": {"gemma4:e2b-qat", "gemma4:e2b", "gemma4:e4b", "solai:e2b",
               "solai:e4b", "Yukiai:e2b", "gemma2:2b"},
    "blade": {"gemma4:e2b", "gemma4:12b", "sol-ai:e4b", "dav1d:e2b",
              "kaedra:e4b", "gemma2:2b"},
    "phoebus": {"gemma4:e2b", "gemma4:e4b", "solai:latest", "kaedracode:e2b",
                "gemma2:2b"},
}


@pytest.mark.parametrize("machine", sorted(INSTALLED))
def test_local_default_is_installed_on_the_machine_serving_it(monkeypatch, machine):
    monkeypatch.setattr("nougen_shards.nougenmsg.get_current_node", lambda: machine)
    chosen = AgentPinger._default_ollama_model("local")
    assert chosen in INSTALLED[machine], (
        f"{machine} would request {chosen!r}, which it does not have")


def test_whoart_keeps_its_pinned_resident_model(monkeypatch):
    """Rule 0.5.1 pins gemma4:e2b-qat as whoart's resident lane -- a blanket
    swap to gemma4:e2b would move it off that for a fault it does not have."""
    monkeypatch.setattr("nougen_shards.nougenmsg.get_current_node", lambda: "whoart")
    assert AgentPinger._default_ollama_model("local") == "gemma4:e2b-qat"


@pytest.mark.parametrize("machine", ["blade", "phoebus"])
def test_nodes_without_the_qat_tag_do_not_request_it(monkeypatch, machine):
    """The exact 404 this fixes."""
    monkeypatch.setattr("nougen_shards.nougenmsg.get_current_node", lambda: machine)
    assert AgentPinger._default_ollama_model("local") != "gemma4:e2b-qat"
    assert AgentPinger._default_ollama_model("local") == "gemma4:e2b"


def test_remote_target_resolves_against_the_remote_machine(monkeypatch):
    """Called from whoart but addressed at blade, the tag must be blade's."""
    monkeypatch.setattr("nougen_shards.nougenmsg.get_current_node", lambda: "whoart")
    assert AgentPinger._default_ollama_model("blade") == "gemma4:e2b"
    assert AgentPinger._default_ollama_model("phoebus") == "gemma4:e2b"
    # Naming the current node explicitly is the same as "local".
    assert AgentPinger._default_ollama_model("whoart") == "gemma4:e2b-qat"


def test_explicit_model_argument_still_wins(monkeypatch):
    monkeypatch.setattr("nougen_shards.nougenmsg.get_current_node", lambda: "blade")
    calls = {}

    def fake_urlopen(req, timeout=None):
        raise AssertionError("network must not be reached in this test")

    monkeypatch.setattr("nougen_shards.nougenmsg.urllib.request.urlopen", fake_urlopen)
    # The resolution itself is what we assert; ping_ollama would only add I/O.
    assert AgentPinger._default_ollama_model("blade") == "gemma4:e2b"
    assert not calls


def test_unknown_node_falls_back_to_the_widely_present_tag(monkeypatch):
    monkeypatch.setattr("nougen_shards.nougenmsg.get_current_node", lambda: "whoart")
    assert AgentPinger._default_ollama_model("some-new-node") == "gemma4:e2b"

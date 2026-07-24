"""Roster integrity tests for the NouGen fleet (agents.py)."""
from unittest.mock import MagicMock, patch

import pytest

from nougen_shards import agents


EXPECTED_ROSTER = {"Sharder", "Remember", "Kronos", "DavOs", "Sol-Ai", "NouGen", "Griot", "Rhea", "Kaedra", "Iris"}


def test_roster_names():
    assert set(agents.ROSTER) == EXPECTED_ROSTER


def test_specs_complete():
    for spec in agents.ROSTER.values():
        assert spec.name and spec.role and spec.motto
        assert len(spec.system_prompt) > 50
        assert spec.default_model  # every player binds to a local model


def test_get_agent_case_insensitive():
    assert agents.get_agent("sol-ai").name == "Sol-Ai"
    assert agents.get_agent("NOUGEN").name == "NouGen"
    assert agents.get_agent("ghost") is None


def test_remember_speaks_anghkooey():
    assert "Anghkooey" in agents.ROSTER["Remember"].system_prompt
    assert agents.ROSTER["Remember"].motto == "Anghkooey."


def test_list_roster_renders_all():
    depth_chart = agents.list_roster()
    for name in EXPECTED_ROSTER:
        assert name in depth_chart


def test_run_agent_unknown_name_fails_soft():
    out = agents.run_agent("nobody", "hi")
    assert out.startswith("[roster]")
    assert "nobody" in out


# ---------------------------------------------------------------------------
# Happy path. Previously untested, so a run_agent that always returned the
# "[roster] ..." soft-fail string passed the whole suite (mutation audit).
# ---------------------------------------------------------------------------

@pytest.fixture(name="agent_name")
def fixture_agent_name():
    """Take a real roster member rather than pinning one by name."""
    return sorted(agents.ROSTER)[0]


def _fake_ollama(reply, alive=True):
    client = MagicMock()
    client.is_alive.return_value = alive
    client.chat.return_value = reply
    factory = MagicMock(return_value=client)
    return factory, client


def test_run_agent_returns_local_model_output(agent_name):
    """A live local lane must return the model's answer, not a roster message."""
    spec = agents.get_agent(agent_name)
    factory, client = _fake_ollama("local answer")

    with patch("nougen_shards.models_client.OllamaClient", factory):
        out = agents.run_agent(agent_name, "what is the play?")

    assert out == "local answer"
    assert not out.startswith("[roster]")
    assert not out.startswith("[gatekeeper]")

    client.chat.assert_called_once()
    model, messages = client.chat.call_args.args
    assert model == spec.default_model
    assert messages == [
        {"role": "system", "content": spec.system_prompt},
        {"role": "user", "content": "what is the play?"},
    ]


def test_run_agent_model_override_beats_the_spec_default(agent_name):
    """An explicit model argument must reach the local client."""
    spec = agents.get_agent(agent_name)
    override = f"{spec.default_model}-override"
    factory, client = _fake_ollama("overridden")

    with patch("nougen_shards.models_client.OllamaClient", factory):
        out = agents.run_agent(agent_name, "hi", model=override)

    assert out == "overridden"
    assert client.chat.call_args.args[0] == override


def test_run_agent_is_case_insensitive_on_the_happy_path(agent_name):
    """Lookup case must not change which agent actually runs."""
    spec = agents.get_agent(agent_name)
    factory, client = _fake_ollama("cased answer")

    with patch("nougen_shards.models_client.OllamaClient", factory):
        out = agents.run_agent(agent_name.upper(), "hi")

    assert out == "cased answer"
    assert client.chat.call_args.args[0] == spec.default_model


def test_run_agent_blocks_gated_prompts_before_touching_a_model(agent_name):
    """The gatekeeper verdict must short-circuit ahead of any model call."""
    factory, client = _fake_ollama("should never be reached")
    blocked = {"allowed": False, "gate": "TEST_GATE", "reason": "denied by test"}

    with patch("nougen_shards.agents.check_mutation_gate", return_value=blocked), \
         patch("nougen_shards.models_client.OllamaClient", factory):
        out = agents.run_agent(agent_name, "rm -rf /")

    assert out.startswith("[gatekeeper]")
    assert "TEST_GATE" in out
    assert "denied by test" in out
    client.chat.assert_not_called()

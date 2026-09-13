"""Proves coach_governor is actually wired into run_agent()'s live dispatch
path, not just tested in isolation: a killed/exhausted scope must deny
BEFORE any Ollama/OpenRouter/cloud client is ever touched."""
import pytest

from nougen_shards import agents
from nougen_shards.coach_governor import CoachGovernor, BudgetExceeded


AGENT_NAME = "Sharder"  # real roster entry, see agents.ROSTER


@pytest.fixture(autouse=True)
def isolated_governor(monkeypatch):
    """run_agent() calls get_default_governor() — swap the process-wide
    singleton for a fresh one per test so tests can't leak state into each
    other via the shared default."""
    fresh = CoachGovernor(telemetry_path=":memory-unused:")
    monkeypatch.setattr(agents, "get_default_governor", lambda: fresh)
    return fresh


def test_kill_switch_blocks_run_agent_before_any_dispatch(monkeypatch, isolated_governor):
    def _boom(*a, **kw):
        raise AssertionError("_dispatch_agent must not run when the lease is denied")

    monkeypatch.setattr(agents, "_dispatch_agent", _boom)
    isolated_governor.set_kill(f"machine/{AGENT_NAME}", "test kill")

    result = agents.run_agent(AGENT_NAME, "hello")

    assert result.startswith("[coach-governor] Blocked:")


def test_exhausted_ceiling_blocks_run_agent_before_any_dispatch(monkeypatch, isolated_governor):
    def _boom(*a, **kw):
        raise AssertionError("_dispatch_agent must not run when budget is exhausted")

    monkeypatch.setattr(agents, "_dispatch_agent", _boom)
    isolated_governor.register_scope(f"machine/{AGENT_NAME}", ceiling=1.0)

    result = agents.run_agent(AGENT_NAME, "a prompt far longer than one character")

    assert result.startswith("[coach-governor] Blocked:")


def test_governor_allows_and_settles_on_successful_dispatch(monkeypatch, isolated_governor):
    monkeypatch.setattr(agents, "_dispatch_agent", lambda *a, **kw: "ok-response")

    result = agents.run_agent(AGENT_NAME, "hello")

    assert result == "ok-response"
    status = isolated_governor.status(f"machine/{AGENT_NAME}")
    assert status["registered"] is True
    assert status["reserved"] == 0.0
    assert status["spent"] == float(len("ok-response"))


def test_governor_settles_zero_on_dispatch_exception(monkeypatch, isolated_governor):
    def _raise(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(agents, "_dispatch_agent", _raise)

    with pytest.raises(RuntimeError):
        agents.run_agent(AGENT_NAME, "hello")

    status = isolated_governor.status(f"machine/{AGENT_NAME}")
    assert status["reserved"] == 0.0  # settled, not left dangling


def test_gatekeeper_block_still_takes_precedence(monkeypatch, isolated_governor):
    """The mutation gate runs before the governor lease — a gatekeeper block
    must not even register a governor charge."""
    monkeypatch.setattr(
        agents, "check_mutation_gate",
        lambda prompt: {"allowed": False, "gate": "test", "reason": "blocked for test"},
    )

    result = agents.run_agent(AGENT_NAME, "delete everything")

    assert result.startswith("[gatekeeper] Blocked")
    status = isolated_governor.status(f"machine/{AGENT_NAME}")
    assert status["registered"] is False

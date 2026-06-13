"""Roster integrity tests for the NouGen fleet (agents.py)."""
from nougen_shards import agents


EXPECTED_ROSTER = {"Sharder", "Remember", "Kronos", "DavOs", "Sol-Ai", "NouGen"}


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

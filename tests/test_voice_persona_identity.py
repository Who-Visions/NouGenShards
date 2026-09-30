import json

import pytest

from nougen_shards import voice_persona as vp

CODEX = "codex"  # canonical: profile Onyx, archetype analyst


def test_normal_result_uses_canonical_profile_and_archetype():
    ident = vp.identity_for(CODEX, 0.9)
    assert ident == {"persona_name": "Onyx", "archetype": "analyst",
                     "source_id": "voice-persona.v1:Onyx:analyst"}


def test_output_shape_is_exactly_the_v1_contract_and_json_serialisable():
    ident = vp.identity_for(CODEX, 0.9)
    assert set(ident) == {"persona_name", "archetype", "source_id"}
    assert json.loads(json.dumps(ident)) == ident


def test_source_id_is_what_the_voice_consumer_pins():
    # NouGenVoice PersonaIdentity requires source_id == "voice-persona.v1:<name>:<archetype>".
    for agent in vp.DEFAULT_AGENTS:
        ident = vp.identity_for(agent, 1.0)
        assert ident["source_id"] == f"voice-persona.v1:{ident['persona_name']}:{ident['archetype']}"


def test_low_confidence_falls_back_to_neutral():
    ident = vp.identity_for(CODEX, 0.3)
    assert ident["archetype"] == vp.NEUTRAL_ARCHETYPE
    assert ident["persona_name"] == "Onyx"  # identity stays; only the overlay is gated
    assert ident["source_id"] == "voice-persona.v1:Onyx:neutral"


def test_low_relevance_falls_back_to_neutral_even_when_confidence_is_high():
    assert vp.identity_for(CODEX, 0.9, relevance=0.5)["archetype"] == vp.NEUTRAL_ARCHETYPE  # 0.45 < 0.6


def test_gate_boundary_matches_gated_archetype_exactly():
    for c, r in ((0.6, 1.0), (0.59, 1.0), (0.8, 0.75), (0.8, 0.74)):
        want = vp.gated_archetype("analyst", c, r)
        assert vp.identity_for(CODEX, c, r)["archetype"] == want, (c, r)


def test_stable_across_calls():
    assert vp.identity_for(CODEX, 0.9, 0.9) == vp.identity_for(CODEX, 0.9, 0.9)


def test_unknown_agent_is_rejected_not_invented():
    with pytest.raises(ValueError, match="unknown agent"):
        vp.identity_for("nobody", 1.0)


@pytest.mark.parametrize("bad", [True, "0.9", None, float("nan"), float("inf"), -0.1, 1.5])
def test_bad_confidence_or_relevance_is_rejected(bad):
    with pytest.raises(ValueError):
        vp.identity_for(CODEX, bad)
    with pytest.raises(ValueError):
        vp.identity_for(CODEX, 0.9, relevance=bad)


def test_agents_override_is_honoured_and_unknown_archetype_goes_neutral(monkeypatch, tmp_path):
    f = tmp_path / "agents.json"
    f.write_text(json.dumps({"scout": {"profile": "Vega", "engine": "kokoro", "voice": "x", "archetype": "not_real"}}))
    monkeypatch.setenv("NOUGEN_VOICE_AGENTS", str(f))
    assert vp.identity_for("scout", 1.0) == {
        "persona_name": "Vega", "archetype": "neutral", "source_id": "voice-persona.v1:Vega:neutral"}


def test_identity_contract_version_is_independent_of_config_version():
    assert vp.IDENTITY_CONTRACT_VERSION == "voice-persona.v1"
    assert "IDENTITY_CONTRACT_VERSION" in vp.identity_for.__globals__

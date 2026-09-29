import itertools
import math

import pytest

from nougen_shards import voice_persona as vp

ENV = dict(
    outcome="success",
    changed=("Added voice_persona module with five archetypes.",),
    verified=("Twelve focused tests pass on Blade.",),
    issues=("Kokoro cannot shape pitch range, so that control is reported unsupported.",),
    next_action="Create the Apollo profile once the backend is up.",
)


def _env(agent, **kw):
    return vp.PostflightEnvelope(agent=agent, **{**ENV, **kw})


def test_five_agents_bound_to_distinct_speakers_and_archetypes():
    b = vp.DEFAULT_AGENTS
    assert len(b) == 5
    assert len({v["voice"] for v in b.values()}) == 5
    assert {v["archetype"] for v in b.values()} == set(vp.ARCHETYPES)
    assert b["claude-code"]["voice"] != b["antigravity"]["voice"]


def test_archetype_masks_exist_in_persona_py():
    from nougen_shards import persona
    for masks in vp.ARCHETYPES.values():
        for m in masks:
            assert persona.get_mask(m) is not None
            assert m in vp.MASK_PROSODY


@pytest.mark.parametrize("agent", list(vp.DEFAULT_AGENTS))
def test_facts_byte_equal_after_extraction(agent):
    env = _env(agent)
    assert vp.extract_facts(vp.plan(env)) == env.facts()


def test_same_payload_is_distinguishable_across_all_five():
    sigs = {a: vp.rhythm_signature(vp.plan(_env(a))) for a in vp.DEFAULT_AGENTS}
    for a, b in itertools.combinations(sigs, 2):
        assert vp.rhythm_distance(sigs[a], sigs[b]) > 0.1, (a, b)


def test_plan_is_deterministic_and_versioned():
    p1, p2 = vp.plan(_env("claude-code")), vp.plan(_env("claude-code"))
    assert p1 == p2 and p1.config_version == vp.CONFIG_VERSION
    assert vp.plan(_env("claude-code", outcome="failure")).fingerprint != p1.fingerprint


def test_outcome_modulates_delivery_not_facts():
    ok, bad = vp.plan(_env("codex")), vp.plan(_env("codex", outcome="failure"))
    assert bad.policy.rate < ok.policy.rate and bad.policy.pause_ms > ok.policy.pause_ms
    assert vp.extract_facts(ok) == vp.extract_facts(bad)


def test_bad_outcome_and_unknown_agent_rejected():
    with pytest.raises(ValueError):
        vp.plan(_env("claude-code", outcome="meh"))
    with pytest.raises(KeyError):
        vp.plan(_env("nobody"))


def test_lowering_reports_unsupported_controls_explicitly():
    req = vp.lower(vp.plan(_env("claude-code")))
    assert req.voice == "am_michael" and req.profile == "Apollo"
    assert req.params == {"speed": vp.plan(_env("claude-code")).policy.rate}
    assert "pitch_range_st" in req.unsupported and "energy" in req.unsupported
    for fact in _env("claude-code").facts():
        for word in fact.rstrip(".").split(" "):
            assert word in req.text


def test_agents_override_from_env(tmp_path, monkeypatch):
    f = tmp_path / "agents.json"
    f.write_text('{"x": {"profile": "X", "engine": "kokoro", "voice": "am_adam", "archetype": "heavy"}}')
    monkeypatch.setenv("NOUGEN_VOICE_AGENTS", str(f))
    assert vp.plan(_env("x")).voice == "am_adam"


def _tone_with_gaps(sr, gaps_ms, tone_ms=300):
    out = []
    for g in gaps_ms + [None]:
        out += [math.sin(2 * math.pi * 220 * i / sr) for i in range(int(sr * tone_ms / 1000))]
        if g:
            out += [0.0] * int(sr * g / 1000)
    return out


def test_measure_pauses_and_drift():
    sr = 8000
    m = vp.measure_pauses(_tone_with_gaps(sr, [400, 400, 400]), sr)
    assert m["pause_count"] == 3 and abs(m["mean_pause_ms"] - 400) <= 40
    p = vp.plan(_env("dav1d"))
    assert vp.drift(p, {"mean_pause_ms": p.policy.pause_ms}) == []
    assert vp.drift(p, {"mean_pause_ms": p.policy.pause_ms * 3})

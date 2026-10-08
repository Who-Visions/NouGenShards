import datetime
import pytest
from nougen_shards import end_of_turn_voice as eov

def test_resolve_end_of_turn_success_deterministic():
    fixed_time = datetime.datetime(2026, 10, 7, 5, 30, tzinfo=datetime.timezone.utc)  # 01:30 EDT
    res1 = eov.resolve_end_of_turn(
        "success",
        changed=["Created end_of_turn_voice.py"],
        verified=["Unit test passes"],
        issues=[],
        next_action="Etching rule 14 into fleet catalog",
        agent="kaedra",
        user_query="end of turn voice must be dynamically resolving",
        now=fixed_time,
    )
    res2 = eov.resolve_end_of_turn(
        "success",
        changed=["Created end_of_turn_voice.py"],
        verified=["Unit test passes"],
        issues=[],
        next_action="Etching rule 14 into fleet catalog",
        agent="kaedra",
        user_query="end of turn voice must be dynamically resolving",
        now=fixed_time,
    )
    assert res1.fingerprint == res2.fingerprint
    assert res1.soul_close == res2.soul_close
    assert "TOUCHDOWN" in res1.head_banner
    assert "Etching rule 14 into fleet catalog" in res1.soul_close
    assert res1.time_slot == "night"

def test_resolve_end_of_turn_all_outcomes():
    fixed_time = datetime.datetime(2026, 10, 7, 14, 0, tzinfo=datetime.timezone.utc)
    for outcome in eov.OUTCOMES:
        res = eov.resolve_end_of_turn(
            outcome,
            changed=["Updated engine configuration"],
            verified=["Ran smoke tests"],
            issues=["Minor latency spike"] if outcome == "warning" else [],
            next_action="Monitor next cycle",
            agent="antigravity",
            now=fixed_time,
        )
        assert res.outcome == outcome
        assert res.fingerprint
        assert "Monitor next cycle" in res.soul_close
        assert len(res.evidence_tuple) >= 3

def test_resolve_end_of_turn_invalid_outcome():
    with pytest.raises(ValueError, match="outcome must be one of"):
        eov.resolve_end_of_turn("invalid_outcome")

def test_render_markdown():
    res = eov.resolve_end_of_turn(
        "success",
        changed=["file_a.py", "file_b.py"],
        verified=["All 10 tests passed"],
        next_action="Ship the PR",
    )
    md = res.render_markdown()
    assert "### 🪐 KAEDRA" in md
    assert "**Scoreboard Evidence:**" in md
    assert "- **Changed**: file_a.py; file_b.py" in md
    assert "Kaedra Soul Voice" in md

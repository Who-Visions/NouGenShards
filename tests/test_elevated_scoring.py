"""Flagged elevations: score blend (NOUGEN_ELEVATED_SCORE) and adaptive lane budget."""

import pytest

from nougen_shards import core, federation


def test_stronger_match_scores_higher():
    weak = core.elevated_final_score(-1.0, 1.0, 1.0, 0.0)
    strong = core.elevated_final_score(-30.0, 1.0, 1.0, 0.0)
    assert strong > weak


def test_gain_is_bounded():
    assert 0.0 <= core.elevated_final_score(-1e6, 1.0, 1.0, 0.0) <= 1.0


def test_old_shard_decays_but_keeps_floor():
    fresh = core.elevated_final_score(-10.0, 1.0, 0.5, 0.0)
    old = core.elevated_final_score(-10.0, 1.0, 0.5, 3650.0)
    assert old < fresh
    floored = core.elevated_final_score(-10.0, 0.0, 0.5, 3650.0)
    assert floored > 0.0  # utility floor, never zero


def test_canon_lock_is_age_invariant():
    old_canon = core.elevated_final_score(-10.0, 1.0, 0.5, 3650.0, is_canon_lock=True)
    fresh = core.elevated_final_score(-10.0, 1.0, 0.5, 0.0)
    assert old_canon == pytest.approx(fresh)


def test_flag_off_keeps_existing_blend(monkeypatch):
    monkeypatch.delenv("NOUGEN_ELEVATED_SCORE", raising=False)
    assert core._elevated_scoring_enabled() is False


def test_flag_on(monkeypatch):
    monkeypatch.setenv("NOUGEN_ELEVATED_SCORE", "1")
    assert core._elevated_scoring_enabled() is True


@pytest.fixture
def fresh_reliability(monkeypatch):
    monkeypatch.setattr(federation, "_LANE_RELIABILITY", {})
    yield


def test_budget_is_full_deadline_when_flag_off(monkeypatch, fresh_reliability):
    monkeypatch.delenv("NOUGEN_ADAPTIVE_LANE_TIMEOUT", raising=False)
    for _ in range(20):
        federation._lane_reliability_record("blade", "timeout")
    assert federation._lane_budget_s("blade", 20.0) == 20.0


def test_failing_lane_is_held_to_floor_when_flag_on(monkeypatch, fresh_reliability):
    monkeypatch.setenv("NOUGEN_ADAPTIVE_LANE_TIMEOUT", "1")
    monkeypatch.setenv("NOUGEN_LANE_MIN_DEADLINE_S", "5")
    for _ in range(40):
        federation._lane_reliability_record("whoart", "timeout")
    assert federation._lane_budget_s("whoart", 20.0) == pytest.approx(5.0, abs=0.5)


def test_healthy_lane_keeps_full_budget(monkeypatch, fresh_reliability):
    monkeypatch.setenv("NOUGEN_ADAPTIVE_LANE_TIMEOUT", "1")
    for _ in range(40):
        federation._lane_reliability_record("local", "ok")
    assert federation._lane_budget_s("local", 20.0) > 18.0


def test_canon_event_type_is_fetched_by_keyword_path(tmp_path, monkeypatch):
    """The elevated score can only grant a canon lock if the row carries event_type."""
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(core, "get_db_path", lambda i: tmp_path / f"t_{i}.db")
    core.init_db(1)
    core.capture("CANON", "Lock title zzcanonqq1", "canon body zzcanonqq1 locked", domain_key="global")
    monkeypatch.setenv("NOUGEN_ELEVATED_SCORE", "1")
    rows = core.retrieve("zzcanonqq1", limit=3)
    assert rows and rows[0].get("event_type") == "CANON"


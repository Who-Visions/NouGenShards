"""ContextState (wishlist items 26, 41-50, 60) and health generation IDs
(item 39). Source: leg 20260910T202128Z, rebroadcast 20260923T174020Z.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards.status_semantics import (  # noqa: E402
    ContextState, HealthGeneration, Observation, RequiredSource, StatusLevel,
    derive_context_state, is_stale_generation, stamp_generation,
)


def src(name, is_local, answered, reason=""):
    return RequiredSource(name, is_local, answered, reason)


# --------------------------------------------------------------- state derivation
def test_all_required_answered_is_full():
    r = derive_context_state([src("blade", False, True), src("whoart", False, True),
                              src("phoebus", True, True)])
    assert r.state is ContextState.FULL


def test_one_missing_remote_with_others_answered_is_degraded():
    r = derive_context_state([src("blade", False, True), src("whoart", False, False, "timeout")])
    assert r.state is ContextState.DEGRADED
    assert "whoart" in r.reason


def test_only_local_answered_no_remote_reachable_is_local_only():
    r = derive_context_state([src("phoebus", True, True), src("blade", False, False, "unreachable")])
    assert r.state is ContextState.LOCAL_ONLY


def test_nothing_answered_is_unavailable():
    r = derive_context_state([src("blade", False, False), src("phoebus", True, False)])
    assert r.state is ContextState.UNAVAILABLE


def test_no_required_sources_declared_is_unavailable_not_full():
    """Item 26's whole point: a task that declares nothing required has not
    proven completeness. This must NOT default to FULL."""
    r = derive_context_state([])
    assert r.state is ContextState.UNAVAILABLE
    assert "no required sources declared" in r.reason


def test_negative_control_full_requires_every_source_not_just_one():
    """Confirms FULL isn't reachable by a single lucky answer."""
    all_answered = derive_context_state([src("a", False, True), src("b", False, True)])
    one_missing = derive_context_state([src("a", False, True), src("b", False, False)])
    assert all_answered.state is ContextState.FULL
    assert one_missing.state is not ContextState.FULL


def test_sources_answered_and_missing_are_both_reported():
    r = derive_context_state([src("blade", False, True), src("whoart", False, False, "timeout")])
    assert r.sources_answered == ("blade",)
    assert r.sources_missing == ("whoart",)


# ------------------------------------------------------ degraded-mode prohibitions
def test_full_permits_exhaustive_recall_absence_and_destructive_edits():
    r = derive_context_state([src("blade", False, True)])
    assert r.exhaustive_recall_permitted
    assert r.absence_conclusions_permitted
    assert r.destructive_edits_permitted


@pytest.mark.parametrize("sources", [
    [src("blade", False, True), src("whoart", False, False)],   # degraded
    [src("phoebus", True, True), src("blade", False, False)],   # local_only
    [src("blade", False, False)],                                # unavailable
])
def test_anything_less_than_full_prohibits_all_three(sources):
    """Items 48, 49, 50, applied literally: degraded/local_only/unavailable
    must all refuse exhaustive-recall claims, absence conclusions, and
    destructive edits -- not just 'degraded' specifically."""
    r = derive_context_state(sources)
    assert r.state is not ContextState.FULL
    assert not r.exhaustive_recall_permitted
    assert not r.absence_conclusions_permitted
    assert not r.destructive_edits_permitted


def test_negative_control_permissions_are_not_hardcoded_true():
    """Confirms the three permission properties actually read .state rather
    than always returning True regardless of it."""
    full = derive_context_state([src("a", False, True)])
    degraded = derive_context_state([src("a", False, True), src("b", False, False)])
    assert full.exhaustive_recall_permitted is True
    assert degraded.exhaustive_recall_permitted is False


# ------------------------------------------------------------------------ receipt
def test_receipt_to_dict_is_a_compact_complete_record():
    r = derive_context_state([src("blade", False, True), src("whoart", False, False, "timeout")])
    d = r.to_dict()
    assert d["context_state"] == "degraded"
    assert d["sources_answered"] == ["blade"]
    assert d["sources_missing"] == ["whoart"]
    assert d["exhaustive_recall_permitted"] is False
    assert "reason" in d


def test_context_state_enum_values_match_the_leg_exactly():
    """Item 26's own wording: 'full, degraded, local_only, unavailable'."""
    assert {s.value for s in ContextState} == {"full", "degraded", "local_only", "unavailable"}


# ------------------------------------------------------------ health generation
def test_fresh_stamp_is_not_stale_against_its_own_generation():
    g = HealthGeneration()
    g.bump()
    o = Observation("x", "probe", StatusLevel.GREEN, "ok")
    stamped = stamp_generation(o, g.value)
    assert not is_stale_generation(stamped, g.value)


def test_a_new_sweep_makes_the_old_stamp_stale():
    g = HealthGeneration()
    g.bump()
    o = Observation("x", "probe", StatusLevel.GREEN, "ok")
    stamped = stamp_generation(o, g.value)
    g.bump()  # a fresh sweep happened
    assert is_stale_generation(stamped, g.value)


def test_stale_generation_is_true_even_though_status_still_says_green():
    """The exact scenario item 39 exists for: a cached GREEN that predates
    the latest sweep must be detectable as stale independent of its color."""
    g = HealthGeneration()
    g.bump()
    o = Observation("x", "probe", StatusLevel.GREEN, "still green in the cache")
    stamped = stamp_generation(o, g.value)
    g.bump()
    assert stamped.status is StatusLevel.GREEN  # color unchanged
    assert is_stale_generation(stamped, g.value)  # but staleness is detectable


def test_unstamped_observation_is_never_judged_stale_by_this_check():
    o = Observation("x", "probe", StatusLevel.GREEN, "ok")  # never stamped
    assert not is_stale_generation(o, current_generation=99)


def test_generation_counter_is_monotonic_and_independent_per_instance():
    g1 = HealthGeneration()
    g2 = HealthGeneration()
    assert g1.value == g2.value == 0
    g1.bump()
    g1.bump()
    assert g1.value == 2
    assert g2.value == 0  # separate instances do not share state


def test_stamp_generation_does_not_mutate_status_or_reason():
    o = Observation("x", "probe", StatusLevel.YELLOW, "partial")
    stamped = stamp_generation(o, 7)
    assert stamped.status is StatusLevel.YELLOW
    assert stamped.reason == "partial"
    assert stamped.evidence["health_generation"] == 7
    assert "health_generation" not in o.evidence  # original untouched

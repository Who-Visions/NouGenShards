"""nougen wishlist: the canonical 100-item wishlist as a real, trackable
artifact (leg 20260910T202128Z, rebroadcast 20260923T174020Z, Dave's
explicit order 2026-09-23 for a fresh shard + relay of the exact original)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards.wishlist import (  # noqa: E402
    CATEGORIES, ITEMS, ItemStatus, WishlistState, category_of, default_state_path,
    load_state, phase_of, progress_by_category, progress_by_phase, save_state,
)


# --------------------------------------------------------------- the text
def test_exactly_100_items():
    assert len(ITEMS) == 100
    assert set(ITEMS) == set(range(1, 101))


def test_item_ids_are_contiguous_and_start_at_1():
    assert sorted(ITEMS) == list(range(1, 101))


@pytest.mark.parametrize("item_id,expected_category", [
    (1, "A"), (20, "A"), (21, "B"), (40, "B"), (41, "C"), (60, "C"),
    (61, "D"), (80, "D"), (81, "E"), (90, "E"), (91, "F"), (100, "F"),
])
def test_category_boundaries_match_the_leg_exactly(item_id, expected_category):
    assert category_of(item_id) == expected_category
    assert ITEMS[item_id].category == expected_category


@pytest.mark.parametrize("item_id,expected_phase", [
    (1, 1), (40, 1), (41, 2), (60, 2), (61, 3), (90, 3), (91, 4), (100, 4),
])
def test_phase_boundaries_match_the_execution_order_section(item_id, expected_phase):
    assert phase_of(item_id) == expected_phase
    assert ITEMS[item_id].phase == expected_phase


def test_category_of_refuses_out_of_range():
    with pytest.raises(ValueError):
        category_of(0)
    with pytest.raises(ValueError):
        category_of(101)


def test_every_category_has_a_name():
    for letter in "ABCDEF":
        assert letter in CATEGORIES
        assert CATEGORIES[letter]


def test_known_items_read_verbatim_from_the_leg():
    """Spot-check the exact wording survived transcription -- the id IS the
    citation, so drift here would silently break every future reference."""
    assert ITEMS[1].text == "Make every shard read query each physical machine vault independently."
    assert ITEMS[40].text == ("Never mark a repair completed unless acceptance probes pass "
                              "from ChatGPT or another external consumer.")
    assert ITEMS[100].text.startswith("Final acceptance gate:")
    assert "Deep Health report" in ITEMS[99].text


# ------------------------------------------------------------------- state
def test_fresh_state_has_every_item_open():
    state = WishlistState()
    for item_id in ITEMS:
        assert state.get(item_id).status is ItemStatus.OPEN


def test_get_unknown_item_raises():
    state = WishlistState()
    with pytest.raises(KeyError):
        state.get(101)


def test_landed_without_evidence_is_refused():
    """The wishlist's own doctrine ('No completion stamp without live
    verification') enforced structurally, not just documented."""
    state = WishlistState()
    with pytest.raises(ValueError):
        state.mark(1, ItemStatus.LANDED)


def test_verified_without_evidence_is_also_refused():
    state = WishlistState()
    with pytest.raises(ValueError):
        state.mark(1, ItemStatus.VERIFIED)


def test_open_and_in_progress_do_not_require_evidence():
    state = WishlistState()
    state.mark(1, ItemStatus.OPEN)
    state.mark(1, ItemStatus.IN_PROGRESS, owner="phoebus/claude-cli")
    assert state.get(1).status is ItemStatus.IN_PROGRESS


def test_landed_with_evidence_succeeds_and_is_recorded():
    state = WishlistState()
    rec = state.mark(99, ItemStatus.LANDED, evidence=["PR#500"], owner="phoebus/claude-cli",
                     note="hardcade_cron_out ships parts of this")
    assert rec.status is ItemStatus.LANDED
    assert "PR#500" in rec.evidence
    assert rec.owner == "phoebus/claude-cli"
    assert rec.updated_at is not None


def test_evidence_accumulates_across_marks_without_duplication():
    state = WishlistState()
    state.mark(1, ItemStatus.LANDED, evidence=["leg-A"])
    state.mark(1, ItemStatus.VERIFIED, evidence=["leg-A", "leg-B"])
    assert state.get(1).evidence == ["leg-A", "leg-B"]


def test_negative_control_removing_the_guard_lets_landed_through_without_evidence():
    """Proves the refusal above is actually load-bearing, not a test that
    would pass regardless."""
    class NoGuardState(WishlistState):
        def mark(self, item_id, status, evidence=None, owner=None, note=""):  # noqa: D401
            rec = self.get(item_id)
            rec.status = status
            return rec

    state = NoGuardState()
    rec = state.mark(1, ItemStatus.LANDED)  # would have raised on the real class
    assert rec.status is ItemStatus.LANDED  # confirms the subclass really did bypass it


# --------------------------------------------------------- persistence round-trip
def test_state_round_trips_through_json(tmp_path):
    state = WishlistState()
    state.mark(1, ItemStatus.LANDED, evidence=["PR#494"], owner="phoebus")
    state.mark(50, ItemStatus.IN_PROGRESS, owner="whoart/claude-app")
    path = save_state(state, tmp_path / "wishlist_state.json")
    assert path.is_file()

    reloaded = load_state(path)
    assert reloaded.get(1).status is ItemStatus.LANDED
    assert reloaded.get(1).evidence == ["PR#494"]
    assert reloaded.get(50).status is ItemStatus.IN_PROGRESS
    assert reloaded.get(2).status is ItemStatus.OPEN  # untouched items default correctly


def test_missing_state_file_loads_as_fresh_all_open(tmp_path):
    state = load_state(tmp_path / "does_not_exist.json")
    assert all(state.get(i).status is ItemStatus.OPEN for i in (1, 50, 100))


def test_saved_json_is_actually_readable_by_a_human(tmp_path):
    state = WishlistState()
    state.mark(7, ItemStatus.LANDED, evidence=["shard:12345@db4"])
    path = save_state(state, tmp_path / "s.json")
    doc = json.loads(path.read_text())
    assert doc["items"]["7"]["status"] == "landed"
    assert doc["source_leg_rebroadcast"] == "20260923T174020Z__chatgpt-app__g-whoentertains"


def test_default_state_path_is_under_dot_nougen():
    assert ".nougen" in str(default_state_path())
    assert default_state_path().name == "wishlist_state.json"


# --------------------------------------------------------------------- progress
def test_progress_by_phase_totals_match_the_execution_order_section():
    state = WishlistState()
    by_phase = progress_by_phase(state)
    assert by_phase[1]["total"] == 40
    assert by_phase[2]["total"] == 20
    assert by_phase[3]["total"] == 30
    assert by_phase[4]["total"] == 10
    assert sum(p["total"] for p in by_phase.values()) == 100


def test_progress_by_category_totals_match_the_category_sections():
    state = WishlistState()
    by_cat = progress_by_category(state)
    assert by_cat["A"]["total"] == 20
    assert by_cat["B"]["total"] == 20
    assert by_cat["C"]["total"] == 20
    assert by_cat["D"]["total"] == 20
    assert by_cat["E"]["total"] == 10
    assert by_cat["F"]["total"] == 10
    assert sum(c["total"] for c in by_cat.values()) == 100


def test_progress_reflects_a_real_mark():
    state = WishlistState()
    state.mark(1, ItemStatus.LANDED, evidence=["x"])
    state.mark(2, ItemStatus.VERIFIED, evidence=["y"])
    state.mark(3, ItemStatus.IN_PROGRESS)
    by_phase = progress_by_phase(state)
    assert by_phase[1]["landed"] == 1
    assert by_phase[1]["verified"] == 1
    assert by_phase[1]["in_progress"] == 1
    assert by_phase[1]["open"] == 37


def test_negative_control_progress_is_not_hardcoded_to_zero():
    """Confirms progress actually reads the state rather than always
    reporting an empty/zero summary regardless of input."""
    empty = progress_by_phase(WishlistState())
    state = WishlistState()
    for i in range(1, 21):
        state.mark(i, ItemStatus.LANDED, evidence=["bulk"])
    filled = progress_by_phase(state)
    assert empty[1]["landed"] == 0
    assert filled[1]["landed"] == 20
    assert empty != filled

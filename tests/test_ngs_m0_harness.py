"""Unit tests for the NGS M0 harness helpers (no vault, no model)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals" / "ngs_m0"))

import build_labeled_set as b  # noqa: E402
import run_baseline as r  # noqa: E402


def test_clean_goal_strips_leg_ids_and_handoff():
    text = "Handoff 20260829T133056Z__lane-a__agent-b verified (STATUS). Goal: FIXED: gateway auth ok. Closes legs 20260829T120001Z, done."
    g = b.clean_goal(text)
    assert "2026" not in g and "Handoff" not in g
    assert g.startswith("FIXED: gateway auth ok")


def test_clean_goal_without_goal_is_empty():
    assert b.clean_goal("no marker here") == ""


def test_is_hit_by_title_or_id():
    item = {"gold_title": "T", "gold": [{"db": 3, "id": 9}]}
    assert r.is_hit({"title": "T"}, item)
    assert r.is_hit({"title": "x", "id": 9, "_db_index": 3}, item)
    assert not r.is_hit({"title": "x", "id": 9, "_db_index": 4}, item)
    assert not r.is_hit({"title": "x", "id": 1}, item)


def test_pct():
    assert r.pct([1, 2, 3, 4, 5], 0.5) == 3
    assert r.pct([], 0.5) is None

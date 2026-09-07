"""Shard locators must name exactly one row, and must refuse to guess.

Regression cover for the 2026-09-07 fleet incident: `shards_search` advertised a
`db_index` it never actually returned (it read the key `db_index` while
`core.retrieve` sets `_db_index`), so every caller saw None, cited a bare id, and
those ids collide across DBs -- 99.2% of them on blade. Three lanes each concluded
"not found" from an instrument that could not have found the row.
"""

from __future__ import annotations

import pytest

from nougen_shards import kaedra_tools, locator


class TestParse:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("blade:2#29825", (29825, 2, "blade")),
            ("blade1tb:1#24542", (24542, 1, "blade1tb")),
            ("2#29825", (29825, 2, None)),
            ("db2#29825", (29825, 2, None)),
            ("29825@db2", (29825, 2, None)),  # legacy form seen in relay legs
            ("29825@2", (29825, 2, None)),
            ("29825", (29825, None, None)),
            (29825, (29825, None, None)),
            ("  blade:2#29825  ", (29825, 2, "blade")),
        ],
    )
    def test_accepts_known_forms(self, text, expected):
        ref = locator.parse(text)
        assert ref is not None
        assert (ref.shard_id, ref.db_index, ref.node) == expected

    @pytest.mark.parametrize("bad", [None, "", "   ", "not-a-shard", "abc#12", True, False])
    def test_rejects_non_references(self, bad):
        assert locator.parse(bad) is None

    def test_prose_containing_an_id_is_not_a_locator(self):
        # Anchored match: a number mentioned in a sentence must not parse as a
        # reference, or citing rules become unenforceable.
        assert locator.parse("see shard 29825 for details") is None

    def test_unqualified_id_does_not_invent_a_db(self):
        # The whole defect was a missing part being filled in with a plausible
        # default. None must survive as None.
        ref = locator.parse("29825")
        assert ref.db_index is None and ref.node is None
        assert not ref.is_qualified

    def test_qualified_only_when_all_three_parts_present(self):
        assert locator.parse("blade:2#29825").is_qualified
        assert not locator.parse("2#29825").is_qualified


class TestFormat:
    def test_round_trips(self):
        ref = locator.parse(locator.format_locator(29825, 2, "blade"))
        assert (ref.shard_id, ref.db_index, ref.node) == (29825, 2, "blade")

    def test_node_defaults_to_this_node(self):
        assert locator.format_locator(29825, 2).endswith(":2#29825")

    def test_missing_db_degrades_to_bare_id_not_a_fake_locator(self):
        # A locator that looks complete but isn't would be worse than none.
        assert locator.format_locator(29825, None) == "29825"

    def test_node_is_resolved_at_call_time(self, monkeypatch):
        monkeypatch.setenv("NOUGEN_NODE", "phoebus")
        assert locator.format_locator(1, 3) == "phoebus:3#1"
        monkeypatch.setenv("NOUGEN_NODE", "whoart")
        assert locator.format_locator(1, 3) == "whoart:3#1"

    def test_stamp_reads_the_private_db_key(self):
        # core.retrieve sets _db_index, not db_index. Reading the wrong one is the
        # original bug.
        item = locator.stamp({"id": 24542, "_db_index": 1})
        assert item["locator"].endswith(":1#24542")

    def test_stamp_without_db_does_not_fabricate(self):
        assert locator.stamp({"id": 24542})["locator"] == "24542"


class TestSearchSuppliesWhatRecallRequires:
    """The contract that was broken: search's output must be usable by recall."""

    def test_search_emits_a_qualified_locator(self, monkeypatch):
        monkeypatch.setattr(
            kaedra_tools, "_limit", lambda args: 2, raising=False
        )
        rows = [
            {"id": 24542, "_db_index": 1, "title": "a", "score": 1.0},
            {"id": 29825, "_db_index": 2, "title": "b", "score": 0.5},
        ]

        from nougen_shards import core

        monkeypatch.setattr(core, "retrieve", lambda q, limit=None: rows)

        out = kaedra_tools._shards_search({"query": "x"})
        assert [s["db_index"] for s in out["shards"]] == [1, 2], "db_index must not be None"
        for s in out["shards"]:
            ref = locator.parse(s["locator"])
            assert ref.is_qualified, f"search returned unusable locator {s['locator']!r}"
            assert ref.shard_id == s["id"] and ref.db_index == s["db_index"]


class TestRecallRefusesToGuess:
    def test_bare_id_is_rejected_rather_than_defaulted(self):
        out = kaedra_tools._shards_recall({"shard_id": 24542})
        assert "error" in out and "ambiguous" in out["error"]
        assert "shard" not in out

    def test_missing_reference_is_rejected(self):
        assert "error" in kaedra_tools._shards_recall({})

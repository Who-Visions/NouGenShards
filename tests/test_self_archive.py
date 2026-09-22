"""Synthetic tests for the Xoah Self Archive (Black Glass runtime hardening).

Every archive here is built in tmp_path, so the tests pin behavior, not canon.
"""
import json

import pytest

from nougen_shards import self_archive as sa

PROV = ["shard:test"]


def _archive(tmp_path, **overrides):
    data = {
        "birth_year": 2160, "terminal_year": 2300, "volume_years": {"1": 2170},
        "nodes": [
            {"id": "n_a", "year": 2170, "episode": 1, "coordinate": "2170", "provenance": PROV,
             "event": "the fire", "belief_then": "the fire was an accident",
             "knowledge": ["fire"], "revealed_truth": "SECRET_REVEAL",
             "terminal_interpretation": "SECRET_TERMINAL",
             "choices": {"TERMINAL_KNOWN": [{"option": "open the vault", "patterns": ["open the vault"],
                                            "known_from": "n_z"}]}},
            {"id": "n_b", "year": 2180, "episode": 2, "coordinate": "2180", "provenance": PROV,
             "event": "she leaves", "belief_then": "leaving is safe"},
        ],
        "edges": [{"from": "n_a", "to": "n_b", "type": "CAUSES"},
                  {"from": "n_a", "to": "w_burn", "type": "TRAUMATIZES"}],
        "wounds": [{"id": "w_burn", "name": "burn", "year": 2170, "bias": "avoids fire",
                    "blocks": ["light the fire"], "provenance": PROV}],
        "relationships": [{"entity": "Mara", "provenance": PROV,
                           "timeline": [{"year": 2170, "love": 0.9, "trust": 0.1}]}],
    }
    data.update(overrides)
    p = tmp_path / "archive.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return sa.load_archive(p, force=True)


def test_love_is_not_trust(tmp_path):
    arc = _archive(tmp_path)
    rel = sa.relationship_at("Mara", "2175", archive=arc)
    assert rel["layer"] == "LIVED_TRUTH"
    assert rel["state"]["love"] == 0.9
    assert rel["state"]["trust"] == 0.1


def test_terminal_knowledge_cannot_leak_backward(tmp_path):
    arc = _archive(tmp_path)
    tvn = sa.then_vs_now("2170", archive=arc)
    assert "SECRET_REVEAL" not in json.dumps(tvn["then"])
    assert "SECRET_TERMINAL" not in json.dumps(tvn["then"])
    assert tvn["now"]["revealed"] == "SECRET_REVEAL"
    found = sa.choice_frontier_check("2170", "she tries to open the vault", archive=arc)
    assert any(f["verdict"] == "KNOWLEDGE_CONFLICT" and f["class"] == "TERMINAL_KNOWN" for f in found)


def test_authored_unwritten_slots(tmp_path):
    arc = _archive(tmp_path)
    ep = sa.unwritten("episode 7", archive=arc)
    assert ep["layer"] == "UNWRITTEN_SELF" and ep["authored_episodes"] == [1, 2]
    assert sa.unwritten("episode 1", archive=arc) is None
    assert sa.state_at("2165", archive=arc)["layer"] == "UNWRITTEN_SELF"
    assert sa.relationship_at("Nobody", "2175", archive=arc)["layer"] == "UNWRITTEN_SELF"


def test_missing_archive_is_absent_not_unwritten(tmp_path, monkeypatch):
    missing = tmp_path / "nope.json"
    monkeypatch.setenv("NOUGEN_SELF_ARCHIVE_PATH", str(missing))
    arc = sa.load_archive(force=True)
    assert arc["status"] == sa.ARCHIVE_ABSENT
    for answer in (sa.state_at("2170", archive=arc), sa.relationship_at("Mara", "2170", archive=arc),
                   sa.unwritten("episode 7", archive=arc), sa.then_vs_now("2170", archive=arc),
                   sa.conservation_check("n_a", archive=arc)):
        assert answer["layer"] == sa.ARCHIVE_ABSENT
        assert "UNWRITTEN_SELF" not in json.dumps(answer.get("layer"))
    assert sa.choice_frontier_check("2170", "anything", archive=arc) == []
    # absence is not cached: restoring the file is picked up on the next load
    _archive(tmp_path)
    (tmp_path / "archive.json").replace(missing)
    assert sa.load_archive()["status"] == "PRESENT"


def test_conservation_cost(tmp_path):
    arc = _archive(tmp_path)
    cost = sa.conservation_check("n_a", archive=arc)
    assert cost["violation"] is True
    assert {c["lost"] for c in cost["lost_consequences"]} == {"n_b", "w_burn"}
    assert cost["lost_wounds"] == ["w_burn"]
    assert cost["lost_biases"] == ["avoids fire"]
    assert sa.conservation_check("n_b", archive=arc)["violation"] is False


def test_unprovenanced_node_refused(tmp_path):
    with pytest.raises(ValueError):
        _archive(tmp_path, nodes=[{"id": "n_x", "year": 2170}])


def test_packaged_canon_archive_present():
    arc = sa.load_archive(sa.archive_path(), force=True)
    if arc["status"] == sa.ARCHIVE_ABSENT:
        pytest.skip(f"no packaged archive at {arc['path']}")
    assert arc["nodes"] and arc["relationships"]

from nougen_shards import conflict_set as cs


def shard(sid, db, title, content, ts, tags=None, node=""):
    return {"id": sid, "_db_index": db, "title": title, "content": content,
            "timestamp": ts, "tags": tags or [], "source_node": node}


# Synthetic stand-in for a real class of failure: an early record says one
# trade, a later record corrects it, and recall returns both.
OLD = shard(101, 1, "Acme Mechanical profile",
            "Acme Mechanical is a gas fuel piping and medical gas contractor serving the county.",
            "2026-07-19T10:00:00Z", node="alpha")
FIX = shard(202, 4, "Correction: Acme Mechanical trade",
            "Correction: Acme Mechanical installs residential air conditioning. The gas fuel piping "
            "framing in the earlier profile is wrong.",
            "2026-08-03T15:00:00Z", node="beta")
UNRELATED = shard(303, 2, "Tide tables", "High tide at the inlet arrives before sunrise on weekdays.",
                  "2026-08-04T09:00:00Z")


def test_correction_on_same_subject_is_flagged_and_keeps_both_sides():
    found = cs.find_conflicts([OLD, FIX, UNRELATED])
    assert len(found) == 1
    c = found[0]
    assert c["later"]["ref"] == "202@db4" and c["earlier"]["ref"] == "101@db1"
    assert c["signal"] == "cue_overlap"


def test_order_of_hits_does_not_change_which_side_is_later():
    found = cs.find_conflicts([FIX, OLD])
    assert found[0]["later"]["ref"] == "202@db4"


def test_control_agreeing_and_unrelated_shards_are_not_flagged():
    same = shard(102, 1, "Acme Mechanical address",
                 "Acme Mechanical is a gas fuel piping contractor with an office on Main Street.",
                 "2026-07-20T10:00:00Z")
    assert cs.find_conflicts([OLD, same, UNRELATED]) == []


def test_cue_without_shared_subject_is_not_flagged():
    other = shard(404, 3, "Correction: bus schedule",
                  "Correction: the express route leaves at noon, the earlier timetable was wrong.",
                  "2026-08-05T09:00:00Z")
    assert cs.find_conflicts([OLD, other]) == []


def test_supersedes_marker_outranks_cue_overlap():
    marked = shard(505, 2, "Acme licence status", "Eligible for exam only.",
                   "2026-08-06T09:00:00Z", tags=["supersedes:101@db1"])
    found = cs.find_conflicts([FIX, OLD, marked])
    assert found[0]["signal"] == "supersedes_marker"
    assert found[0]["later"]["ref"] == "505@db2" and found[0]["earlier"]["ref"] == "101@db1"


def test_citing_a_shard_without_a_correction_cue_is_not_a_dispute():
    cites = shard(606, 5, "Follow-up", "Builds on 101@db1 with the office phone number.",
                  "2026-08-07T09:00:00Z")
    assert cs.find_conflicts([OLD, cites]) == []


def test_reference_plus_cue_is_flagged_even_with_little_shared_vocabulary():
    names = shard(707, 5, "Amended", "Retracted: see 101@db1, that record is stale.",
                  "2026-08-08T09:00:00Z")
    found = cs.find_conflicts([OLD, names])
    assert found and found[0]["signal"] == "names_reference"


def test_earlier_shard_cannot_dispute_a_later_one():
    early_fix = dict(FIX, timestamp="2026-01-01T00:00:00Z")
    assert cs.find_conflicts([OLD, early_fix]) == []


def test_render_names_both_refs_and_refuses_to_pick_a_winner():
    block = cs.render(cs.find_conflicts([OLD, FIX]))
    assert block.startswith("[CONFLICT SET] 1 pair(s)")
    assert "202@db4" in block and "101@db1" in block
    assert "neither is ruled correct" in block


def test_annotate_leaves_packet_alone_when_nothing_conflicts():
    assert cs.annotate("PACKET", [OLD, UNRELATED]) == "PACKET"


def test_annotate_appends_block_and_never_drops_the_packet():
    out = cs.annotate("PACKET", [OLD, FIX])
    assert out.startswith("PACKET\n\n[CONFLICT SET]")


def test_kill_switch(monkeypatch):
    monkeypatch.setenv(cs.ENV_ENABLED, "0")
    assert cs.annotate("PACKET", [OLD, FIX]) == "PACKET"


def test_max_pairs_is_env_driven(monkeypatch):
    monkeypatch.setenv(cs.ENV_MAX_PAIRS, "0")
    assert cs.find_conflicts([OLD, FIX]) == []


def test_bad_env_value_falls_back_instead_of_raising(monkeypatch):
    monkeypatch.setenv(cs.ENV_MIN_OVERLAP, "lots")
    assert len(cs.find_conflicts([OLD, FIX])) == 1


def test_malformed_items_do_not_break_recall():
    assert cs.annotate("PACKET", [None, "x", {"id": 1}]) == "PACKET"

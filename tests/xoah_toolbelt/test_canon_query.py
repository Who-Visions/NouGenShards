"""canon_query / missing_context over NEUTRAL synthetic canon (no real lore in this public repo)."""
import pytest

from nougen_shards.xoah_toolbelt.canon_query import content_words, xoah_canon_query
from nougen_shards.xoah_toolbelt.missing_context import xoah_missing_context
from nougen_shards.xoah_toolbelt.types import CanonKind as K
from nougen_shards.xoah_toolbelt.types import CanonPacket, CanonRecord, Provenance, Scene


def prov(n, phrase="p"):
    return (Provenance(n, "db1", "nodeA", phrase),)


LOCK_HARBOR = CanonRecord("L1", K.LOCKED, "The lighthouse keeper never leaves the harbor.", topics=("harbor", "lighthouse"),
                          contradicts=(r"leaves the harbor",), provenance=prov(1, "harbor lock"))
LOCK_OTHER = CanonRecord("L2", K.LOCKED, "Marsh boats carry no engines.", topics=("marsh", "boats"),
                         contradicts=(r"\bcanon\b",), provenance=prov(2, "marsh lock"))  # would fire on a bare word
CAND = CanonRecord("C1", K.CANDIDATE, "The lighthouse keeper leaves the harbor at dusk.", topics=("harbor", "lighthouse"),
                   provenance=prov(3, "cand"))
DONOR_P = CanonRecord("P1", K.PROCESS_DONOR, "Borrow the tide-table method for pacing harbor scenes.", topics=("harbor",),
                      provenance=prov(4, "process"))
DONOR_S = CanonRecord("S1", K.SOURCE_DONOR, "A sailor song about the lighthouse.", topics=("lighthouse",),
                      provenance=prov(5, "source"))
SPEC = CanonRecord("X1", K.SPECULATION, "Maybe the keeper is a ghost of the harbor.", topics=("harbor",), provenance=prov(6, "spec"))
R_A = CanonRecord("RA", K.LOCKED, "On route alpha the pier is closed.", topics=("pier",), routes=("alpha",), provenance=prov(7))
R_B = CanonRecord("RB", K.LOCKED, "On route beta the pier is open.", topics=("pier",), routes=("beta",), provenance=prov(8))
V2 = CanonRecord("V2", K.LOCKED, "In volume two the pier burns.", topics=("pier",), volumes=(2,), provenance=prov(9))

PACKET = CanonPacket("rev-1", records=(LOCK_HARBOR, LOCK_OTHER, CAND, DONOR_P, DONOR_S, SPEC, R_A, R_B, V2),
                     scenes=(Scene("s1", "alpha", "v1", 1, 1), Scene("s2", "alpha", "v2", 1, 2)))


def section(rcpt, name):
    for f in rcpt.findings:
        if f.get("section") == name:
            return f
    return None


def ids(rcpt, name):
    f = section(rcpt, name)
    return [r["id"] for r in f["records"]] if f else []


def test_kinds_stay_separate_and_candidate_is_never_a_fact():
    r = xoah_canon_query(PACKET, "lighthouse keeper harbor")
    assert ids(r, "facts") == ["L1"]
    assert ids(r, "candidate_facts") == ["C1"]
    assert "C1" not in ids(r, "facts")
    assert ids(r, "process_donors") == ["P1"] and ids(r, "source_donors") == ["S1"] and ids(r, "speculation") == ["X1"]
    assert all(e["binding"] for e in section(r, "facts")["records"])
    assert not any(e["binding"] for k in ("candidate_facts", "process_donors", "source_donors", "speculation")
                   for e in (section(r, k) or {"records": []})["records"])


def test_known_false_positive_bare_word_canon_does_not_fire_an_unrelated_lock():
    # The real defect: an engineering question containing the bare word "canon" hit an unrelated lock.
    r = xoah_canon_query(PACKET, "what existing canon bears on this import error in the build")
    assert r.verdict == "NO_MATCH"
    assert section(r, "conflicts") is None
    assert "L2" not in ids(r, "facts")


def test_generic_words_alone_never_establish_relevance():
    assert content_words("what existing canon lock bears on this") == frozenset()
    assert xoah_canon_query(PACKET, "canon lock scene character fact").verdict == "NO_MATCH"


def test_conflict_only_when_a_candidate_contradicts_a_lock_on_a_shared_topic():
    r = xoah_canon_query(PACKET, "lighthouse keeper harbor")
    assert r.verdict == "CONFLICTS"
    c = section(r, "conflicts")["records"][0]
    assert c["locked"] == "L1" and c["candidate"] == "C1"
    # the candidate is reported, never promoted or removed
    assert ids(r, "candidate_facts") == ["C1"]


def test_unrelated_lock_with_a_matching_pattern_cannot_conflict():
    # L2's pattern would match "canon" text, but no candidate shares its topics.
    cand = CanonRecord("C2", K.CANDIDATE, "canon says boats carry engines", topics=("station",), provenance=prov(20))
    pk = CanonPacket("r", records=(LOCK_OTHER, cand))
    r = xoah_canon_query(pk, "marsh boats engines station")
    assert section(r, "conflicts") is None


def test_scope_locked_returns_binding_canon_only():
    r = xoah_canon_query(PACKET, "lighthouse keeper harbor", scope="locked")
    assert [f["section"] for f in r.findings if f["section"] != "scope_report"] == ["facts"]
    assert set(r.kinds_used) == {"locked"}


def test_route_and_volume_scope_are_applied_and_counted_not_silently_lost():
    r = xoah_canon_query(PACKET, "pier", route="alpha", volume=1)
    assert ids(r, "facts") == ["RA"]
    rep = section(r, "scope_report")
    assert rep["excluded_by_route_or_volume"] == 2          # RB (route) and V2 (volume)
    r2 = xoah_canon_query(PACKET, "pier", route="alpha", volume=2)
    assert set(ids(r2, "facts")) == {"RA", "V2"}


def test_output_is_capped_and_reports_the_cut():
    r = xoah_canon_query(PACKET, "lighthouse keeper harbor", max_records=2)
    rep = section(r, "scope_report")
    assert rep["returned"] == 2 and rep["truncated"] >= 1


def test_malformed_pattern_in_the_vault_does_not_break_a_query():
    bad = CanonRecord("B1", K.LOCKED, "Docks are wet.", topics=("docks",), contradicts=("([unclosed",), provenance=prov(30))
    cand = CanonRecord("C3", K.CANDIDATE, "Docks are dry.", topics=("docks",), provenance=prov(31))
    r = xoah_canon_query(CanonPacket("r", records=(bad, cand)), "docks")
    assert r.verdict == "OK" and section(r, "conflicts") is None


def test_receipt_is_deterministic_cites_provenance_and_pins_the_revision():
    a = xoah_canon_query(PACKET, "lighthouse keeper harbor")
    b = xoah_canon_query(PACKET, "lighthouse keeper harbor")
    assert a.receipt_id and a.receipt_id == b.receipt_id and a.packet_revision == "rev-1"
    assert any(p.shard_id == 1 for p in a.sources)
    assert "nodeA/db1#1" in section(a, "facts")["records"][0]["cites"][0]
    assert xoah_canon_query(CanonPacket("rev-2", records=PACKET.records), "lighthouse keeper harbor").receipt_id != a.receipt_id


def test_timepoint_is_recorded_not_applied():
    r = xoah_canon_query(PACKET, "lighthouse keeper harbor", timepoint=5)
    assert "not applied" in section(r, "scope_report")["timepoint"]
    assert r.verdict == xoah_canon_query(PACKET, "lighthouse keeper harbor").verdict


def test_bad_arguments_are_refused():
    with pytest.raises(ValueError):
        xoah_canon_query(PACKET, "x", scope="everything")
    with pytest.raises(ValueError):
        xoah_canon_query(PACKET, "x", max_records=0)


# ------------------------------------------------------------------ xoah_missing_context

ALL_OK = {"db1": "ok", "db2": "complete"}
VAULTS = ["db1", "db2"]


def test_sufficient_when_evidence_present_and_every_vault_read():
    r = xoah_missing_context(PACKET, "lighthouse harbor", coverage=ALL_OK, expected_vaults=VAULTS, route="alpha", scene_id="s1")
    assert r.verdict == "SUFFICIENT"


def test_a_miss_is_absent_only_when_every_expected_vault_was_read():
    r = xoah_missing_context(PACKET, "quantum chromodynamics", coverage=ALL_OK, expected_vaults=VAULTS)
    assert r.verdict == "ABSENT_PROVEN" and section(r, "absence")


def test_a_miss_with_an_unread_vault_is_cannot_determine_not_absent():
    r = xoah_missing_context(PACKET, "quantum chromodynamics", coverage={"db1": "ok", "db2": "timeout"}, expected_vaults=VAULTS)
    assert r.verdict == "CANNOT_DETERMINE" and section(r, "missing_vaults")["vaults"] == ["db2"]
    r2 = xoah_missing_context(PACKET, "quantum chromodynamics", coverage={"db1": "ok"}, expected_vaults=VAULTS)
    assert r2.verdict == "CANNOT_DETERMINE"      # a vault absent from coverage is unproven, not ok


def test_no_coverage_evidence_never_reads_as_proven():
    for q in ("lighthouse harbor", "quantum chromodynamics"):
        r = xoah_missing_context(PACKET, q, coverage={}, expected_vaults=[])
        assert r.verdict == "CANNOT_DETERMINE" and section(r, "no_coverage_evidence")


def test_evidence_found_but_a_vault_unread_is_insufficient():
    r = xoah_missing_context(PACKET, "lighthouse harbor", coverage={"db1": "ok", "db2": "failed"}, expected_vaults=VAULTS, route="alpha")
    assert r.verdict == "INSUFFICIENT"


def test_missing_scene_and_missing_era_are_named():
    r = xoah_missing_context(PACKET, "lighthouse harbor", coverage=ALL_OK, expected_vaults=VAULTS, scene_id="nope")
    assert r.verdict == "INSUFFICIENT" and section(r, "missing_scene")["scene_id"] == "nope"
    only_v2 = CanonPacket("r", records=(V2,))
    r2 = xoah_missing_context(only_v2, "pier", coverage=ALL_OK, expected_vaults=VAULTS, volume=9)
    assert section(r2, "missing_era")["volume"] == 9


def test_unspecified_route_with_route_specific_evidence_is_ambiguous():
    r = xoah_missing_context(PACKET, "pier", coverage=ALL_OK, expected_vaults=VAULTS)
    amb = section(r, "ambiguity")["items"][0]
    assert r.verdict == "INSUFFICIENT" and amb["kind"] == "route" and amb["candidates"] == ["alpha", "beta"]


def test_missing_context_receipt_is_deterministic():
    kw = dict(coverage=ALL_OK, expected_vaults=VAULTS, route="alpha", scene_id="s1")
    assert xoah_missing_context(PACKET, "lighthouse harbor", **kw).receipt_id == xoah_missing_context(PACKET, "lighthouse harbor", **kw).receipt_id

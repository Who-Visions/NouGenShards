"""Stadium model: tickets, rosters, call budgets, and hash-verified call-ups.

Every stadium here is a temporary vault, so nothing touches a real database.
"""
import sqlite3

import pytest

from nougen_shards import stadium as st


def make_vault(path, rows):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE shards (id INTEGER PRIMARY KEY, title TEXT, content TEXT, file_hash TEXT)")
    con.executemany("INSERT INTO shards (id, title, content, file_hash) VALUES (?, ?, ?, ?)", rows)
    con.commit()
    con.close()
    return st.Stadium(path.stem, path)


@pytest.fixture
def stadiums(tmp_path):
    a = "the cargo ship sails at dawn"
    b = "a second record that is different"
    ta, tb = st.ticket_of(a), st.ticket_of(b)
    s1 = make_vault(tmp_path / "s1.db", [(7, "alpha", a, ta)])
    s2 = make_vault(tmp_path / "s2.db", [(3, "alpha copy", a, ta), (9, "beta", b, tb)])
    return [s1, s2], ta, tb


def test_ticket_matches_capture_hash_and_ignores_recall_packet():
    content = "real content"
    packet = content + "\n=== NOUGENSHARDS RECALL PACKET\nnoise"
    assert st.ticket_of(packet) == st.ticket_of(content)
    assert st.is_ticket(st.ticket_of(content))
    assert not st.is_ticket("not-a-ticket")


def test_lookup_finds_the_same_ticket_in_two_stadiums(stadiums):
    vaults, ta, _ = stadiums
    found = st.ticket_lookup(ta, vaults)
    assert {(s["stadium"], s["seat"]) for s in found["seats"]} == {("s1", 7), ("s2", 3)}
    assert found["unavailable"] == []


def test_lookup_refuses_a_malformed_ticket(stadiums):
    vaults, _, _ = stadiums
    with pytest.raises(ValueError):
        st.ticket_lookup("7", vaults)


def test_callup_verified_when_the_content_hashes_to_its_ticket(stadiums):
    vaults, ta, _ = stadiums
    out = st.callup(ta, roster=st.Roster.of([ta]), budget=st.CallBudget(2), stadiums=vaults)
    assert out["status"] == "verified"
    assert out["evidence"]["content_ticket"] == ta
    assert out["budget_used"] == 1


def test_callup_refused_when_the_ticket_is_not_on_the_roster_and_costs_no_budget(stadiums):
    vaults, ta, tb = stadiums
    budget = st.CallBudget(2)
    out = st.callup(ta, roster=st.Roster.of([tb]), budget=budget, stadiums=vaults)
    assert out["status"] == "refused"
    assert budget.used == 0


def test_callup_stops_at_the_budget(stadiums):
    vaults, ta, tb = stadiums
    roster = st.Roster.of([ta, tb])
    budget = st.CallBudget(1)
    assert st.callup(ta, roster=roster, budget=budget, stadiums=vaults)["status"] == "verified"
    assert st.callup(tb, roster=roster, budget=budget, stadiums=vaults)["status"] == "over_budget"
    assert budget.used == 1


def test_callup_not_found_when_no_stadium_holds_the_ticket(stadiums):
    vaults, _, _ = stadiums
    ghost = st.ticket_of("nobody wrote this")
    out = st.callup(ghost, roster=st.Roster.of([ghost]), budget=st.CallBudget(2), stadiums=vaults)
    assert out["status"] == "not_found"


def test_callup_reports_a_hash_mismatch_instead_of_returning_the_content(tmp_path):
    right = st.ticket_of("the original")
    vault = make_vault(tmp_path / "bad.db", [(1, "tampered", "something else", right)])
    out = st.callup(right, roster=st.Roster.of([right]), budget=st.CallBudget(2), stadiums=[vault])
    assert out["status"] == "hash_mismatch"
    assert "content" not in out.get("evidence", {})


def test_a_missing_vault_is_unavailable_not_a_guess(tmp_path, stadiums):
    vaults, ta, _ = stadiums
    gone = st.Stadium("gone", tmp_path / "no-such.db")
    out = st.callup("0" * 32, roster=st.Roster.of(["0" * 32]), budget=st.CallBudget(2), stadiums=[gone, *vaults])
    assert out["status"] == "unavailable"
    lookup = st.ticket_lookup(ta, [gone, *vaults])
    assert lookup["unavailable"][0]["stadium"] == "gone"


def test_roster_and_budget_reject_bad_input():
    with pytest.raises(ValueError):
        st.Roster.of(["zz"])
    with pytest.raises(ValueError):
        st.Roster.of(["0" * 32] * (st.MAX_ROSTER + 1))
    with pytest.raises(ValueError):
        st.CallBudget(0)

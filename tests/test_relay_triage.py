"""Relay triage: synthetic legs only (the public repo carries no real lore or lane names)."""
from datetime import datetime, timedelta, timezone


from nougen_shards import relay_triage as rt

NOW = datetime(2026, 1, 10, tzinfo=timezone.utc)


def leg(goal, status="open", agent="worker", body="", age_days=0.5, **kw):
    made = (NOW - timedelta(days=age_days)).isoformat().replace("+00:00", "Z")
    return {"id": "x", "goal": goal, "status": status, "agent": agent, "body": body,
            "created_utc": made, **kw}


def label(item, me="nodea"):
    return rt.classify(item, me, now=NOW).label


def test_terminal_state_is_closed_whatever_the_goal():
    assert label(leg("IMPLEMENT the thing", status="complete")) == rt.CLOSED


def test_own_leg_is_echo_by_goal_tag_or_host_footer():
    assert label(leg("[nodea] reply to the ping")) == rt.ECHO_OWN
    assert label(leg("Some report", body="details\n\nhost: nodea  session_id: 1")) == rt.ECHO_OWN
    assert label(leg("Some report", body="host: nodeb")) != rt.ECHO_OWN


def test_auto_note_by_agent_or_prefix():
    assert label(leg("session ended with dirty files", agent="outpost")) == rt.AUTO_NOTE
    assert label(leg("[auto] repo@main: 1 uncommitted file")) == rt.AUTO_NOTE


def test_addressed_elsewhere_is_other_lane_and_broadcast_is_not():
    assert label(leg("[NouGenMsg -> @nodeb] please restart")) == rt.OTHER_LANE
    assert label(leg("[NouGenMsg -> @all] pipe check")) != rt.OTHER_LANE


def test_addressed_to_me_is_actionable_and_never_stale():
    assert label(leg("[NouGenMsg -> @nodea] need the symlink", age_days=400)) == rt.ACTIONABLE
    assert label(leg("[NODEA DIRECT] apply the config", age_days=400)) == rt.ACTIONABLE


def test_owner_decision_surfaces_before_status_wording():
    v = rt.classify(leg("Draft PR built and verified; owner to decide merge/close"), "nodea", now=NOW)
    assert v.label == rt.NEEDS_OWNER


def test_status_and_action_leads():
    assert label(leg("RESOLVED: service restarted")) == rt.STATUS_FYI
    assert label(leg("Feature landed with 12 tests passing")) == rt.STATUS_FYI
    assert label(leg("IMPLEMENT the exporter")) == rt.ACTIONABLE
    assert label(leg("TODO: rotate the cert")) == rt.ACTIONABLE


def test_old_unaddressed_open_leg_is_stale_but_recent_is_unknown():
    assert label(leg("Curious note about a thing", age_days=30)) == rt.STALE
    assert label(leg("Curious note about a thing", age_days=0.1)) == rt.UNKNOWN


def test_unknown_surfaces_and_stale_does_not():
    assert rt.classify(leg("???"), "nodea", now=NOW).surface()
    assert not rt.Verdict(rt.STALE, "r", "r").surface()
    assert not rt.Verdict(rt.STATUS_FYI, "r", "r").surface()
    assert rt.Verdict(rt.NEEDS_OWNER, "r", "r").surface()


def test_every_verdict_is_in_the_closed_menu_and_names_a_rule():
    goals = ["", "a", "[x", "IMPLEMENT", "[NouGenMsg -> @", "shipped", "->@", "owner to decide"]
    for g in goals:
        for st in ("open", "acked", "complete", ""):
            v = rt.classify(leg(g, status=st), "nodea", now=NOW)
            assert v.label in rt.LABELS and v.rule and v.reason


def test_missing_fields_do_not_crash():
    assert rt.classify({}, "nodea", now=NOW).label in rt.LABELS
    assert rt.classify({"goal": None, "status": None}, None, now=NOW).label in rt.LABELS


def test_node_identity_comes_from_env_not_a_hardcoded_name(monkeypatch):
    monkeypatch.setenv("NOUGEN_MACHINE", "tenantbox")
    assert rt.classify(leg("[tenantbox] my own"), None, now=NOW).label == rt.ECHO_OWN
    monkeypatch.delenv("NOUGEN_MACHINE")
    assert rt.classify(leg("[tenantbox] my own"), None, now=NOW).label != rt.ECHO_OWN


def test_confusion_reports_counts_not_a_ratio():
    pred = [rt.ACTIONABLE, rt.CLOSED, rt.UNKNOWN, rt.STALE]
    truth = [rt.ACTIONABLE, rt.ACTIONABLE, rt.CLOSED, rt.CLOSED]
    assert rt.confusion(pred, truth) == {"tp": 1, "fn": 1, "fp": 1, "tn": 1}


def test_summarize_counts_every_label():
    rows = rt.triage([leg("IMPLEMENT x"), leg("RESOLVED y", status="complete")], "nodea", now=NOW)
    counts = rt.summarize(rows)
    assert set(counts) == set(rt.LABELS)
    assert counts[rt.ACTIONABLE] == 1 and counts[rt.CLOSED] == 1


def test_dead_letter_is_not_closed_and_surfaces():
    v = rt.classify(leg("IMPLEMENT the thing", status="dead_letter"), "nodea", now=NOW)
    assert v.label == rt.UNKNOWN and v.rule == "R1b-dead-letter" and v.surface()

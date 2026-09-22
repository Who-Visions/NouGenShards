"""Tests for nougen_shards.control_loop (synthetic data only)."""
from __future__ import annotations

import pathlib
import re

import pytest

import importlib.util

from nougen_shards import control_loop as cl

_spec = importlib.util.spec_from_file_location(
    "synthetic_control_loop",
    pathlib.Path(__file__).parent / "fixtures" / "synthetic_control_loop.py")
_fx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fx)
NOW, iso, scenarios = _fx.NOW, _fx.iso, _fx.scenarios


@pytest.mark.parametrize("name,goal,execution,verdict,check",
                         scenarios(), ids=[s[0] for s in scenarios()])
def test_intent_scenarios(name, goal, execution, verdict, check):
    r = cl.intent_alignment_check(goal, execution, now=NOW)
    assert r["verdict"] == verdict, r
    if check:
        assert check in {c["check"] for c in r["conflicts"]}
        assert r["cheapest_repair"]
        assert all(c.get("source") for c in r["conflicts"])


def test_duplicate_claim_requires_confirmation():
    s = {x[0]: x for x in scenarios()}["duplicate_claim"]
    assert cl.intent_alignment_check(s[1], s[2], now=NOW)["requires_confirmation"] is True


def test_missing_premise_never_aligned():
    goal = {"task_id": "t", "actor": "a", "constraints": {"dynamic_failover": True}}
    assert cl.intent_alignment_check(goal, {}, now=NOW)["verdict"] == "UNKNOWN"


def test_health_age_from_env(monkeypatch):
    s = {x[0]: x for x in scenarios()}["stale_health_unknown"]
    monkeypatch.setenv("NOUGEN_CONTROL_HEALTH_MAX_AGE_S", str(10 ** 6))
    assert cl.intent_alignment_check(s[1], s[2], now=NOW)["verdict"] == "ALIGNED"


def test_priority_inversion_margin_env(monkeypatch):
    monkeypatch.setenv("NOUGEN_PRIORITY_INVERSION_MARGIN", "0.9")
    s = {x[0]: x for x in scenarios()}["priority_inversion"]
    assert cl.intent_alignment_check(s[1], s[2], now=NOW)["verdict"] == "ALIGNED"


# projection ---------------------------------------------------------------
def _recall(total=4, reachable=4, failed=None, cands=True):
    return {"vault_coverage": {"total": total, "reachable": reachable, "failed": failed or {}},
            "candidate_sources": [{"key": "k"}] if cands else [], "absence_proven": False}


def test_projection_full_fresh_is_low_risk():
    p = cl.projection_envelope(_recall(), filters_applied=["alias"], observed_utc=iso(-5), now=NOW)
    assert p["projection_risk"] == "low" and p["complete"] and p["coverage"] == 1.0


def test_projection_partial_and_empty_are_high():
    p = cl.projection_envelope(_recall(4, 1, {"db3": "timeout", "db4": "x", "db5": "y"}),
                               observed_utc=iso(-5), now=NOW)
    assert p["projection_risk"] == "high" and p["unavailable_sources"] == ["db3", "db4", "db5"]
    p = cl.projection_envelope(_recall(cands=False), observed_utc=iso(-5), now=NOW)
    assert p["projection_risk"] == "high" and not p["complete"]


def test_projection_unmeasured_coverage_not_complete():
    p = cl.projection_envelope({"candidate_sources": [{"key": "k"}]}, now=NOW)
    assert p["projection_risk"] == "high" and p["coverage"] is None


def test_projection_reads_real_reconstruction_envelope():
    from nougen_shards.reconstruction import ReconstructionEnvelope
    env = ReconstructionEnvelope(query="q", query_fingerprint={}, retrieval_angles=[],
                                 candidate_sources=[], association_hops=[],
                                 vault_coverage={"total": 2, "reachable": 2, "failed": {}},
                                 time_coverage={}, correction_state={}, confidence=0.0,
                                 reconstruction_summary="", unresolved_gaps=[])
    p = cl.projection_envelope(env.to_dict(), observed_utc=iso(), now=NOW)
    assert p["projection_risk"] == "high"  # empty, absence not proven


# policy -------------------------------------------------------------------
POLICY = {"id": "route-pin", "context": {"port": 11434, "model": "m-small"},
          "set_utc": iso(-86400 * 200)}


def test_policy_known_positive_contradicted():
    r = cl.policy_pressure_test(POLICY, [{"premise": "port", "observed": 11436, "source": "probe"}],
                                dependents=["router"], now=NOW)
    assert r["verdict"] == "contradicted" and r["dependents"] == ["router"]
    assert "delete" not in (r["migration"] or "").replace("do not delete", "")


def test_policy_still_valid_after_positive_control():
    ev = [{"premise": "port", "observed": 11434}, {"premise": "model", "observed": "m-small"}]
    assert cl.policy_pressure_test(POLICY, ev, now=NOW)["verdict"] == "still_valid"


def test_policy_partial_and_old_and_new():
    assert cl.policy_pressure_test(POLICY, [{"premise": "port", "observed": 11434}],
                                   now=NOW)["verdict"] == "context_bound"
    assert cl.policy_pressure_test(POLICY, [], now=NOW)["verdict"] == "context_bound"
    fresh = dict(POLICY, set_utc=iso(-60))
    assert cl.policy_pressure_test(fresh, [], now=NOW)["verdict"] == "insufficient_evidence"
    assert cl.policy_pressure_test(dict(POLICY, superseded_by="route-v2"), [],
                                   now=NOW)["verdict"] == "superseded"


def test_policy_age_threshold_env(monkeypatch):
    monkeypatch.setenv("NOUGEN_POLICY_MAX_AGE_DAYS", "365")
    assert cl.policy_pressure_test(POLICY, [], now=NOW)["verdict"] == "insufficient_evidence"


# destiny ------------------------------------------------------------------
DESTINY = {"goal": "ship feature", "verification": "acceptance test passes",
           "deadline": "2030-03-01", "required_events": ["tests green"],
           "forbidden_outcomes": ["data loss"], "trigger": "manual", "status": "active",
           "links": [{"kind": "agent", "ref": "agent-a"}]}


def test_destiny_ready_with_complete_contract():
    r = cl.destiny_readiness(DESTINY, first_action="write test", environment={"node": "GREEN"})
    assert r["ready"], r


def test_destiny_without_verification_not_ready():
    r = cl.destiny_readiness(dict(DESTINY, verification=None), first_action="x",
                             environment={"node": "GREEN"})
    assert not r["ready"] and "verification" in r["missing_fields"]


def test_destiny_unobserved_environment_blocks():
    r = cl.destiny_readiness(DESTINY, first_action="x")
    assert "environment_unobserved" in r["blockers"]


# learning -----------------------------------------------------------------
def test_learning_failure_and_success():
    f = cl.post_run_learning({"verified": True, "outcome": "failure", "steps": [
        {"name": "fetch", "ok": False, "error_type": "HTTPError"}, {"name": "b", "ok": True}]})
    assert [i["class"] for i in f["items"]] == ["HTTPError"]
    s = cl.post_run_learning({"verified": True, "outcome": "success", "steps": [
        {"name": "a", "ok": True, "verified": True, "shard_refs": ["1@db1"]},
        {"name": "b", "ok": True, "verified": False, "shard_refs": ["2@db1"]}]})
    kinds = [i["kind"] for i in s["items"]]
    assert kinds == ["mark_useful", "recipe_candidate"] and s["items"][1]["steps"] == ["a"]


def test_learning_cap_env(monkeypatch):
    monkeypatch.setenv("NOUGEN_LEARNING_MAX_ITEMS", "2")
    r = cl.post_run_learning({"verified": True, "outcome": "failure",
                              "steps": [{"name": str(i), "ok": False} for i in range(6)]})
    assert len(r["items"]) == 2 and r["truncated"]


# guards -------------------------------------------------------------------
import os

_BASE_TERMS = ["neurolog", "unconscious", "hologra", "quantum", "repattern", "hypno", "life force"]
# Source/brand names are kept out of the public repo: supply them locally via
# NOUGEN_FORBIDDEN_TERMS (comma-separated) or NOUGEN_FORBIDDEN_TERMS_FILE (one per line).


def _forbidden_terms():
    terms = list(_BASE_TERMS)
    terms += [x.strip() for x in os.environ.get("NOUGEN_FORBIDDEN_TERMS", "").split(",") if x.strip()]
    path = os.environ.get("NOUGEN_FORBIDDEN_TERMS_FILE", "").strip()
    if path and pathlib.Path(path).is_file():
        terms += [x.strip() for x in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    return terms


BANNED = re.compile("|".join(re.escape(x) for x in _forbidden_terms()), re.I)


def test_no_donor_claims_or_source_names_in_code():
    root = pathlib.Path(cl.__file__)
    fixture = pathlib.Path(__file__).parent / "fixtures" / "synthetic_control_loop.py"
    for path in (root, fixture):
        hits = BANNED.findall(path.read_text(encoding="utf-8"))
        assert not hits, (path.name, hits)


def test_guard_known_positive():
    assert BANNED.search("the unconscious mind is holographic")


def test_no_writes_imported():
    src = pathlib.Path(cl.__file__).read_text(encoding="utf-8")
    assert not re.search(r"sqlite3|create_destiny|capture|relay_create|open\(", src)


def test_learning_hook_defaults_to_verified_runs(monkeypatch):
    monkeypatch.delenv("NOUGEN_LEARNING_HOOK", raising=False)
    run = {"outcome": "failure", "steps": [{"name": "x", "ok": False}]}
    assert cl.post_run_learning(run)["items"] == []
    monkeypatch.setenv("NOUGEN_LEARNING_HOOK", "all")
    assert len(cl.post_run_learning(run)["items"]) == 1


def test_conflict_is_report_only(monkeypatch):
    monkeypatch.setenv("NOUGEN_CONFLICT_ACTION", "auto")
    r = cl.intent_alignment_check({"task_id": "t"}, {}, now=NOW)
    assert r["action_mode"] == "report" and r["auto_apply"] is False


def test_policy_age_default_is_long(monkeypatch):
    monkeypatch.delenv("NOUGEN_POLICY_MAX_AGE_DAYS", raising=False)
    assert cl._cfg()["policy_max_age_days"] >= 180

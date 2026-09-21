"""Fixtures mirror NouGenMix main (src/fl_studio_mcp/theory/mix_decisions.py)."""
import pytest

from nougen_shards.decision import DecisionPlane, Escalation
from nougen_shards.decision.domains import mix
from nougen_shards.decision.types import ChoiceSpec, NoulSpec, ScoreSpec

COLLISION = ("KICK_808_LF", "MASKING", "PHASE", "TAIL_OVERLAP", "ARRANGEMENT_DENSITY", "TRANSLATION", "NONE")
QUESTIONS = (
    {"kind": "choice", "key": "collision", "options": COLLISION},
    {"kind": "score", "key": "translation_risk", "minimum": 0, "maximum": 4},
    {"kind": "choice", "key": "energy_role", "options": ("SUB", "PUNCH", "BODY", "AIR", "WIDE", "UNKNOWN")},
    {"kind": "choice", "key": "next_diagnostic",
     "options": ("low_end_audit", "phase_offset_scan", "masking_matrix", "band_presence", "arrangement_review", "none")},
    {"kind": "noul", "key": "evidence_sufficient"},
)
REQ = {"namespace": "mix.diagnostic", "schema_version": "1", "state": {"tail_steps": 9, "bpm": 152},
       "questions": QUESTIONS, "criticality": "normal"}


def rules_decide(state):
    if state.get("tail_steps", 0) > 6:
        return {"namespace": "mix.diagnostic", "schema_version": "1", "backend": "rules",
                "values": [{"key": "collision", "value": "TAIL_OVERLAP", "confidence": 1.0, "probabilities": {}},
                           {"key": "next_diagnostic", "value": "low_end_audit", "confidence": 1.0, "probabilities": {}}],
                "escalation": "accept", "reasons": ["tail_steps>6"]}
    return {"values": [], "escalation": "abstain", "reasons": []}


def test_from_dict_maps_every_question_kind():
    r = mix.from_dict(REQ)
    kinds = [type(q) for q in r.questions]
    assert kinds == [ChoiceSpec, ScoreSpec, ChoiceSpec, ChoiceSpec, NoulSpec]
    assert r.questions[0].options == COLLISION and r.state["bpm"] == 152


def test_foreign_namespace_or_schema_is_refused():
    with pytest.raises(ValueError):
        mix.from_dict({**REQ, "schema_version": "2"})
    with pytest.raises(ValueError):
        mix.from_dict({**REQ, "namespace": "relay.triage"})


def test_rules_accept_is_decisive_and_round_trips():
    plane = DecisionPlane({"rules": mix.rules_backend(rules_decide)})
    rec = plane.decide(mix.from_dict(REQ))
    assert rec.escalation == Escalation.ACCEPT and rec.value("collision") == "TAIL_OVERLAP"
    assert rec.provenance["rule"] == "tail_steps>6"
    d = mix.to_dict(rec)
    assert d["escalation"] == "accept" and d["values"][1]["value"] == "low_end_audit"


def test_rules_abstain_falls_through_to_abstain_with_no_models():
    plane = DecisionPlane({"rules": mix.rules_backend(rules_decide)})
    rec = plane.decide(mix.from_dict({**REQ, "state": {"tail_steps": 2}}))
    assert rec.escalation == Escalation.ABSTAIN
    assert [a["outcome"] for a in rec.provenance["attempts"]] == ["rule"]

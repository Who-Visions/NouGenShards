import json
import math

import pytest

from nougen_shards.decision import (ChoiceSpec, DecisionPlane, DecisionPolicy, DecisionRequest,
                                    DecisionValue, Escalation, NoulSpec, ScoreSpec,
                                    can_auto_accept, canonical_hash, margin, normalized_entropy)
from nougen_shards.decision.backends import JevBackend, RulesBackend
from nougen_shards.decision.backends.base import json_schema, parse_values, receipt
from nougen_shards.decision.cache import MemoryCache
from nougen_shards.decision.telemetry import JsonlSink, MemorySink

Q = ChoiceSpec("label", ("A", "B", "C"))
REQ = DecisionRequest("t.ns", "1", {"x": 1}, (Q,))


class Fake:
    def __init__(self, name, values=(), exc=None, up=True, version="v1"):
        self.name, self._v, self._exc, self._up, self.version = name, values, exc, up, version
        self.calls = 0

    def available(self):
        return self._up

    def decide(self, request):
        self.calls += 1
        if self._exc:
            raise self._exc
        return receipt(request, self.name, "m", self.version, self._v, 1.0)


def rules(values, decisive):
    return RulesBackend(lambda r: (values, decisive, "R-test"))


# --- policy -------------------------------------------------------------
def test_entropy_and_margin():
    assert normalized_entropy({"a": 1.0, "b": 0.0}) == pytest.approx(0, abs=1e-9)
    assert normalized_entropy({"a": .5, "b": .5}) == pytest.approx(1.0)
    assert margin({"a": .7, "b": .2}) == pytest.approx(.5)
    assert margin({"a": 1.0}) == 1.0


def test_confidence_is_not_authority():
    p = DecisionPolicy()
    assert not can_auto_accept(DecisionValue("k", "A", 0.0), p)  # uncalibrated
    assert can_auto_accept(DecisionValue("k", "A", 0.95), p)
    # confident top-1 but a close runner-up: refuse
    assert not can_auto_accept(DecisionValue("k", "A", 0.95, {"A": .5, "B": .45, "C": .05}), p)
    assert can_auto_accept(DecisionValue("k", "A", 0.97, {"A": .97, "B": .02, "C": .01}), p)


# --- hashing ------------------------------------------------------------
def test_hash_changes_with_schema_and_backend_version():
    h = canonical_hash(REQ, "v1")
    assert h == canonical_hash(DecisionRequest("t.ns", "1", {"x": 1}, (Q,)), "v1")
    assert h != canonical_hash(REQ, "v2")
    assert h != canonical_hash(DecisionRequest("t.ns", "2", {"x": 1}, (Q,)), "v1")


# --- schema / parse -----------------------------------------------------
def test_schema_and_parse_are_strict():
    req = DecisionRequest("n", "1", {}, (Q, ScoreSpec("s", 0, 1), NoulSpec("n")))
    sch = json_schema(req)
    assert sch["properties"]["label"]["enum"] == ["A", "B", "C"]
    ok = parse_values(req, json.dumps({"label": "B", "s": 0.5, "n": None}))
    assert [v.value for v in ok] == ["B", 0.5, None]
    assert parse_values(req, json.dumps({"label": "Z", "s": 0.5, "n": True})) == ()
    assert parse_values(req, json.dumps({"label": "A", "s": 2, "n": True})) == ()
    assert parse_values(req, json.dumps({"label": "A", "s": True, "n": True})) == ()
    assert parse_values(req, json.dumps({"label": "A", "s": 0.1})) == ()
    assert parse_values(req, "nope") == ()


# --- plane --------------------------------------------------------------
def test_decisive_rule_wins_and_models_never_called():
    m = Fake("ollama", (DecisionValue("label", "B"),))
    sink = MemorySink()
    r = DecisionPlane({"rules": rules((DecisionValue("label", "A", 1.0),), True), "ollama": m},
                      receipt_sink=sink).decide(REQ)
    assert (r.backend, r.value("label"), r.escalation) == ("rules", "A", Escalation.ACCEPT)
    assert m.calls == 0 and sink.receipts == [r]


def test_indecisive_rule_falls_through_and_attempts_are_recorded():
    plane = DecisionPlane({
        "rules": rules((DecisionValue("label", "C"),), False),
        "jev": JevBackend(),
        "ollama": Fake("ollama", exc=TimeoutError()),
        "structured_llm": Fake("structured_llm", (DecisionValue("label", "B"),)),
    })
    r = plane.decide(REQ)
    assert r.backend == "structured_llm" and r.value("label") == "B"
    # uncalibrated model answer is never auto-accepted
    assert r.escalation == Escalation.LLM
    outcomes = [(a["backend"], a["outcome"]) for a in r.provenance["attempts"]]
    assert outcomes == [("rules", "rule"), ("jev", "unavailable"), ("ollama", "error"),
                        ("structured_llm", "llm")]


def test_off_menu_falls_through_then_abstains():
    plane = DecisionPlane({"ollama": Fake("ollama", ()), "structured_llm": Fake("structured_llm", up=False)})
    r = plane.decide(REQ)
    assert r.escalation == Escalation.ABSTAIN and r.backend == "none"
    assert [a["outcome"] for a in r.provenance["attempts"]] == ["off_menu", "unavailable"]


def test_calibrated_model_can_be_accepted_but_criticality_forces_human():
    v = (DecisionValue("label", "A", 0.99, {"A": .99, "B": .005, "C": .005}),)
    plane = DecisionPlane({"ollama": Fake("ollama", v)})
    assert plane.decide(REQ).escalation == Escalation.ACCEPT
    hot = DecisionRequest("t.ns", "1", {"x": 1}, (Q,), criticality="destructive")
    assert plane.decide(hot).escalation == Escalation.HUMAN
    # destructive also overrides a decisive rule
    rp = DecisionPlane({"rules": rules((DecisionValue("label", "A", 1.0),), True)})
    assert rp.decide(hot).escalation == Escalation.HUMAN


def test_cache_hit_skips_backend_and_is_flagged():
    m = Fake("ollama", (DecisionValue("label", "B"),))
    plane = DecisionPlane({"ollama": m}, cache=MemoryCache())
    first, second = plane.decide(REQ), plane.decide(REQ)
    assert m.calls == 1 and not first.cache_hit and second.cache_hit
    assert second.value("label") == "B"


def test_jsonl_sink_round_trips(tmp_path):
    sink = JsonlSink(tmp_path / "r.jsonl")
    DecisionPlane({"rules": rules((DecisionValue("label", "A", 1.0),), True)}, receipt_sink=sink).decide(REQ)
    row = json.loads((tmp_path / "r.jsonl").read_text().splitlines()[0])
    assert row["escalation"] == "accept" and row["values"][0]["value"] == "A"


def test_specs_validate():
    with pytest.raises(ValueError):
        ChoiceSpec("k", ())
    with pytest.raises(ValueError):
        ChoiceSpec("k", ("A", "A"))
    with pytest.raises(ValueError):
        ScoreSpec("s", 1, 1)
    with pytest.raises(ValueError):
        DecisionRequest("n", "1", {}, (Q, Q))


@pytest.mark.parametrize("raw,want", [("", "off"), ("shadow", "shadow"), ("ENFORCE", "enforce"),
                                      ("enfroce", "off"), ("on", "off")])
def test_mode_fails_closed(monkeypatch, raw, want):
    from nougen_shards.decision.policy import mode
    monkeypatch.setenv("NOUGEN_DECISION_PLANE", raw)
    assert mode() == want

from nougen_shards.decision import Escalation
from nougen_shards.decision.backends.base import receipt
from nougen_shards.decision.domains import relay
from nougen_shards.decision.plane import DecisionPlane
from nougen_shards.decision.types import DecisionValue


class Fake:
    name, version = "ollama", "v"

    def __init__(self, label):
        self.label, self.calls = label, 0

    def available(self):
        return True

    def decide(self, request):
        self.calls += 1
        return receipt(request, "ollama", "m", "v", (DecisionValue("label", self.label),), 1.0)


def plane(model):
    return DecisionPlane({"rules": relay.default_plane().backends["rules"], "ollama": model})


def test_owner_ask_is_decided_by_rules_and_surfaces():
    leg = {"id": "x", "status": "open", "goal": "Dave to decide: lock canon?"}
    m = Fake("STATUS_FYI")
    r = relay.triage_leg(leg, "phoebus", plane(m))
    assert r.backend == "rules" and r.value("label") == "NEEDS_OWNER" and relay.surfaces(r)
    assert m.calls == 0


def test_dead_letter_is_never_closed_on_status_alone():
    leg = {"id": "y", "status": "dead_letter", "goal": "Build the thing"}
    m = Fake("ACTIONABLE")
    r = relay.triage_leg(leg, "phoebus", plane(m))
    assert m.calls == 1 and r.backend == "ollama"
    assert r.escalation == Escalation.LLM and relay.surfaces(r)


def test_request_carries_the_rule_menu_and_leg_provenance():
    req = relay.request_for({"id": "z", "goal": "g", "junk": 1}, "phoebus")
    assert req.questions[0].options == tuple(relay.LABELS)
    assert "junk" not in req.state and req.provenance["leg_id"] == "z"


def test_complete_with_recorded_failures_is_not_trusted():
    leg = {"id": "w", "status": "complete", "retry_count": "2",
           "failures": "[{'attempt': 2, 'error': 'non-zero exit (1)'}]", "goal": "Consolidate research"}
    m = Fake("ACTIONABLE")
    r = relay.triage_leg(leg, "phoebus", plane(m))
    assert m.calls == 1 and relay.surfaces(r)


def test_clean_complete_is_closed_by_rules():
    leg = {"id": "v", "status": "complete", "failures": "[]", "goal": "Done thing"}
    m = Fake("ACTIONABLE")
    r = relay.triage_leg(leg, "phoebus", plane(m))
    assert m.calls == 0 and r.value("label") == "CLOSED" and not relay.surfaces(r)

import math

import pytest

from nougen_shards.decision import ChoiceSpec, DecisionRequest, NoulSpec, ScoreSpec
from nougen_shards.decision.backends import ollama_prob as op
from nougen_shards.decision.backends.ollama_prob import OllamaProbBackend, fit_temperature, softmax


def _resp(**tops):
    return {"logprobs": [{"token": max(tops, key=tops.get),
                          "top_logprobs": [{"token": k, "logprob": v} for k, v in tops.items()]}]}


def _backend(monkeypatch, replies, **kw):
    it = iter(replies)
    monkeypatch.setattr(op._http, "post", lambda *a, **k: next(it))
    return OllamaProbBackend(model="m", **kw)


REQ = DecisionRequest("t.ns", "1", {"x": 1}, (ChoiceSpec("route", ("fast", "strong", "code")),))


def test_normalize_host_handles_bare_bind_address():
    n = op.normalize_host
    assert n("0.0.0.0") == "http://127.0.0.1:11434" and n("") == "http://127.0.0.1:11434"
    assert n("box:9999") == "http://box:9999" and n("https://h:1/") == "https://h:1"


def test_softmax_sums_to_one_and_temperature_flattens():
    p1, p2 = softmax([2, 0, 0]), softmax([2, 0, 0], 4.0)
    assert sum(p1) == pytest.approx(1) and p2[0] < p1[0]


def test_probabilities_come_from_letter_logprobs(monkeypatch):
    b = _backend(monkeypatch, [_resp(B=-0.1, A=-2.5, C=-3.0, X=-0.05)])
    v = b.decide(REQ).values[0]
    assert v.value == "strong" and v.confidence == pytest.approx(v.probabilities["strong"])
    assert sum(v.probabilities.values()) == pytest.approx(1, abs=1e-4)
    assert v.confidence > 0.85  # the stray "X" token is ignored


def test_temperature_lowers_overconfidence(monkeypatch):
    hot = _backend(monkeypatch, [_resp(A=-0.1, B=-3.0, C=-3.0)], temperature=3.0).decide(REQ).values[0]
    raw = _backend(monkeypatch, [_resp(A=-0.1, B=-3.0, C=-3.0)]).decide(REQ).values[0]
    assert hot.confidence < raw.confidence and hot.value == raw.value == "fast"


def test_noul_maps_yes_no_unknown(monkeypatch):
    req = DecisionRequest("t", "1", {}, (NoulSpec("ok"),))
    v = _backend(monkeypatch, [_resp(B=-0.05, A=-3.5, C=-4.0)]).decide(req).values[0]
    assert v.value is False and "null" in v.probabilities


def test_missing_letters_void_the_reply(monkeypatch):
    assert _backend(monkeypatch, [_resp(Z=-0.1)]).decide(REQ).values == ()


def test_score_question_voids_and_transport_error_voids(monkeypatch):
    req = DecisionRequest("t", "1", {}, (ScoreSpec("s", 0, 1),))
    assert _backend(monkeypatch, []).decide(req).values == ()
    def boom(*a, **k):
        raise OSError("down")
    monkeypatch.setattr(op._http, "post", boom)
    assert OllamaProbBackend(model="m").decide(REQ).values == ()


def test_fit_temperature_recovers_overconfidence():
    # logits claim ~99% for the top class but it is right only 2 of 3 times
    data = [([5.0, 0.0, 0.0], 0), ([5.0, 0.0, 0.0], 0), ([5.0, 0.0, 0.0], 1)]
    t = fit_temperature(data)
    assert t > 1.5
    assert -sum(math.log(softmax(lg, t)[y]) for lg, y in data) < -sum(math.log(softmax(lg)[y]) for lg, y in data)
    assert fit_temperature([]) == 1.0


def test_rotation_cancels_position_bias(monkeypatch):
    # the model always says the letter B, whatever the option order: rotations must flatten that
    monkeypatch.setattr(op._http, "post", lambda *a, **k: _resp(B=-0.05, A=-4.0, C=-4.0))
    b = OllamaProbBackend(model="m", rotations=3)
    v = b.decide(REQ).values[0]
    assert max(v.probabilities.values()) - min(v.probabilities.values()) < 0.01
    assert b.version.endswith(":r3")

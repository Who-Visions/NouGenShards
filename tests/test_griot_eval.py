"""Hermetic tests for the Griot eval harness and the Reflexion pass.

No DB, no Ollama, no cloud: every model-touching path is monkeypatched, and the
eval harness exercises only Griot's deterministic pure functions.
"""

from nougen_shards import griot, griot_eval


# -- (A) Eval harness ---------------------------------------------------

def test_eval_parse_default_parser_passes():
    res = griot_eval.eval_parse()
    assert res.score == 1.0
    assert res.passed is True
    assert res.threshold == 0.95


def test_eval_parse_empty_parser_fails():
    res = griot_eval.eval_parse(parser=lambda content: [])
    # The empty-expected golden case still scores F1 1.0, so the mean is < 1.0
    # but not 0.0 — assert it falls below threshold and is marked failing.
    assert res.score < 0.95
    assert res.passed is False


def test_eval_verdicts_passes():
    res = griot_eval.eval_verdicts()
    assert res.score == 1.0
    assert res.passed is True
    assert res.threshold == 1.0


def test_groundedness_all_present():
    assert griot_eval.groundedness("the SQLite rule and Docker rule",
                                   ["SQLite", "Docker"]) == 1.0


def test_groundedness_none_present():
    assert griot_eval.groundedness("nothing", ["SQLite", "Docker"]) == 0.0


def test_groundedness_empty_subjects():
    assert griot_eval.groundedness("x", []) == 1.0


def test_run_all_passes_with_two_evals():
    summary = griot_eval.run_all()
    assert summary["passed"] is True
    assert len(summary["evals"]) == 2


def test_run_all_verbose_includes_detail():
    summary = griot_eval.run_all(verbose=True)
    assert len(summary["evals"]) == 2
    for ev in summary["evals"]:
        assert "detail" in ev


def test_run_all_nonverbose_omits_detail():
    summary = griot_eval.run_all()
    for ev in summary["evals"]:
        assert "detail" not in ev


def test_golden_sets_nonempty():
    assert len(griot_eval.GOLDEN_PARSE_CASES) > 0
    assert len(griot_eval.GOLDEN_VERDICT_CASES) > 0


# -- (B) Reflexion pass -------------------------------------------------

def _make_griot(monkeypatch, complete_impl):
    """Build a Griot with recall stubbed and _complete replaced."""
    g = griot.Griot()
    monkeypatch.setattr(g, "recall", lambda query: "RECALLED CONTEXT HERE")
    monkeypatch.setattr(g, "_complete", complete_impl)
    return g


def test_chat_no_reflect_returns_draft(monkeypatch):
    calls = []

    def fake_complete(messages):
        calls.append(messages)
        return '{"answer":"plain"}'

    g = _make_griot(monkeypatch, fake_complete)
    out = g.chat("hello", reflect=False)
    assert out == "plain"
    # Exactly one completion: the draft action, no reflection.
    assert len(calls) == 1


def test_chat_reflect_applies_correction(monkeypatch):
    scripted = iter([
        '{"answer":"draft text"}',
        '{"ok":false,"answer":"corrected text"}',
    ])

    def fake_complete(messages):
        return next(scripted)

    g = _make_griot(monkeypatch, fake_complete)
    out = g.chat("hello", reflect=True)
    assert out == "corrected text"


def test_reflect_none_returns_draft(monkeypatch):
    g = _make_griot(monkeypatch, lambda messages: None)
    assert g._reflect("the draft", "ctx") == "the draft"


def test_reflect_ok_true_returns_fixed(monkeypatch):
    g = _make_griot(monkeypatch, lambda messages: '{"ok":true,"answer":"fixed"}')
    assert g._reflect("the draft", "ctx") == "fixed"


def test_reflect_garbage_returns_draft(monkeypatch):
    g = _make_griot(monkeypatch, lambda messages: "not json at all !!!")
    assert g._reflect("the draft", "ctx") == "the draft"


def test_chat_reflect_complete_none_is_noop(monkeypatch):
    counter = {"n": 0}

    def fake_complete(messages):
        counter["n"] += 1
        if counter["n"] == 1:
            return '{"answer":"draft"}'
        return None

    g = _make_griot(monkeypatch, fake_complete)
    out = g.chat("hello", reflect=True)
    assert out == "draft"
    # Two calls: the draft action, then the reflection (which returns None).
    assert counter["n"] == 2

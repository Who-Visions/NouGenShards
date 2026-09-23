import json

import pytest

from nougen_shards import relay_triage_model as m
from nougen_shards.relay_triage import LABELS

LEG = {"id": "20260921T000000Z__blade1tb__x", "machine": "blade1tb", "agent": "x",
       "status": "open", "goal": "Dave to decide: lock the canon?", "body": ""}


def _fake(label):
    return lambda prompt, timeout: label


def test_parse_accepts_only_menu_labels():
    assert m._parse(json.dumps({"label": "ACTIONABLE"})) == "ACTIONABLE"
    assert m._parse(json.dumps({"label": "act"})) is None
    assert m._parse("not json") is None
    assert m._parse("[]") is None


def test_schema_enum_is_the_rule_menu():
    assert m._SCHEMA["properties"]["label"]["enum"] == list(LABELS)
    assert set(m._GLOSS) == set(LABELS)


def test_first_backend_that_answers_wins(monkeypatch):
    monkeypatch.setitem(m.BACKENDS, "ollama", _fake(None))
    monkeypatch.setitem(m.BACKENDS, "openrouter", _fake("NEEDS_OWNER"))
    v = m.classify_model(LEG, "phoebus", backends="ollama,openrouter")
    assert v.label == "NEEDS_OWNER" and v.rule == "M-openrouter"


def test_backend_exception_falls_through_and_all_fail_is_none(monkeypatch):
    def boom(prompt, timeout):
        raise TimeoutError
    monkeypatch.setitem(m.BACKENDS, "ollama", boom)
    monkeypatch.setitem(m.BACKENDS, "openrouter", _fake(None))
    assert m.classify_model(LEG, "phoebus") is None


def test_unknown_backend_name_is_skipped(monkeypatch):
    monkeypatch.setitem(m.BACKENDS, "ollama", _fake("STATUS_FYI"))
    assert m.classify_model(LEG, "phoebus", backends="nope,ollama").label == "STATUS_FYI"


def test_shadow_logs_and_compares_surface(monkeypatch, tmp_path):
    monkeypatch.setitem(m.BACKENDS, "ollama", _fake("ACTIONABLE"))
    log = tmp_path / "s.jsonl"
    row = m.shadow(LEG, "phoebus", backends="ollama", log=log)
    assert row["rule"] == "NEEDS_OWNER" and row["model"] == "ACTIONABLE"
    assert row["agree"] is False and row["agree_surface"] is True  # both surface
    assert json.loads(log.read_text().splitlines()[0])["id"] == LEG["id"]


def test_shadow_with_no_model_answer_never_agrees(monkeypatch):
    monkeypatch.setitem(m.BACKENDS, "ollama", _fake(None))
    row = m.shadow(LEG, "phoebus", backends="ollama")
    assert row["model"] is None and row["agree"] is False and row["agree_surface"] is False


@pytest.mark.parametrize("key", ["", "sk-test"])
def test_openrouter_without_key_makes_no_call(monkeypatch, key):
    monkeypatch.setenv("OPENROUTER_API_KEY", key)
    monkeypatch.setattr(m, "_openrouter_key", lambda: key)
    calls = []
    monkeypatch.setattr(m, "_post", lambda *a, **k: calls.append(1) or {"choices": [{"message": {"content": '{"label":"CLOSED"}'}}]})
    out = m._openrouter("p", 1)
    assert (out, len(calls)) == ((None, 0) if not key else ("CLOSED", 1))

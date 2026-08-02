"""Reading the fleet's three handoff dialects as one corpus.

Samples are the real shapes, taken from records on disk: a NouGenQ claim, a
NouGenRelay leg, a NouGenShards handoff.
"""
import json

import pytest

from nougen_shards import handoff_dialects as D

CLAIM = {  # NouGenQ tools/git_handoff.py
    "machine": "blade1tb", "agent": "claude-cli", "branch": "uploads",
    "goal": "dev port resolves per machine", "scope": "package.json,scripts/dev.mjs",
    "status": "active", "created_utc": "2026-07-31T23:09:35Z",
    "released_utc": None, "ttl_hours": 4, "sha": "7e99d15",
}
LEG = {  # NouGenRelay
    "id": "20260731T190313Z__blade1tb__claude-cli", "machine": "blade1tb",
    "agent": "claude-cli", "branch": "uploads", "goal": "extract relay protocol",
    "status": "released", "created_utc": "2026-07-31T19:03:13Z",
    "sha": "abc1234", "stack": "next 16.2.10", "dirty": False, "remote": "origin",
}
HANDOFF = {  # NouGenShards registry
    "handoff_id": "20260731_144611_whoart_main", "timestamp": "2026-07-31T14:46:11",
    "agent": "claude-cli", "machine": {"host": "whoart", "machine_id": "ff00ff00"},
    "goal": "transport confirmed, naming collision needs GM",
    "git": {"branch": "main"}, "status": "acknowledged",
    "acknowledged_by": "claude-cli", "tasks": {"raw_count": 0}, "session_id": "abc",
}


# --- dialect detection ----------------------------------------------------

@pytest.mark.parametrize("record,expected", [
    (CLAIM, "claim"), (LEG, "leg"), (HANDOFF, "handoff"), ({"nothing": 1}, "unknown"),
])
def test_dialect_is_detected_by_shape(record, expected):
    assert D.detect_dialect(record) == expected


def test_a_claim_stays_a_claim_wherever_it_lands():
    """Records travel between repos. Classifying by directory would make a
    NouGenQ claim copied into the registry answer the wrong question."""
    assert D.detect_dialect(dict(CLAIM)) == "claim"


# --- the fields they genuinely share --------------------------------------

def test_machine_reads_from_a_bare_string_or_a_stamp_dict():
    assert D.normalise(CLAIM)["machine"] == "blade1tb"
    assert D.normalise(HANDOFF)["machine"] == "whoart"


def test_the_three_time_field_names_all_resolve():
    assert D.normalise(CLAIM)["when"].startswith("2026-07-31T23:09")
    assert D.normalise(HANDOFF)["when"].startswith("2026-07-31T14:46")


def test_branch_reads_from_a_nested_git_block_or_a_flat_field():
    assert D.normalise(LEG)["branch"] == "uploads"
    assert D.normalise(HANDOFF)["branch"] == "main"


def test_a_record_with_no_id_field_falls_back_to_its_filename(tmp_path):
    p = tmp_path / "20260731T230935Z__blade1tb__claude-cli.json"
    p.write_text(json.dumps(CLAIM))
    assert D.normalise(CLAIM, p)["id"] == "20260731T230935Z__blade1tb__claude-cli"


# --- status vocabulary ----------------------------------------------------

def test_released_and_complete_are_the_same_event():
    """A claim ending and work finishing are one thing seen from two sides."""
    assert D.normalise(dict(LEG, status="released"))["status"] == "done"
    assert D.normalise(dict(HANDOFF, status="complete"))["status"] == "done"


def test_acknowledged_is_not_flattened_into_held():
    """An ack means a transfer was ACCEPTED — a stronger claim than merely
    working. Merging the two would lose the read-back entirely."""
    assert D.normalise(HANDOFF)["status"] == "accepted"
    assert D.normalise(CLAIM)["status"] == "held"


def test_the_original_status_word_is_preserved():
    assert D.normalise(CLAIM)["raw_status"] == "active"


# --- nothing is discarded -------------------------------------------------

def test_dialect_specific_fields_survive_in_extra():
    """A converged view that silently drops `scope` is worse than none: it
    looks complete while answering 'who is touching this file' with silence."""
    assert D.normalise(CLAIM)["extra"]["ttl_hours"] == 4
    assert D.normalise(LEG)["extra"]["stack"] == "next 16.2.10"
    assert D.normalise(HANDOFF)["extra"]["session_id"] == "abc"


def test_scope_is_first_class_because_only_claims_have_it():
    assert D.normalise(CLAIM)["scope"] == ["package.json", "scripts/dev.mjs"]
    assert D.normalise(LEG)["scope"] is None


# --- corpus ---------------------------------------------------------------

def _write(root, name, record):
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(json.dumps(record))


def test_the_corpus_spans_repos_and_sorts_by_the_records_own_clock(tmp_path):
    _write(tmp_path / "nougenq", "a.json", CLAIM)
    _write(tmp_path / "relay", "b.json", LEG)
    _write(tmp_path / "shards", "c.json", HANDOFF)
    corpus = D.read_corpus([tmp_path / "nougenq", tmp_path / "relay", tmp_path / "shards"])

    assert [r["dialect"] for r in corpus] == ["claim", "leg", "handoff"]
    assert corpus[0]["when"] > corpus[-1]["when"]


def test_one_unreadable_record_does_not_take_the_fleet_view_down(tmp_path):
    _write(tmp_path / "r", "good.json", CLAIM)
    (tmp_path / "r" / "half-written.json").write_text("{not json")
    (tmp_path / "r" / "a-list.json").write_text("[]")
    assert len(D.read_corpus([tmp_path / "r"])) == 1


def test_a_missing_root_is_not_an_error(tmp_path):
    assert D.read_corpus([tmp_path / "never-existed"]) == []


# --- the query this exists for --------------------------------------------

def test_active_claims_finds_held_claims_only():
    records = [D.normalise(r) for r in (CLAIM, LEG, HANDOFF)]
    held = D.active_claims(records)
    assert len(held) == 1 and held[0]["machine"] == "blade1tb"


def test_a_released_claim_is_not_active():
    assert D.active_claims([D.normalise(dict(CLAIM, status="released"))]) == []


def test_two_machines_claiming_one_path_is_surfaced():
    """The failure this converged view exists to catch: before it, a claim on
    NouGenQ was invisible to the registry, so two boxes could edit the same
    files with both registries looking quiet."""
    other = dict(CLAIM, machine="whoart", scope="package.json,src/lib/twitch.ts")
    clashes = D.conflicting_scopes([D.normalise(CLAIM), D.normalise(other)])
    assert len(clashes) == 1
    assert clashes[0]["machines"] == ["blade1tb", "whoart"]
    assert clashes[0]["paths"] == ["package.json"]


def test_one_machine_holding_two_claims_is_not_a_conflict():
    second = dict(CLAIM, scope="package.json,other.ts")
    assert D.conflicting_scopes([D.normalise(CLAIM), D.normalise(second)]) == []


def test_disjoint_scopes_do_not_conflict():
    other = dict(CLAIM, machine="whoart", scope="README.md")
    assert D.conflicting_scopes([D.normalise(CLAIM), D.normalise(other)]) == []


def test_the_older_acked_spelling_maps_too():
    """Five records in the live registry use `acked`. Unmapped they fell
    through as their own status, invisible to any query for accepted
    transfers — found by running the reader over the real corpus."""
    assert D.normalise(dict(HANDOFF, status="acked"))["status"] == "accepted"


def test_every_status_the_fleet_writes_is_mapped():
    """The vocabularies actually emitted by the three tools, pinned so a new
    word has to be mapped deliberately rather than silently passing through."""
    for word in ("open", "active", "claimed", "acknowledged", "acked",
                 "in_progress", "blocked", "released", "complete", "completed"):
        assert word in D._STATUS, f"{word} is written by the fleet but unmapped"


def test_an_unmapped_status_passes_through_rather_than_vanishing():
    """Unknown words must stay legible, not become None or a crash."""
    out = D.normalise(dict(CLAIM, status="quarantined"))
    assert out["status"] == "quarantined" and out["raw_status"] == "quarantined"


def test_a_held_handoff_is_not_reported_as_a_claim():
    """One live record is an in_progress handoff, not a claim. It maps to
    `held` correctly but must not answer the may-I-edit-this-file query."""
    rec = D.normalise(dict(HANDOFF, status="in_progress"))
    assert rec["status"] == "held"
    assert D.active_claims([rec]) == []



# --- capture must not block on an optional enrichment ---------------------

def test_density_scoring_is_off_by_default(monkeypatch):
    """A memory write must not wait on a model.

    Measured before this: 48s per capture, of which the SQLite write was 0.03s
    and the gzip fallback 0.0000s. The whole cost was one local Ollama
    inference producing a single float. It never failed — it waited, which is
    why it survived so long.
    """
    from nougen_shards import core
    monkeypatch.delenv("NOUGEN_DENSITY_LLM", raising=False)
    monkeypatch.setattr(core, "_llm_scoring_enabled", lambda: False)

    called = []
    monkeypatch.setattr(core, "_llm_density", lambda c: called.append(c) or 0.9)
    score = core.calculate_contrastive_perplexity("some text")

    assert called == [], "no model may be consulted unless opted in"
    assert score == core.compression_density("some text")


def test_the_gate_refuses_under_pytest_regardless_of_the_env():
    """Belt and braces: even opted in, a test run never calls out."""
    import os
    from nougen_shards.core import _llm_scoring_enabled
    os.environ["NOUGEN_DENSITY_LLM"] = "1"
    try:
        assert _llm_scoring_enabled() is False
    finally:
        os.environ.pop("NOUGEN_DENSITY_LLM", None)


def test_the_scorer_does_not_reference_its_callers_locals():
    """It was extracted from the caller and kept returning `fallback_score`,
    a name that no longer existed in its scope — a NameError on the
    no-provider path."""
    import inspect
    from nougen_shards.core import _llm_density
    assert "fallback_score" not in inspect.getsource(_llm_density)


def test_the_budget_bounds_a_call_already_in_flight(monkeypatch):
    """The first version checked a deadline only BETWEEN provider attempts, so
    it gated whether a call started and did nothing about one already running —
    measured at 48s with the budget set to 3."""
    import time as _t
    from nougen_shards import core
    monkeypatch.setattr(core, "_llm_scoring_enabled", lambda: True)
    monkeypatch.setenv("NOUGEN_DENSITY_TIMEOUT", "0.3")
    monkeypatch.setattr(core, "_llm_density", lambda c: (_t.sleep(30), 0.9)[1])

    started = _t.perf_counter()
    score = core.calculate_contrastive_perplexity("text")
    elapsed = _t.perf_counter() - started

    assert elapsed < 5, f"budget not enforced: took {elapsed:.1f}s"
    assert score == core.compression_density("text")


def test_an_opted_in_score_is_used_when_it_arrives_in_time(monkeypatch):
    from nougen_shards import core
    monkeypatch.setattr(core, "_llm_scoring_enabled", lambda: True)
    monkeypatch.setattr(core, "_llm_density", lambda c: 0.77)
    assert core.calculate_contrastive_perplexity("text") == 0.77

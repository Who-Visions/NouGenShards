"""Wing grounding: acquire_knowledge pulls real vault recall, falls back cleanly."""
import types

import pytest

from nougen_shards import evolution


@pytest.fixture
def engine(tmp_path, monkeypatch):
    # Never touch a real model lane or the live vault from tests.
    monkeypatch.setattr(evolution, "get_best_available_client", lambda: None, raising=True)
    return evolution.EvolutionEngine(workspace_path=tmp_path, verbose=False)


def test_grounded_path_returns_vault_content(engine, monkeypatch):
    shards = [{"id": 1, "title": "t", "content": "subagent orchestration notes", "final_score": 0.9}]
    monkeypatch.setattr(evolution.core, "retrieve", lambda q, limit: shards)
    monkeypatch.setattr(evolution.core, "compile_recall_packet",
                        lambda s: "RECALL: subagent orchestration notes")
    grounding = engine.acquire_knowledge("claude subagent orchestration")
    assert "RECALL: subagent orchestration notes" in grounding
    assert grounding.startswith("Grounding for 'claude subagent orchestration':")


def test_empty_recall_falls_back_to_static(engine, monkeypatch):
    monkeypatch.setattr(evolution.core, "retrieve", lambda q, limit: [])
    grounding = engine.acquire_knowledge("anything at all")
    assert "FTS5" in grounding  # legacy static grounding
    assert grounding.startswith("Grounding for 'anything at all':")


def test_retrieve_exception_falls_back_not_crash(engine, monkeypatch):
    def boom(q, limit):
        raise RuntimeError("vault offline")
    monkeypatch.setattr(evolution.core, "retrieve", boom)
    grounding = engine.acquire_knowledge("resilience check")
    assert "FTS5" in grounding


def test_distill_failure_falls_back_to_raw_packet(engine, monkeypatch):
    monkeypatch.setenv("NOUGEN_EVOLVE_DISTILL", "1")
    monkeypatch.setattr(evolution.core, "retrieve",
                        lambda q, limit: [{"id": 1, "title": "t", "content": "x", "final_score": 0.5}])
    monkeypatch.setattr(evolution.core, "compile_recall_packet", lambda s: "RAW PACKET")

    def bad_chat(**kwargs):
        raise RuntimeError("lane down")
    engine.client = types.SimpleNamespace(chat=bad_chat, default_model="m")
    grounding = engine.acquire_knowledge("distill resilience")
    assert "RAW PACKET" in grounding


def test_virtual_task_survives_gate_tripping_grounding(engine):
    # Shard prose quoting destructive-looking SQL/shell must not fail the
    # gatekeeper scan of the generated script (payloads are base64-embedded).
    from nougen_shards import nougen_sandbox
    grounding = ("Grounding for 'sql cleanup': the video demonstrates "
                 "DELETE FROM users and rm -rf on a demo box, plus TRUNCATE tables.")
    script = engine.build_virtual_task("sql cleanup", grounding)
    out = nougen_sandbox.execute_sandboxed(script, language="python", trusted=True)
    assert "Virtual Task Passed" in out, out

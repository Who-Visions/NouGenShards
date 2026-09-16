"""Reconstructive recall prototype tests (synthetic fixture vault only)."""
import importlib.util
from pathlib import Path

import pytest

from nougen_shards.reconstruction import (
    SweepConfig, recognition_score, fingerprint, retrieval_angle_sweep, single_shot,
)

_FX_PATH = Path(__file__).parent / "fixtures" / "synthetic_reconstruction_vault.py"
_spec = importlib.util.spec_from_file_location("synthetic_reconstruction_vault", _FX_PATH)
fx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fx)


@pytest.fixture
def vaults():
    return fx.build_vaults()


@pytest.fixture
def cfg(monkeypatch):
    for name in ("NOUGEN_RECON_ANGLES", "NOUGEN_RECON_WEIGHTS", "NOUGEN_RECON_MAX_CALLS",
                 "NOUGEN_RECON_ACCEPT", "NOUGEN_RECON_MARGIN", "NOUGEN_RECON_MAX_MS"):
        monkeypatch.delenv(name, raising=False)
    return SweepConfig.from_env()


def sweep(q, vs, cfg):
    return retrieval_angle_sweep(q, vs, aliases=fx.ALIASES, known_entities=fx.ENTITIES, config=cfg)


# --- adversarial controls -------------------------------------------------

@pytest.mark.parametrize("query,expected", fx.GOOD_QUERIES)
def test_known_positive_control_single_shot_hits(vaults, cfg, query, expected):
    assert single_shot(query, vaults, known_entities=fx.ENTITIES, config=cfg).answer_key == expected


# --- bad-query recovery ---------------------------------------------------

@pytest.mark.parametrize("query,expected", [
    ("orch storage warning level", "T09"),
    ("orch cooling noise tweak", "T16"),
    ("did mira sign off on the books table layout", "T03"),
])
def test_bad_wording_recovered_by_sweep(vaults, cfg, query, expected):
    base = single_shot(query, fx.build_vaults(), known_entities=fx.ENTITIES, config=cfg)
    assert base.answer_key != expected  # the control: single shot really misses
    env = sweep(query, vaults, cfg)
    assert env.answer_key == expected
    assert env.calls <= cfg.max_calls
    assert env.vault_coverage["state"] == "complete_federated_recall"


def test_sweep_respects_call_budget(vaults, monkeypatch):
    monkeypatch.setenv("NOUGEN_RECON_MAX_CALLS", "2")
    env = retrieval_angle_sweep("orch storage warning level", vaults, aliases=fx.ALIASES,
                                known_entities=fx.ENTITIES, config=SweepConfig.from_env())
    assert env.calls <= 2
    assert env.stop_reason in {"budget_calls", "no_marginal_gain", "angles_exhausted"}


# --- partial-vault degradation -------------------------------------------

@pytest.mark.parametrize("down", [["beta"], ["alpha", "beta"], ["alpha", "beta", "gamma"]])
def test_partial_vault_never_proves_absence(cfg, down):
    vs = fx.build_vaults()
    # control: with everything up the target (T09 lives in gamma) is found
    assert sweep("orch storage warning level", fx.build_vaults(), cfg).answer_key == "T09"
    for v in vs:
        if v.name in down:
            v.available = False
    env = sweep("orch storage warning level", vs, cfg)
    assert env.absence_proven is False
    assert set(env.vault_coverage["failed"]) == set(down)
    if len(down) == 3:
        assert env.vault_coverage["state"] == "no_reachable_evidence"
        assert env.answer_key is None
        assert "no_candidates_absence_not_proven" in env.unresolved_gaps
    else:
        assert env.vault_coverage["state"] == "reconstructed_from_partial_evidence"
        assert env.answer_key == "T09"  # reachable evidence stays usable
        full = sweep("orch storage warning level", fx.build_vaults(), cfg)
        assert env.confidence < full.confidence  # resolution degrades


def test_target_vault_down_is_not_absence(cfg):
    vs = fx.build_vaults()
    for v in vs:
        if v.name == "gamma":  # holds T09
            v.available = False
    env = sweep("orch storage warning level", vs, cfg)
    assert env.answer_key != "T09"
    assert env.absence_proven is False
    assert "vault_unavailable:gamma" in env.unresolved_gaps


def test_absence_only_under_complete_exhausted_sweep(vaults, cfg):
    # control first: the same vaults do return evidence for a real query
    assert sweep("quill search timeout", fx.build_vaults(), cfg).answer_key == "T06"
    env = sweep("zzqx nonexistent wibble", vaults, cfg)
    assert env.candidate_sources == []
    assert env.absence_proven is True


def test_dead_vault_not_retried(cfg):
    vs = fx.build_vaults()
    vs[1].available = False
    sweep("orch storage warning level", vs, cfg)
    assert vs[1].calls == 1


# --- association hops -----------------------------------------------------

def test_association_hop_recovers_linked_decision(vaults, monkeypatch):
    monkeypatch.setenv("NOUGEN_RECON_ANGLES", "relay,association")
    # force the expansion step: a confident first angle would otherwise stop the sweep
    monkeypatch.setenv("NOUGEN_RECON_CONFIDENCE_TARGET", "1.01")
    env = retrieval_angle_sweep("the handoff about quill pipe hostname", vaults, aliases=fx.ALIASES,
                                known_entities=fx.ENTITIES, config=SweepConfig.from_env())
    keys = {c.key for c in env.candidate_sources}
    assert "T05" in keys and "A05" in keys
    assert any(h.from_key == "T05" and h.to_key == "A05" and h.relation == "decided_by"
               for h in env.association_hops)
    assert env.answer_key == "T05"  # the query asked for the handoff itself
    assert len(env.association_hops) == 1  # edge deduped across sources


def test_relay_only_search_misses_decision_without_hop(vaults, monkeypatch):
    monkeypatch.setenv("NOUGEN_RECON_ANGLES", "relay")
    env = retrieval_angle_sweep("the handoff about quill pipe hostname", vaults, aliases=fx.ALIASES,
                                known_entities=fx.ENTITIES, config=SweepConfig.from_env())
    assert "T05" in {c.key for c in env.candidate_sources}  # control
    assert "A05" not in {c.key for c in env.candidate_sources}


# --- false-positive resistance --------------------------------------------

def test_retracted_lookalike_never_wins(vaults, cfg):
    env = sweep("lantern gateway port 8811", vaults, cfg)
    assert env.answer_key != "D01"
    assert env.correction_state.get("D01") == "retracted"
    assert any(r.key == "D01" and r.reason == "retracted" for r in env.rejected)


def test_entity_lookalike_rejected(vaults, cfg):
    env = sweep("when does orch do its snapshot job", vaults, cfg)
    assert env.answer_key == "T02"
    assert env.rival_margin >= cfg.rival_margin


def test_time_window_beats_newer_lookalike(vaults, cfg):
    env = sweep("heron vector model swap in february 2026", vaults, cfg)
    assert env.answer_key == "T07"
    assert env.time_coverage["window"][0] == "2026-02-01"


def test_ambiguous_rivals_withhold_answer(cfg):
    fp = fingerprint("dashboard colour tokens unified", fx.ALIASES, fx.ENTITIES)
    a = recognition_score({"title": "Sparrow dashboard colour tokens unified", "entities": ["sparrow"]}, fp, cfg.weights)[0]
    b = recognition_score({"title": "Kestrel dashboard colour tokens unified", "entities": ["kestrel"]}, fp, cfg.weights)[0]
    assert a == b  # control: no entity named, the two are indistinguishable
    env = sweep("dashboard colour tokens unified", fx.build_vaults(), cfg)
    assert env.answer_key is None
    assert "ambiguous_rival" in env.unresolved_gaps


def test_envelope_has_every_schema_field(vaults, cfg):
    d = sweep("quill lookup deadline bump", vaults, cfg).to_dict()
    for f in ("query", "query_fingerprint", "retrieval_angles", "candidate_sources",
              "association_hops", "vault_coverage", "time_coverage", "correction_state",
              "confidence", "reconstruction_summary", "unresolved_gaps"):
        assert f in d


def test_alias_map_is_opt_in(monkeypatch, tmp_path):
    from nougen_shards.reconstruction import load_alias_map
    monkeypatch.delenv("NOUGEN_RECON_ALIAS_MAP", raising=False)
    assert load_alias_map() == {}
    p = tmp_path / "aliases.json"
    p.write_text('{"ledger": ["books"]}', encoding="utf-8")
    monkeypatch.setenv("NOUGEN_RECON_ALIAS_MAP", str(p))
    assert load_alias_map() == {"ledger": ["books"]}
    monkeypatch.setenv("NOUGEN_RECON_ALIAS_MAP", str(tmp_path / "missing.json"))
    assert load_alias_map() == {}


def test_sweep_trigger_default_low_confidence(monkeypatch, vaults, cfg):
    from nougen_shards.reconstruction import should_sweep
    monkeypatch.delenv("NOUGEN_RECON_SWEEP_TRIGGER", raising=False)
    miss = single_shot("zzqx nonexistent term", vaults, config=cfg)
    assert should_sweep(miss, cfg) is True
    monkeypatch.setenv("NOUGEN_RECON_SWEEP_TRIGGER", "never")
    assert should_sweep(miss, cfg) is False


def test_fact_snapshot_supersession_resolver():
    from nougen_shards.reconstruction import resolve_fact_snapshot, FactSnapshot

    records = [
        {
            "canonical_key": "token_usage:fleet:YTD:2026",
            "as_of": "2026-09-14T00:00:00Z",
            "machine_values": {"blade1tb": 34.513, "phoebus": 10.0, "whoart": 10.981},
            "total": 55.494,
            "provenance_ids": ["shard_old"],
        },
        {
            "canonical_key": "token_usage:fleet:YTD:2026",
            "as_of": "2026-09-16T18:00:00Z",
            "machine_values": {"blade1tb": 40.0, "phoebus": 12.5, "whoart": 15.0},
            "total": 67.5,
            "provenance_ids": ["shard_new"],
        }
    ]

    resolved = resolve_fact_snapshot(records, "token_usage:fleet:YTD:2026")
    assert resolved is not None
    assert isinstance(resolved, FactSnapshot)
    assert resolved.as_of == "2026-09-16T18:00:00Z"
    assert resolved.total == 67.5
    assert resolved.completeness_state == "complete"
    assert resolved.provenance_ids == ["shard_new"]


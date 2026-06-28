"""
Tests for Griot's self-healing memory: confidence decay + contradiction
auto-reconciliation. All hermetic against a temp federated DB.
"""

import tempfile
from pathlib import Path

import pytest

from nougen_shards import griot
import nougen_shards.core as core


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Temp single-DB environment (mirrors test_dual_system.py)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(core, "GLOBAL_DIR", temp_path)
        monkeypatch.setattr(core, "get_db_path",
                            lambda index: temp_path / f"test_shards_{index}.db")
        monkeypatch.setattr(core, "get_routing_index", lambda fhash: 1)
        monkeypatch.setattr(core, "get_write_index", lambda fhash: 1)
        core.init_db(1)
        yield temp_path


def _insert(subject, predicate, confidence):
    conn = core.get_connection(1)
    try:
        conn.execute(
            "INSERT INTO semantic_knowledge (subject, predicate, confidence_score, "
            "domain_key, updated_at) VALUES (?, ?, ?, 'global', '2026-01-01T00:00:00Z')",
            (subject, predicate, confidence))
        conn.commit()
    finally:
        conn.close()


def _confidence(subject, predicate):
    conn = core.get_connection(1)
    try:
        row = conn.execute(
            "SELECT confidence_score FROM semantic_knowledge "
            "WHERE subject = ? AND predicate = ?", (subject, predicate)).fetchone()
        return row["confidence_score"] if row else None
    finally:
        conn.close()


# -- decay --------------------------------------------------------------

def test_decay_multiplies_confidence():
    _insert("SQLite", "timeout 10s", 1.0)
    res = griot.Griot.decay_confidence(factor=0.9)
    assert res["decayed"] == 1
    assert res["pruned"] == 0
    assert abs(_confidence("SQLite", "timeout 10s") - 0.9) < 1e-9


def test_decay_prunes_below_threshold():
    _insert("Stale", "old rule", 0.05)
    _insert("Fresh", "kept rule", 1.0)
    res = griot.Griot.decay_confidence(factor=0.9, prune_below=0.1)
    # Stale: 0.05 * 0.9 = 0.045 < 0.1 -> pruned
    assert res["pruned"] == 1
    assert _confidence("Stale", "old rule") is None
    assert _confidence("Fresh", "kept rule") is not None


def test_decay_no_prune_by_default():
    _insert("Low", "weak rule", 0.01)
    res = griot.Griot.decay_confidence(factor=0.5)
    assert res["pruned"] == 0
    assert _confidence("Low", "weak rule") is not None  # survives without prune


# -- reconciliation -----------------------------------------------------

def test_reconcile_demotes_losers():
    # Same subject, conflicting predicates with a clear confidence winner.
    _insert("Docker", "must use read-only root", 2.0)
    _insert("Docker", "may use writable root", 1.0)
    res = griot.Griot.reconcile_conflicts(penalty=0.5)
    assert res["groups_found"] == 1
    assert res["groups_reconciled"] == 1
    entry = res["reconciled"][0]
    assert entry["subject"] == "Docker"
    assert entry["winner"] == "must use read-only root"
    # Loser demoted 1.0 * 0.5 = 0.5; winner untouched.
    assert abs(_confidence("Docker", "may use writable root") - 0.5) < 1e-9
    assert abs(_confidence("Docker", "must use read-only root") - 2.0) < 1e-9


def test_reconcile_skips_ties():
    _insert("Port", "use 3000", 1.0)
    _insert("Port", "use 8080", 1.0)  # exact tie -> ambiguous, untouched
    res = griot.Griot.reconcile_conflicts(penalty=0.5)
    assert res["groups_found"] == 1
    assert res["groups_reconciled"] == 0
    assert _confidence("Port", "use 3000") == 1.0
    assert _confidence("Port", "use 8080") == 1.0


def test_reconcile_ignores_non_conflicts():
    _insert("Alpha", "rule a", 1.0)
    _insert("Beta", "rule b", 1.0)  # distinct subjects, no conflict
    res = griot.Griot.reconcile_conflicts()
    assert res["groups_found"] == 0
    assert res["groups_reconciled"] == 0


def test_reconcile_prunes_demoted_below_threshold():
    _insert("Cache", "ttl 30m", 2.0)
    _insert("Cache", "ttl 5m", 0.1)  # demoted 0.1*0.5=0.05 < 0.1 -> pruned
    res = griot.Griot.reconcile_conflicts(penalty=0.5, prune_below=0.1)
    assert res["groups_reconciled"] == 1
    assert _confidence("Cache", "ttl 5m") is None
    assert _confidence("Cache", "ttl 30m") == 2.0


# -- heal orchestrator --------------------------------------------------

def test_heal_runs_decay_then_reconcile():
    _insert("Docker", "read-only root", 2.0)
    _insert("Docker", "writable root", 1.0)
    g = griot.Griot()
    res = g.heal(decay_factor=0.9, penalty=0.5)
    assert res["decay"]["decayed"] == 2
    assert res["reconciliation"]["groups_reconciled"] == 1
    # After decay both *0.9 (2.0->1.8, 1.0->0.9); winner 1.8 kept,
    # loser 0.9 demoted *0.5 = 0.45.
    assert abs(_confidence("Docker", "read-only root") - 1.8) < 1e-9
    assert abs(_confidence("Docker", "writable root") - 0.45) < 1e-9


def test_heal_registered_as_tool():
    g = griot.Griot()
    assert "heal" in g.tools.names()

"""Relay 20261026T210020Z: /search buried an operator DECISION shard under doc
mirrors and Bash-error captures. Two causes, two pins:

1. _run_db_scans waited on grid DB 1 first, so one slow DB spent the shared
   deadline and DBs 2..9 were reported timed out although finished -> the core
   lane came back empty and only side-lane doc mirrors reached the caller.
2. RRF fuses by position only, so the KIND of shard never spoke. Recall priors
   now multiply the fused score by event_type / tag / title-shape weights.
"""
import threading
import time

from nougen_shards import core

QUERY = "which tool designs the screens and writes the code for the tutoring site"

BUILD_CHAIN = {
    "id": 31721, "_db_index": 7, "event_type": "DECISION", "utility_score": 1.0,
    "title": "Build chain: NouGenDesign (rules) -> Stitch (screens) -> Antigravity (build, own worktree) -> Claude (brief, review, ship)",
    "content": "Operator-approved build chain for the tutoring site back office.",
    "tags": '["build-chain", "stitch", "antigravity"]',
}
MPV_DOC = {
    "id": "vault_1_a", "_db_index": "vault_docs", "event_type": "LOCAL_VAULT", "utility_score": 1.0,
    "title": "mpv manual: screen and code options", "content": "--screen ... writes the code ...",
    "tags": '["indexer", "docs"]',
}
FIREBASE_DOC = {
    "id": "vault_1_b", "_db_index": "vault_docs", "event_type": "LOCAL_VAULT", "utility_score": 1.0,
    "title": "Firebase hosting: site tooling", "content": "tool for the site", "tags": '["indexer", "docs"]',
}
BASH_ERROR = {
    "id": 30382, "_db_index": 1, "event_type": None, "utility_score": 1.0,
    "title": "Bash error [92a4235cf93b167e]: Shell cwd was reset",
    "content": "Command: python tools/design_screens.py --site tutoring", "tags": '["claude-code", "bash-error"]',
}


def test_priors_rank_decision_above_mirrors_and_error_captures(monkeypatch):
    monkeypatch.delenv("NOUGEN_RECALL_PRIORS", raising=False)
    assert core.recall_prior_multiplier(BUILD_CHAIN) > 1.0
    assert core.recall_prior_multiplier(BASH_ERROR) < 1.0
    assert core.recall_prior_multiplier(MPV_DOC) < 1.0
    assert core.recall_prior_multiplier({"title": "plain", "tags": []}) == 1.0


def test_leg_query_puts_build_chain_in_top_3_after_fusion(monkeypatch):
    """Keyword lane ranks the DECISION 4th; two vault lanes rank the mirrors and
    the error capture first. Position-only RRF left the DECISION outside the top 3."""
    monkeypatch.delenv("NOUGEN_RECALL_PRIORS", raising=False)
    local = [BASH_ERROR, MPV_DOC, FIREBASE_DOC, BUILD_CHAIN]
    vault_a = [MPV_DOC, FIREBASE_DOC]
    vault_b = [BASH_ERROR, MPV_DOC]
    fused = core.reciprocal_rank_fusion([local, vault_a, vault_b], k=60, weights=[1.0, 0.35, 0.35])
    top3 = [(r["_db_index"], r["id"]) for r in fused[:3]]
    assert (7, 31721) in top3, [r["title"][:40] for r in fused]
    monkeypatch.setenv("NOUGEN_RECALL_PRIORS", "0")
    unweighted = core.reciprocal_rank_fusion([local, vault_a, vault_b], k=60, weights=[1.0, 0.35, 0.35])
    assert (7, 31721) not in [(r["_db_index"], r["id"]) for r in unweighted[:3]], "regression fixture no longer reproduces the burial"


def test_priors_disabled_is_neutral(monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_PRIORS", "0")
    assert core.recall_prior_multiplier(BUILD_CHAIN) == 1.0 == core.recall_prior_multiplier(BASH_ERROR)


def test_env_overrides_fallback_weights(monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_EVENT_TYPE_WEIGHTS", "decision:2.0")
    monkeypatch.setenv("NOUGEN_RECALL_TAG_WEIGHTS", "")
    monkeypatch.setenv("NOUGEN_RECALL_TITLE_PREFIX_WEIGHTS", "")
    assert core.recall_prior_multiplier(BUILD_CHAIN) == 2.0
    assert core.recall_prior_multiplier(BASH_ERROR) == 1.0


def test_run_db_scans_one_slow_db_does_not_starve_the_rest(monkeypatch):
    monkeypatch.setattr(core, "_retrieve_db_workers", lambda: 4)
    monkeypatch.setattr(core, "elevated_lane_timeout", lambda **k: 0.6)
    release = threading.Event()

    def scan(i):
        if i == 1:
            release.wait(5.0)  # DB 1 outlives the deadline
            return (["late"], False)
        return ([f"db{i}"], False)

    try:
        started = time.monotonic()
        out = dict(core._run_db_scans(scan))
        elapsed = time.monotonic() - started
    finally:
        release.set()
    assert out[1] == ([], True)
    assert all(out[i] == ([f"db{i}"], False) for i in range(2, core.MAX_DB_COUNT + 1)), out
    assert elapsed < 3.0

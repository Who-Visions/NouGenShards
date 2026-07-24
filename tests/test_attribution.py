"""Attribution-guided utility (AttriMem, arXiv 2607.21106) — the logging half.

What is asserted here, and what is deliberately NOT:

  * A caller can DECLARE which shards it used, and that declaration is durably
    recorded and usable as a ranking tiebreak.
  * When nobody declares anything, `observed_prior` changes NOTHING. The
    absence of a usage signal is reported as absence, never smoothed over.
  * Retrieval-time ACCESSED events are NOT attribution. Feeding rank back in as
    "contribution" would be a fabricated signal, so it must stay unwired.

The RL half of the paper (token-level local rewards + policy optimization) is
GPU-bound and out of scope on an 8GB-VRAM host; nothing here pretends to it.
"""
from datetime import datetime, timezone

import pytest

from nougen_shards import attribution, core, provenance


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Isolated history substrate; never touches the live vault."""
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(attribution, "ENABLED", True)
    attribution.invalidate_cache()
    yield tmp_path
    attribution.flush()
    attribution.invalidate_cache()


def _shard(shard_id, utility, db_index=1, title="local_note.md"):
    return {
        "id": shard_id,
        "_db_index": db_index,
        "file_hash": f"hash_{shard_id}",
        "title": title,
        "content": "body",
        "tags": "[]",
        "event_type": "DOCUMENTATION",
        "utility_score": utility,
        "timestamp": _now(),
    }


# --------------------------------------------------------------------------
# The honest baseline: no signal means no signal
# --------------------------------------------------------------------------

def test_no_usage_recorded_means_prior_is_unchanged(store, monkeypatch):
    monkeypatch.setattr(attribution, "TIEBREAK_ENABLED", True)
    item = _shard(1, 4.286875)
    assert attribution.observed_prior(item, 4.286875) == 4.286875
    assert "_attribution_credit" not in item


def test_tiebreak_is_off_by_default(store, monkeypatch):
    """It must not switch itself on before real usage data exists.

    Asserted as BEHAVIOUR: durable credit exists for the shard, and the default
    config still leaves the ranking prior untouched.
    """
    import queue as _q
    assert attribution.TIEBREAK_ENABLED is False

    # Real, durable, strong credit exists for this shard...
    monkeypatch.setattr(attribution, "_queue", _q.Queue(maxsize=attribution.QUEUE_MAX))
    monkeypatch.setattr(attribution, "_ensure_writer", lambda: None)
    assert attribution.record_usage([_shard(42, 1.0)], contribution=9.0) == 1
    row = attribution._queue.get_nowait()
    attribution._drain([row])
    attribution._queue.task_done()
    attribution.invalidate_cache()
    assert attribution.credit_for(42, 1) is not None

    # ...yet under the default config the prior is returned completely unchanged
    # and the item is not annotated: the tiebreak does not touch ranking.
    item = _shard(42, 4.286875)
    assert attribution.observed_prior(item, 4.286875) == 4.286875
    assert "_attribution_credit" not in item
    assert "_attribution_observations" not in item

    # Contrast: the SAME credit does move the prior once the flag is turned on
    # deliberately — so the assertion above is the default suppressing it, not
    # an absence of usage data.
    monkeypatch.setattr(attribution, "TIEBREAK_ENABLED", True)
    boosted = _shard(42, 4.286875)
    assert attribution.observed_prior(boosted, 4.286875) != 4.286875
    assert boosted["_attribution_credit"] > 0


def test_credit_for_unobserved_shard_is_none(store):
    assert attribution.credit_for(999, 1) is None


def test_accessed_events_are_not_treated_as_attribution(store, monkeypatch):
    """Retrieval rank must never launder itself into a contribution signal."""
    from nougen_shards import history
    monkeypatch.setattr(attribution, "TIEBREAK_ENABLED", True)
    history.log_event(7, 1, "ACCESSED")
    attribution.invalidate_cache()
    assert attribution.credit_for(7, 1) is None
    assert attribution.observed_prior(_shard(7, 2.0), 2.0) == 2.0


# --------------------------------------------------------------------------
# The explicit API
# --------------------------------------------------------------------------

def test_record_usage_persists_declared_shards(store):
    assert attribution.record_usage([_shard(11, 1.0)], query="logfire wiring") == 1
    attribution.flush()
    attribution.invalidate_cache()
    observed = attribution.credit_for(11, 1)
    assert observed is not None and observed[1] == 1


def test_record_usage_accepts_id_index_tuples(store):
    assert attribution.record_usage([(12, 3), (13, 3)]) == 2
    attribution.flush()
    attribution.invalidate_cache()
    assert attribution.credit_for(12, 3) is not None
    assert attribution.credit_for(13, 3) is not None


def test_federated_namespaced_db_index_is_preserved(store):
    """A bare int would credit a DIFFERENT shard on the primary grid."""
    item = _shard(14, 1.0, db_index="pull-clone:2")
    attribution.record_usage([item])
    attribution.flush()
    attribution.invalidate_cache()
    assert attribution.credit_for(14, "pull-clone:2") is not None
    assert attribution.credit_for(14, 2) is None


def test_unresolvable_refs_are_skipped_not_faked(store):
    assert attribution.record_usage([{"title": "no id"}, None, "junk"]) == 0


def test_record_usage_is_a_noop_when_disabled(store, monkeypatch):
    monkeypatch.setattr(attribution, "ENABLED", False)
    assert attribution.record_usage([_shard(15, 1.0)]) == 0


def test_write_is_non_blocking(store, monkeypatch):
    """The caller enqueues; it must not perform the SQLite write itself.

    Made deterministic (no sleeps, no thread race) by handing record_usage a
    private queue and stubbing the writer start: nothing can drain the row
    behind our back, so "not on disk yet" is a stable observation. An inline
    SQLite write inside record_usage fails the pre-drain assertion below.
    """
    import queue as _q
    started = []
    monkeypatch.setattr(attribution, "_queue", _q.Queue(maxsize=attribution.QUEUE_MAX))
    monkeypatch.setattr(attribution, "_ensure_writer", lambda: started.append(True))

    assert attribution.record_usage([_shard(16, 1.0)]) == 1
    # BEFORE any drain: the row is parked on the queue and is NOT yet on disk.
    assert attribution._queue.qsize() == 1
    attribution.invalidate_cache()
    assert attribution.credit_for(16, 1) is None
    assert started == [True]  # the write was handed off, not performed inline

    # Now let the write actually happen: the same row becomes durable.
    row = attribution._queue.get_nowait()
    attribution._drain([row])
    attribution._queue.task_done()  # keep flush() in the fixture teardown instant
    attribution.invalidate_cache()
    assert attribution.credit_for(16, 1) is not None


def test_queue_overflow_drops_instead_of_blocking(store, monkeypatch):
    import queue as _q
    full = _q.Queue(maxsize=1)
    full.put(("x",))
    monkeypatch.setattr(attribution, "_queue", full)
    before = attribution.dropped_count()
    assert attribution.record_usage([(20, 1), (21, 1), (22, 1)]) == 0
    assert attribution.dropped_count() > before


def test_missing_table_reports_no_evidence(tmp_path, monkeypatch):
    """A store with no attribution table yet is 'no evidence', not an error."""
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    attribution.invalidate_cache()
    assert attribution.credit_for(1, 1) is None


# --------------------------------------------------------------------------
# Wiring into the existing mark_utility path
# --------------------------------------------------------------------------

def test_mark_utility_emits_an_attribution_observation(store, monkeypatch):
    """mark_utility is the one existing call where a caller states on the record
    that a specific shard mattered, so it doubles as attribution."""
    recorded = []
    monkeypatch.setattr(attribution, "record_usage",
                        lambda used, **kw: recorded.append((list(used), kw)) or len(used))
    assert core.capture("DOCTRINE", "attribution_probe.md",
                        "probe body for attribution wiring") is True
    # capture() routes by content hash across the 9-DB grid, so find the shard
    # rather than assuming index 1.
    found = None
    for idx in range(1, core.MAX_DB_COUNT + 1):
        if not core.get_db_path(idx).exists():
            continue
        conn = core.get_connection(idx)
        try:
            row = conn.execute("SELECT id FROM shards WHERE title = ?",
                               ("attribution_probe.md",)).fetchone()
        finally:
            conn.close()
        if row:
            found = (row["id"], idx)
            break
    assert found is not None
    assert core.mark_shard(found[0], worked=True, db_index=found[1]) is True
    assert recorded, "mark_utility must record an attribution observation"
    assert recorded[0][1]["source"] == attribution.SOURCE_MARK_UTILITY


# --------------------------------------------------------------------------
# BEFORE / AFTER: observed attribution replaces the inflated prior
# --------------------------------------------------------------------------

def _rank_pair(monkeypatch):
    """Two shards tied on RRF consensus (rank 1 in their own lane).

    `inflated` carries the bulk-ingest prior (4.286875) and has NEVER been used.
    `used` carries an ordinary prior (0.9) but was explicitly declared as used.
    Provenance is neutralised so this test isolates FIX 2.
    """
    monkeypatch.setattr(provenance, "ENABLED", False)
    inflated = _shard(31, 4.286875, title="inflated_never_used.md")
    used = _shard(32, 0.9, db_index=2, title="actually_used.md")
    fused = core.reciprocal_rank_fusion([[inflated], [used]], k=60)
    return [f["id"] for f in fused]


def test_before_inflated_prior_beats_the_shard_that_was_actually_used(store, monkeypatch):
    """BEFORE: tiebreak off — the never-used shard wins purely on its prior."""
    monkeypatch.setattr(attribution, "TIEBREAK_ENABLED", False)
    attribution.record_usage([_shard(32, 0.9, db_index=2)], contribution=1.0)
    attribution.flush()
    attribution.invalidate_cache()
    assert _rank_pair(monkeypatch)[0] == 31, "expected the inflated prior to win"


def test_after_observed_attribution_reverses_the_ranking(store, monkeypatch):
    """AFTER: tiebreak on — real observed contribution outranks a prior that was
    never earned. The inflated shard has no attribution record, so it keeps its
    stored prior; the used shard's prior is replaced by observed credit."""
    monkeypatch.setattr(attribution, "TIEBREAK_ENABLED", True)
    monkeypatch.setattr(attribution, "CREDIT_WEIGHT", 10.0)
    attribution.record_usage([_shard(32, 0.9, db_index=2)], contribution=1.0)
    attribution.flush()
    attribution.invalidate_cache()
    assert _rank_pair(monkeypatch)[0] == 32, "observed usage should now lead"


def test_negative_contribution_floors_the_prior(store, monkeypatch):
    monkeypatch.setattr(attribution, "TIEBREAK_ENABLED", True)
    attribution.record_usage([_shard(41, 3.0)], contribution=-1.0)
    attribution.flush()
    attribution.invalidate_cache()
    assert attribution.observed_prior(_shard(41, 3.0), 3.0) == attribution.FLOOR_PRIOR


def test_min_observations_gate_holds_back_thin_evidence(store, monkeypatch):
    monkeypatch.setattr(attribution, "TIEBREAK_ENABLED", True)
    monkeypatch.setattr(attribution, "MIN_OBSERVATIONS", 5)
    attribution.record_usage([_shard(42, 2.0)])
    attribution.flush()
    attribution.invalidate_cache()
    assert attribution.observed_prior(_shard(42, 2.0), 2.0) == 2.0


def test_observed_prior_annotates_the_item_for_transparency(store, monkeypatch):
    monkeypatch.setattr(attribution, "TIEBREAK_ENABLED", True)
    attribution.record_usage([_shard(43, 1.0)])
    attribution.flush()
    attribution.invalidate_cache()
    item = _shard(43, 1.0)
    attribution.observed_prior(item, 1.0)
    assert item["_attribution_observations"] == 1
    assert item["_attribution_credit"] > 0


# --------------------------------------------------------------------------
# Rule 0.2 / honesty of the diagnostics
# --------------------------------------------------------------------------

def test_describe_states_the_rl_half_is_not_implemented():
    desc = attribution.describe()
    assert "not implemented" in str(desc["rl_half"])
    assert "GPU-bound" in str(desc["rl_half"])
    # The shipped default, not "any bool": the tiebreak is off until switched on.
    assert desc["tiebreak_enabled"] is False
    assert desc["tiebreak_enabled"] is attribution.TIEBREAK_ENABLED


def test_bad_env_values_fall_back_without_crashing(monkeypatch):
    monkeypatch.setenv("NOUGEN_ATTRIBUTION_HALFLIFE_DAYS", "not-a-number")
    assert attribution._env_float("NOUGEN_ATTRIBUTION_HALFLIFE_DAYS", 30.0) == 30.0
    monkeypatch.setenv("NOUGEN_ATTRIBUTION_QUEUE_MAX", "")
    assert attribution._env_int("NOUGEN_ATTRIBUTION_QUEUE_MAX", 1000) == 1000

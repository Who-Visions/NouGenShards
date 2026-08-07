"""Cue-anchored trigger delivery — synthetic fixtures, one per trigger type.

Every type must prove three things: it FIRES on a genuine match, it stays
SILENT otherwise, and it never drags along shards that declared no triggers.
Plus the budget cap must actually truncate, because an unbounded injector
recreates the held-context cost this whole lane exists to remove.
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nougen_shards import core as shards
from nougen_shards import triggers


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Isolated vault + isolated trigger sidecar. Mirrors tests/test_shards.py."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)

        def mock_get_db_path(index):
            return temp_path / f"test_shards_{index}.db"

        monkeypatch.setattr(shards, "get_db_path", mock_get_db_path)
        # Trigger store follows the vault; clear the per-path init cache so the
        # sidecar is genuinely recreated per test.
        monkeypatch.delenv("NOUGEN_VAULT_DIR", raising=False)
        monkeypatch.delenv("NOUGEN_TRIGGERS_DB", raising=False)
        monkeypatch.setenv("NOUGEN_TRIGGERS_DB", str(temp_path / "triggers.db"))
        monkeypatch.setenv("NOUGEN_TRIGGER_LOG", str(temp_path / "inject.jsonl"))
        triggers._INITIALIZED.clear()
        shards.init_db(1)
        yield temp_path
        triggers._INITIALIZED.clear()


def _mk_shard(title, content, ts=None):
    """Create a real shard row and return its stable hash: ref."""
    assert shards.capture("TEST", title, content) is True
    fhash = shards.compute_dedup_hash(content)
    if ts is not None:
        idx = shards.get_routing_index(fhash)
        conn = shards.get_connection(idx)
        try:
            conn.execute("UPDATE shards SET timestamp = ? WHERE file_hash = ?",
                         (ts, fhash))
            conn.commit()
        finally:
            conn.close()
    return f"hash:{fhash}"


def _refs(matches):
    return [m.shard_ref for m in matches]


# ---------------------------------------------------------------------------
# path
# ---------------------------------------------------------------------------

def test_path_trigger_fires_on_touched_file():
    ref = _mk_shard("core gotcha", "init_db caches per (dir, index).")
    triggers.add_trigger(ref, "path", "src/nougen_shards/core.py")
    ctx = triggers.TriggerContext(
        event="pre_tool_use",
        paths=["D:/checkouts/repo/src/nougen_shards/core.py"])
    out = triggers.evaluate(ctx)
    assert _refs(out) == [ref]
    assert out[0].reasons == ["path:src/nougen_shards/core.py"]


def test_path_trigger_silent_on_other_file():
    ref = _mk_shard("core gotcha", "init_db caches per (dir, index).")
    triggers.add_trigger(ref, "path", "src/nougen_shards/core.py")
    ctx = triggers.TriggerContext(paths=["src/nougen_shards/graph.py"])
    assert triggers.evaluate(ctx) == []


def test_path_glob_matches_directory_wildcard():
    ref = _mk_shard("tools convention", "tools/ scripts swallow exceptions.")
    triggers.add_trigger(ref, "path", "tools/*.py")
    assert _refs(triggers.evaluate(
        triggers.TriggerContext(paths=["/repo/tools/handoff_guard.py"]))) == [ref]
    assert triggers.evaluate(
        triggers.TriggerContext(paths=["/repo/src/app.py"])) == []


# ---------------------------------------------------------------------------
# symbol
# ---------------------------------------------------------------------------

def test_symbol_trigger_fires_on_identifier():
    ref = _mk_shard("routing", "get_routing_index is a pure hash function.")
    triggers.add_trigger(ref, "symbol", "get_routing_index")
    assert _refs(triggers.evaluate(
        triggers.TriggerContext(symbols=["get_routing_index"]))) == [ref]
    assert _refs(triggers.evaluate(
        triggers.TriggerContext(text="calling get_routing_index(h) here"))) == [ref]


def test_symbol_trigger_silent_without_word_boundary():
    ref = _mk_shard("routing", "get_routing_index is a pure hash function.")
    triggers.add_trigger(ref, "symbol", "capture")
    # Each negative genuinely CONTAINS "capture" as a substring, so only a real
    # word-boundary guard can keep it silent: precision over coverage.
    for text in ("the recapture step",
                 "captured output",
                 "a capturer of state",
                 "we recaptured it yesterday",
                 "shard_capture_v2 ran"):
        assert "capture" in text, text  # the negative is a true substring case
        assert triggers.evaluate(triggers.TriggerContext(text=text)) == [], text
    # ...while the bare, boundary-delimited symbol still fires.
    for text in ("call capture() now",
                 "capture, then verify",
                 "the capture lane is up"):
        assert _refs(triggers.evaluate(
            triggers.TriggerContext(text=text))) == [ref], text


# ---------------------------------------------------------------------------
# semantic
# ---------------------------------------------------------------------------

def test_semantic_trigger_requires_all_terms():
    ref = _mk_shard("wal note", "WAL mode is skipped in readonly vaults.")
    triggers.add_trigger(ref, "semantic", "sqlite,readonly")
    assert _refs(triggers.evaluate(
        triggers.TriggerContext(text="Why is SQLite ReadOnly here?"))) == [ref]
    # One term present is not a match — AND, not OR.
    assert triggers.evaluate(triggers.TriggerContext(text="sqlite is fine")) == []


# ---------------------------------------------------------------------------
# event
# ---------------------------------------------------------------------------

def test_event_trigger_fires_on_named_moment():
    ref = _mk_shard("doctrine", "Always read the handoff before planning.")
    triggers.add_trigger(ref, "event", "session_start,pre_commit")
    assert _refs(triggers.evaluate(
        triggers.TriggerContext(event="session_start"))) == [ref]
    assert _refs(triggers.evaluate(
        triggers.TriggerContext(event="PRE_COMMIT"))) == [ref]
    assert triggers.evaluate(triggers.TriggerContext(event="session_end")) == []
    assert triggers.evaluate(triggers.TriggerContext()) == []


# ---------------------------------------------------------------------------
# temporal
# ---------------------------------------------------------------------------

def _iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)) \
        .isoformat().replace("+00:00", "Z")


def test_temporal_trigger_alone_fires_inside_window():
    ref = _mk_shard("fresh incident", "Today's outage details.", ts=_iso(1))
    triggers.add_trigger(ref, "temporal", "age<=7d")
    assert _refs(triggers.evaluate(triggers.TriggerContext(event="session_start"))) == [ref]


def test_temporal_trigger_alone_silent_outside_window():
    ref = _mk_shard("old incident", "An outage from last quarter.", ts=_iso(60))
    triggers.add_trigger(ref, "temporal", "age<=7d")
    assert triggers.evaluate(triggers.TriggerContext(event="session_start")) == []


def test_temporal_gates_a_matching_cue():
    """A stale shard must not be delivered even when its path cue hits."""
    ref = _mk_shard("stale core note", "Old advice about core.py.", ts=_iso(90))
    triggers.add_trigger(ref, "path", "core.py")
    triggers.add_trigger(ref, "temporal", "age<=7d")
    assert triggers.evaluate(triggers.TriggerContext(paths=["src/core.py"])) == []
    # Same shard, gate widened -> now it delivers.
    triggers.add_trigger(ref, "temporal", "age<=365d")
    out = triggers.evaluate(triggers.TriggerContext(paths=["src/core.py"]))
    assert _refs(out) == [ref]
    assert any(r.startswith("temporal:") for r in out[0].reasons)


def test_malformed_temporal_pattern_rejected_at_author_time():
    ref = _mk_shard("x", "y")
    with pytest.raises(triggers.TriggerError):
        triggers.add_trigger(ref, "temporal", "recently")
    with pytest.raises(triggers.TriggerError):
        triggers.add_trigger(ref, "nonsense", "whatever")


# ---------------------------------------------------------------------------
# Untriggered shards must be completely unaffected
# ---------------------------------------------------------------------------

def test_shard_without_triggers_is_never_injected():
    plain = _mk_shard("plain shard", "No triggers attached to this one at all.")
    cued = _mk_shard("cued shard", "This one has a cue.")
    triggers.add_trigger(cued, "event", "session_start")
    out = triggers.evaluate(triggers.TriggerContext(
        event="session_start", paths=["plain shard"], text="plain shard"))
    assert _refs(out) == [cued]
    assert plain not in _refs(out)


def test_empty_trigger_table_is_a_total_noop():
    _mk_shard("plain", "Nothing declared.")
    ctx = triggers.TriggerContext(event="session_start", paths=["a/b.py"], text="anything")
    assert triggers.evaluate(ctx) == []
    assert triggers.render(ctx) == ""
    assert triggers.deliver("session_start", paths=["a/b.py"]) == ""


def test_master_switch_off_suppresses_everything(monkeypatch):
    ref = _mk_shard("doctrine", "Always read the handoff.")
    triggers.add_trigger(ref, "event", "session_start")
    monkeypatch.setenv("NOUGEN_TRIGGERS_ENABLED", "0")
    assert triggers.evaluate(triggers.TriggerContext(event="session_start")) == []
    assert triggers.deliver("session_start") == ""


# ---------------------------------------------------------------------------
# Ranking + budget
# ---------------------------------------------------------------------------

def test_ranking_prefers_precise_cues_and_composition():
    weak = _mk_shard("weak", "semantic only match here")
    strong = _mk_shard("strong", "path and symbol both match here")
    triggers.add_trigger(weak, "semantic", "alpha")
    triggers.add_trigger(strong, "path", "a/b.py")
    triggers.add_trigger(strong, "symbol", "widget_name")
    out = triggers.evaluate(triggers.TriggerContext(
        paths=["a/b.py"], symbols=["widget_name"], text="alpha"))
    assert _refs(out) == [strong, weak]
    assert out[0].score > out[1].score


def test_max_shards_cap_truncates(monkeypatch):
    refs = []
    for i in range(5):
        r = _mk_shard(f"shard {i}", f"body number {i}")
        triggers.add_trigger(r, "event", "session_start")
        refs.append(r)
    monkeypatch.setenv("NOUGEN_TRIGGER_MAX_SHARDS", "2")
    ctx = triggers.TriggerContext(event="session_start")
    sel = triggers.select(ctx)
    assert sel.candidates == 5
    assert len(sel.injected) == 2
    assert sel.truncated is True


def test_token_budget_cap_truncates(monkeypatch):
    for i in range(4):
        r = _mk_shard(f"big shard {i}", f"body{i} " + "x " * 800)
        triggers.add_trigger(r, "event", "session_start")
    monkeypatch.setenv("NOUGEN_TRIGGER_MAX_SHARDS", "10")
    monkeypatch.setenv("NOUGEN_TRIGGER_BUDGET_TOKENS", "60")
    ctx = triggers.TriggerContext(event="session_start")
    sel = triggers.select(ctx)
    assert sel.candidates == 4
    assert sel.tokens <= 60
    assert sel.truncated is True
    assert len(triggers.render(ctx, sel)) <= 60 * triggers.chars_per_token() + len(triggers.HEADER) + 8


def test_zero_budget_injects_nothing(monkeypatch):
    r = _mk_shard("s", "b")
    triggers.add_trigger(r, "event", "session_start")
    monkeypatch.setenv("NOUGEN_TRIGGER_BUDGET_TOKENS", "0")
    ctx = triggers.TriggerContext(event="session_start")
    assert triggers.select(ctx).injected == []
    assert triggers.render(ctx) == ""


def test_deliver_renders_and_logs(setup_test_env):
    ref = _mk_shard("handoff doctrine", "Read the latest handoff before planning.")
    triggers.add_trigger(ref, "event", "session_start")
    text = triggers.deliver("session_start")
    assert triggers.HEADER in text
    assert "handoff doctrine" in text
    assert "cue: event:session_start" in text
    logged = (setup_test_env / "inject.jsonl").read_text(encoding="utf-8").strip()
    assert '"event": "session_start"' in logged
    assert ref in logged


def test_evaluate_orders_ties_by_a_stable_total_key():
    """Ordering must come from a total sort key, never from dict iteration.

    Renamed from `test_evaluate_is_deterministic`, which only compared
    evaluate() to itself inside one process — that passes even when the order
    is inherited from `by_ref` insertion order. Here all shards score
    identically and share a timestamp, so the shard_ref tiebreak is the ONLY
    discriminator left, and the expected order is computed INDEPENDENTLY
    (sorted refs) instead of from a second call. Because refs are
    content-derived and the key is a total order, this is also what makes the
    order stable across processes; a genuine cross-process check would need a
    subprocess matrix over PYTHONHASHSEED and is not attempted here.
    """
    fixed_ts = "2026-07-24T12:00:00Z"
    # Insert in EXACTLY reverse-stable order, so insertion order is the opposite
    # of the expected output. A fixture that cannot pass by coincidence.
    contents = sorted((f"body {i}" for i in range(6)),
                      key=shards.compute_dedup_hash, reverse=True)
    refs = []
    for i, content in enumerate(contents):
        r = _mk_shard(f"s{i}", content, ts=fixed_ts)
        triggers.add_trigger(r, "event", "session_start")
        refs.append(r)
    ctx = triggers.TriggerContext(event="session_start")

    out = triggers.evaluate(ctx)
    assert len(out) == len(refs)
    # Scores and timestamps are all tied: the tiebreak is what is under test.
    assert len({m.score for m in out}) == 1
    assert len({m.timestamp for m in out}) == 1
    # Non-vacuous fixture: insertion order is the reverse of the stable order.
    assert refs == sorted(refs, reverse=True)
    assert _refs(out) == sorted(refs)
    # ...and it is reproducible within the process.
    assert _refs(triggers.evaluate(ctx)) == sorted(refs)


# ---------------------------------------------------------------------------
# Store semantics
# ---------------------------------------------------------------------------

def test_add_trigger_is_idempotent():
    ref = _mk_shard("s", "b")
    a = triggers.add_trigger(ref, "event", "session_start")
    b = triggers.add_trigger(ref, "event", "session_start")
    assert a == b
    assert len(triggers.list_triggers(ref)) == 1


def test_remove_trigger():
    ref = _mk_shard("s", "b")
    tid = triggers.add_trigger(ref, "path", "a/b.py")
    assert triggers.remove_trigger(tid) is True
    assert triggers.list_triggers(ref) == []
    assert triggers.remove_trigger(tid) is False


def test_unresolvable_ref_is_skipped_silently():
    triggers.add_trigger("hash:deadbeefnotreal", "event", "session_start")
    assert triggers.evaluate(triggers.TriggerContext(event="session_start")) == []


def test_file_ref_resolves_from_vault(setup_test_env):
    (setup_test_env / "note.md").write_text("# Vault note\nsome body", encoding="utf-8")
    triggers.add_trigger("file:note.md", "event", "session_start")
    out = triggers.evaluate(triggers.TriggerContext(event="session_start"))
    assert _refs(out) == ["file:note.md"]
    assert "Vault note" in out[0].content


# ---------------------------------------------------------------------------
# Auto-derivation (conservative by design)
# ---------------------------------------------------------------------------

def test_derive_requires_the_file_to_actually_exist(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "widget.py").write_text("x", encoding="utf-8")
    got = triggers.derive_triggers(
        "note", "Fixed a bug in src/widget.py and also src/imaginary.py",
        repo_root=str(tmp_path))
    assert ("path", "src/widget.py") in got
    assert ("path", "src/imaginary.py") not in got


def test_derive_gives_up_on_survey_shards(tmp_path, monkeypatch):
    for name in ("a.py", "b.py", "c.py", "d.py"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    monkeypatch.setenv("NOUGEN_TRIGGER_AUTODERIVE_MAX", "2")
    got = triggers.derive_triggers("roundup", "touched a.py b.py c.py d.py",
                                   repo_root=str(tmp_path))
    assert [t for t in got if t[0] == "path"] == []


def test_derive_symbols_only_from_definitions(tmp_path):
    got = triggers.derive_triggers(
        "note", "we changed def compute_routing_key(x): and mentioned self a lot",
        repo_root=str(tmp_path))
    assert ("symbol", "compute_routing_key") in got
    assert not any(t[0] == "symbol" and t[1] == "self" for t in got)


def test_derive_never_proposes_semantic_triggers(tmp_path):
    got = triggers.derive_triggers("perf", "this shard is about caching and latency",
                                   repo_root=str(tmp_path))
    assert all(t[0] != "semantic" for t in got)


def test_capture_autoderive_is_off_by_default(monkeypatch):
    monkeypatch.delenv("NOUGEN_TRIGGERS_AUTODERIVE", raising=False)
    assert triggers.autoderive_enabled() is False
    shards.capture("TEST", "note", "changed src/nougen_shards/core.py today")
    assert triggers.count_triggers() == 0


def test_capture_autoderive_attaches_when_enabled(monkeypatch, tmp_path):
    (tmp_path / "widget.py").write_text("x", encoding="utf-8")
    monkeypatch.setenv("NOUGEN_TRIGGERS_AUTODERIVE", "1")
    monkeypatch.setenv("NOUGEN_REPO", str(tmp_path))
    content = "fixed the bug in widget.py"
    shards.capture("TEST", "note", content)
    rows = triggers.list_triggers(f"hash:{shards.compute_dedup_hash(content)}")
    assert [(r["trigger_type"], r["pattern"], r["source"]) for r in rows] == \
        [("path", "widget.py", "auto")]


def test_capture_still_succeeds_when_trigger_lane_explodes(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("trigger lane down")
    monkeypatch.setattr(triggers, "on_capture", boom)
    assert shards.capture("TEST", "resilient", "capture must not fail") is True

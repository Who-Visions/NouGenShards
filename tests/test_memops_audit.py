"""Unit tests for the MemOps memory-health audit harness.

Every fixture is SYNTHETIC -- no test depends on live vault content. Each
detector is proven twice: it FIRES on a dirty fixture and stays SILENT on the
matching clean fixture.
"""
import dataclasses
import sqlite3
import sys
from pathlib import Path

import pytest

from nougen_shards import memops_audit as ma


# ---------------------------------------------------------------------------
# Hermetic environment: no live vault, no ollama, no inherited knobs.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for key in list(dict(**{k: v for k, v in __import__("os").environ.items()})):
        if key.startswith("NOUGEN_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path))
    monkeypatch.setenv("NOUGEN_AUDIT_LLM_ENABLED", "0")   # never touch the fleet in tests
    monkeypatch.setenv("NOUGEN_AUDIT_OUT_DIR", str(tmp_path / "audit-runs"))
    return tmp_path


@pytest.fixture
def cfg():
    return ma.AuditConfig.resolve()


def shard(sid, title, content, ts="2026-07-01T00:00:00+00:00", store="primary",
          db="nougen_shards_1.db", event_type="finding", tags="", fhash="", domain="global"):
    return ma.Shard(store=store, db=db, id=sid, timestamp=ts, event_type=event_type,
                    title=title, content=content, tags=tags, utility_score=0.5,
                    file_hash=fhash, domain_key=domain)


# ---------------------------------------------------------------------------
# Config / Rule 0.2
# ---------------------------------------------------------------------------


def test_config_resolves_from_env_and_records_provenance(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_AUDIT_ARXIV_SAMPLE", "7")
    monkeypatch.setenv("NOUGEN_AUDIT_NEAR_DUP_THRESHOLD", "0.42")
    monkeypatch.setenv("NOUGEN_AUDIT_BINDING_KINDS", "ipv4, port")
    c = ma.AuditConfig.resolve()
    assert c.vault_dir == tmp_path
    assert c.resolved_from["vault_dir"] == "env:NOUGEN_VAULT_DIR"
    assert c.arxiv_sample == 7
    assert c.near_dup_threshold == pytest.approx(0.42)
    assert c.binding_kinds == ["ipv4", "port"]


def test_config_falls_back_when_env_is_junk(monkeypatch):
    monkeypatch.setenv("NOUGEN_AUDIT_ARXIV_SAMPLE", "not-a-number")
    c = ma.AuditConfig.resolve()
    assert c.arxiv_sample == 150  # logged fallback, not a crash


def test_config_argument_beats_env(tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    c = ma.AuditConfig.resolve(str(other))
    assert c.vault_dir == other
    assert c.resolved_from["vault_dir"] == "argument"


# ---------------------------------------------------------------------------
# Read-only guarantee
# ---------------------------------------------------------------------------


def _make_db(path, rows):
    conn = sqlite3.connect(str(path))
    conn.execute("""CREATE TABLE shards (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, event_type TEXT,
        title TEXT, content TEXT, tags TEXT, utility_score REAL, access_count INTEGER,
        file_hash TEXT, domain_key TEXT, embedding BLOB, density_score REAL,
        consolidated INTEGER, schema_version INTEGER)""")
    conn.executemany(
        "INSERT INTO shards (timestamp, event_type, title, content, tags, utility_score,"
        " file_hash, domain_key) VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def test_open_readonly_rejects_writes(tmp_path):
    db = tmp_path / "nougen_shards_1.db"
    _make_db(db, [("2026-07-01", "finding", "t", "c", "", 0.5, "h1", "global")])
    conn = ma.open_readonly(db)
    assert conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0] == 1
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM shards")
    conn.close()


def test_load_shards_caps_arxiv_backlog(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_AUDIT_ARXIV_SAMPLE", "2")
    rows = [("2026-07-01", "research", f"arxiv_cs_AI_paper_{i}", "abstract", "", 0.5,
             f"h{i}", "global") for i in range(10)]
    rows += [("2026-07-01", "finding", "real ops finding", "body", "", 0.5, "hx", "global")]
    _make_db(tmp_path / "nougen_shards_1.db", rows)
    c = ma.AuditConfig.resolve()
    loaded = ma.load_shards("primary", tmp_path, c)
    arxiv = [s for s in loaded if s.title.startswith("arxiv_")]
    assert len(arxiv) == 2                      # backlog sampled, not mass-processed
    assert any(s.title == "real ops finding" for s in loaded)


def test_discover_dbs_probes_filesystem(tmp_path, cfg):
    assert ma.discover_dbs(tmp_path, cfg) == []
    _make_db(tmp_path / "nougen_shards_3.db", [])
    assert [p.name for p in ma.discover_dbs(tmp_path, cfg)] == ["nougen_shards_3.db"]


# ---------------------------------------------------------------------------
# Detector 1 -- stale value
# ---------------------------------------------------------------------------


def test_stale_value_fires_on_revised_numeric_total(cfg):
    dirty = [
        shard(1, "claim reconciliation rev.1",
              "Total claim amount 5321 dollars across the batch.",
              ts="2026-07-01T00:00:00+00:00"),
        shard(2, "claim reconciliation rev.2",
              "Total claim amount 6120 dollars across the batch.",
              ts="2026-07-10T00:00:00+00:00"),
    ]
    found = ma.detect_stale_values(dirty, cfg)
    assert found, "numeric revision must be flagged as a stale value"
    f = found[0]
    assert f.failure_class == "stale_value" and f.subclass == "numeric"
    assert f.detail["older_value"] == "5321" and f.detail["newer_value"] == "6120"
    assert set(f.refs) == {"primary:nougen_shards_1.db#1", "primary:nougen_shards_1.db#2"}


def test_stale_value_fires_on_status_flip(cfg):
    dirty = [
        shard(1, "recall lane status", "The recall lane migration is broken.",
              ts="2026-07-01T00:00:00+00:00"),
        shard(2, "recall lane status", "The recall lane migration is fixed.",
              ts="2026-07-09T00:00:00+00:00"),
    ]
    found = [f for f in ma.detect_stale_values(dirty, cfg) if f.subclass == "status"]
    assert found
    assert {found[0].detail["older_value"], found[0].detail["newer_value"]} == {
        "negative", "positive"}


def test_stale_value_silent_on_clean_fixture(cfg):
    clean = [
        shard(1, "claim reconciliation", "Total claim amount 5321 dollars.",
              ts="2026-07-01T00:00:00+00:00"),
        shard(2, "claim reconciliation", "Total claim amount 5321 dollars.",
              ts="2026-07-10T00:00:00+00:00"),
        shard(3, "unrelated topic", "Shutter latency measured 41 milliseconds.",
              ts="2026-07-11T00:00:00+00:00"),
    ]
    assert ma.detect_stale_values(clean, cfg) == []


def test_stale_value_silent_when_supersession_is_recorded(cfg):
    """A recorded lifecycle 'update' is correct behaviour, not a failure."""
    marked = [
        shard(1, "claim reconciliation superseded",
              "Total claim amount 5321 dollars.", ts="2026-07-01T00:00:00+00:00",
              tags="superseded"),
        shard(2, "claim reconciliation current",
              "Total claim amount 6120 dollars.", ts="2026-07-10T00:00:00+00:00"),
    ]
    assert [f for f in ma.detect_stale_values(marked, cfg) if f.subclass == "numeric"] == []


def test_stale_value_ignores_path_and_version_numbers(cfg):
    """Regression: live-vault FP where release paths read as contradicted values."""
    noise = [
        shard(1, "ecc release evidence note",
              r"Evidence stored under docs\releases\1.8.0\quote-eval.md today.",
              ts="2026-07-01T00:00:00+00:00"),
        shard(2, "ecc release evidence note",
              r"Evidence stored under docs\releases\2.0.0\quote-eval.md today.",
              ts="2026-07-10T00:00:00+00:00"),
    ]
    assert [f for f in ma.detect_stale_values(noise, cfg) if f.subclass == "numeric"] == []


def test_stale_value_ignores_structural_label_keys(cfg):
    """'source_row 338' vs 'source_row 394' enumerates records, it does not assert."""
    noise = [
        shard(1, "vault migration record", "Migrated source_row 338 into shards.",
              ts="2026-07-01T00:00:00+00:00"),
        shard(2, "vault migration record", "Migrated source_row 394 into shards.",
              ts="2026-07-10T00:00:00+00:00"),
    ]
    assert [f for f in ma.detect_stale_values(noise, cfg) if f.subclass == "numeric"] == []


def test_stale_value_requires_topical_overlap(cfg):
    """Same metric label in unrelated documents is a coincidence, not a stale value."""
    unrelated = [
        shard(1, "power up plan", "Estimated completion time 2 weeks.",
              ts="2026-07-01T00:00:00+00:00"),
        shard(2, "api security audit", "Estimated completion time 4 weeks.",
              ts="2026-07-10T00:00:00+00:00"),
    ]
    assert ma.detect_stale_values(unrelated, cfg) == []
    # ...but the same pair under one topic still fires.
    related = [
        shard(1, "power up plan", "Estimated completion time 2 weeks.",
              ts="2026-07-01T00:00:00+00:00"),
        shard(2, "power up plan", "Estimated completion time 4 weeks.",
              ts="2026-07-10T00:00:00+00:00"),
    ]
    assert [f for f in ma.detect_stale_values(related, cfg) if f.subclass == "numeric"]


def test_stale_value_silent_without_time_ordering(cfg):
    same_time = [
        shard(1, "claim reconciliation", "Total claim amount 5321 dollars."),
        shard(2, "claim reconciliation", "Total claim amount 6120 dollars."),
    ]
    assert ma.detect_stale_values(same_time, cfg) == []


# ---------------------------------------------------------------------------
# Detector 2 -- wrong binding
# ---------------------------------------------------------------------------


def test_wrong_binding_fires_on_identifier_bound_to_two_entities(cfg):
    dirty = [
        shard(1, "node inventory", "Mercury Station reachable at 10.0.0.136 today."),
        shard(2, "node inventory two", "Stadium answers on 10.0.0.136 as well."),
    ]
    found = [f for f in ma.detect_wrong_bindings(dirty, cfg)
             if f.subclass == "identifier_ipv4"]
    assert found
    assert found[0].detail["identifier"] == "10.0.0.136"
    assert len(found[0].detail["owners"]) >= 2


def test_wrong_binding_silent_when_identifier_has_one_owner(cfg):
    clean = [
        shard(1, "node inventory", "Mercury Station reachable at 10.0.0.136 today."),
        shard(2, "node inventory two", "Mercury Station answers on 10.0.0.136 as well."),
    ]
    assert [f for f in ma.detect_wrong_bindings(clean, cfg)
            if f.failure_class == "wrong_binding"] == []


def test_wrong_binding_fires_on_date_drift(cfg):
    dirty = [shard(1, "ingest incident report",
                   "The incident occurred on 2026-01-05 and was contained.",
                   ts="2026-07-24T10:00:00+00:00", event_type="finding")]
    found = [f for f in ma.detect_wrong_bindings(dirty, cfg) if f.subclass == "date_drift"]
    assert found and found[0].detail["min_delta_days"] > cfg.date_tolerance_days


def test_wrong_binding_silent_on_dates_within_tolerance(cfg):
    clean = [shard(1, "ingest incident report",
                   "The incident occurred on 2026-07-23 and was contained.",
                   ts="2026-07-24T10:00:00+00:00", event_type="finding")]
    assert [f for f in ma.detect_wrong_bindings(clean, cfg) if f.subclass == "date_drift"] == []


def test_wrong_binding_exempts_research_shards_from_date_drift(cfg):
    """arXiv shards legitimately carry a foreign publication date."""
    papers = [shard(1, "arxiv_cs_AI_20260714_MemOps_Benchmarking",
                    "Published: 2026-07-14 abstract text.",
                    ts="2026-07-24T10:00:00+00:00", event_type="research")]
    assert [f for f in ma.detect_wrong_bindings(papers, cfg) if f.subclass == "date_drift"] == []


def test_wrong_binding_fires_on_cross_store_attribution(cfg):
    dirty = [
        shard(1, "handoff registry rebuild", "body one", store="vault", domain="ops"),
        shard(2, "handoff registry rebuild", "body two", store="pull-clone",
              domain="transcripts"),
    ]
    found = [f for f in ma.detect_wrong_bindings(dirty, cfg)
             if f.subclass == "cross_store_attribution"]
    assert found and sorted(found[0].detail["stores"]) == ["pull-clone", "vault"]


def test_wrong_binding_silent_when_stores_agree_on_domain(cfg):
    clean = [
        shard(1, "handoff registry rebuild", "body one", store="vault", domain="ops"),
        shard(2, "handoff registry rebuild", "body two", store="pull-clone", domain="ops"),
    ]
    assert [f for f in ma.detect_wrong_bindings(clean, cfg)
            if f.subclass == "cross_store_attribution"] == []


# ---------------------------------------------------------------------------
# Detector 3 -- retrieval blind spots
# ---------------------------------------------------------------------------


def test_blind_spot_fires_when_known_answer_query_misses(cfg):
    shards = [shard(1, "dead whole brain fallback in domain scoped retrieval", "body text")]
    found = ma.detect_retrieval_blind_spots(shards, cfg, retriever=lambda q, k: [])
    assert found and found[0].subclass == "unretrievable_shard"
    assert found[0].severity == "high"


def test_blind_spot_silent_when_shard_is_returned(cfg):
    s = shard(1, "dead whole brain fallback in domain scoped retrieval", "body text")
    hit = [{"id": 1, "title": s.title}]
    assert ma.detect_retrieval_blind_spots([s], cfg, retriever=lambda q, k: hit) == []


def test_blind_spot_matches_on_title_when_ids_are_store_local(cfg):
    """Federated hits may not carry the primary store's id; title match must save it."""
    s = shard(7, "rrf tie break utility prior", "body text")
    hit = [{"id": 999, "title": "rrf tie break utility prior"}]
    assert ma.detect_retrieval_blind_spots([s], cfg, retriever=lambda q, k: hit) == []


def test_unindexed_file_fires_and_stays_silent(tmp_path, cfg):
    (tmp_path / "orphan_ops_note.md").write_text("content", encoding="utf-8")
    (tmp_path / "known_ops_note.md").write_text("content", encoding="utf-8")
    shards = [shard(1, "known_ops_note", "content")]
    found = ma.detect_unindexed_files(shards, cfg)
    names = {Path(f.detail["path"]).name for f in found}
    assert "orphan_ops_note.md" in names       # fires on the orphan
    assert "known_ops_note.md" not in names    # silent on the indexed one


# ---------------------------------------------------------------------------
# Detector 4 -- duplicates
# ---------------------------------------------------------------------------


def _long_body(swap=None):
    words = [f"token{i}" for i in range(120)]
    if swap is not None:
        words[swap] = "divergent"
    return " ".join(words)


def test_duplicate_fires_on_exact_hash_collision(cfg):
    dirty = [
        shard(1, "handoff note", _long_body(), fhash="deadbeefdeadbeef"),
        shard(2, "handoff note", _long_body(), fhash="deadbeefdeadbeef", db="nougen_shards_2.db"),
    ]
    found = [f for f in ma.detect_duplicates(dirty, cfg) if f.subclass == "exact_hash"]
    assert found and found[0].detail["count"] == 2


def test_duplicate_fires_on_near_duplicate(cfg):
    dirty = [
        shard(1, "wargame ledger entry", _long_body(), fhash="aaa1"),
        shard(2, "wargame ledger entry", _long_body(swap=60), fhash="bbb2"),
    ]
    found = [f for f in ma.detect_duplicates(dirty, cfg) if f.subclass == "near_duplicate"]
    assert found and found[0].detail["similarity"] >= cfg.near_dup_threshold


def test_duplicate_silent_on_clean_fixture(cfg):
    clean = [
        shard(1, "wargame ledger entry", _long_body(), fhash="aaa1"),
        shard(2, "unrelated capture note",
              " ".join(f"other{i}" for i in range(120)), fhash="bbb2"),
    ]
    assert ma.detect_duplicates(clean, cfg) == []


def test_duplicate_threshold_is_configurable(monkeypatch):
    monkeypatch.setenv("NOUGEN_AUDIT_NEAR_DUP_THRESHOLD", "0.999")
    strict = ma.AuditConfig.resolve()
    pair = [
        shard(1, "wargame ledger entry", _long_body(), fhash="aaa1"),
        shard(2, "wargame ledger entry", _long_body(swap=60), fhash="bbb2"),
    ]
    assert [f for f in ma.detect_duplicates(pair, strict)
            if f.subclass == "near_duplicate"] == []


# ---------------------------------------------------------------------------
# Local-fleet adjudicator: must degrade, never escalate to cloud
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("0.0.0.0", "http://127.0.0.1:11434"),          # bind address inherited from env
    ("127.0.0.1:11434", "http://127.0.0.1:11434"),  # missing scheme
    ("http://box:9999", "http://box:9999"),         # already valid, untouched
    ("", "http://127.0.0.1:11434"),
])
def test_ollama_host_normalisation(monkeypatch, raw, expected):
    """Regression: OLLAMA_HOST=0.0.0.0 made a live fleet look unreachable."""
    monkeypatch.setenv("OLLAMA_HOST", raw)
    monkeypatch.delenv("NOUGEN_AUDIT_OLLAMA_HOST", raising=False)
    assert ma.AuditConfig.resolve().ollama_host == expected


def test_adjudicator_degrades_when_disabled(cfg):
    adj = ma.OllamaAdjudicator(cfg)
    assert adj.probe() is False
    assert adj.available is False
    findings = [ma.Finding("stale_value", "numeric", "high", "s", ["a"], ["x", "y"])]
    tally = adj.adjudicate(findings)
    assert tally["unscored"] == 1
    assert findings[0].confidence == "lexical"   # lexical verdict survives untouched


def test_adjudicator_degrades_when_host_unreachable(monkeypatch):
    """Hermetic: no real socket. The connection failure is injected, so the
    assertion can name the ONE reason this path must produce instead of
    accepting an unrelated 'no preferred model' verdict."""
    host = "http://127.0.0.1:11434"
    calls = []

    def refuse(req, *a, **k):
        calls.append(getattr(req, "full_url", req))
        raise ma.urllib.error.URLError(ConnectionRefusedError("connection refused"))

    monkeypatch.setattr(ma.urllib.request, "urlopen", refuse)
    monkeypatch.setenv("NOUGEN_AUDIT_LLM_ENABLED", "1")
    monkeypatch.setenv("NOUGEN_AUDIT_OLLAMA_HOST", host)
    c = ma.AuditConfig.resolve()
    adj = ma.OllamaAdjudicator(c)

    assert adj.probe() is False
    # The probe went through the injected failure, not the network.
    assert calls == [f"{host}/api/tags"]
    assert "unreachable" in adj.reason
    assert host in adj.reason
    # Degraded cleanly: no model selected, adjudication stays lexical.
    assert adj.available is False
    assert not adj.model


def test_adjudicator_marks_verdicts_when_model_answers(cfg, monkeypatch):
    adj = ma.OllamaAdjudicator(cfg)
    adj.available, adj.model = True, "gemma4:12b"
    monkeypatch.setattr(adj, "_chat", lambda prompt: "1: CONTRADICTS\n2: UNRELATED")
    findings = [
        ma.Finding("stale_value", "numeric", "high", "a", ["r1"], ["old", "new"]),
        ma.Finding("stale_value", "numeric", "high", "b", ["r2"], ["old", "new"]),
    ]
    tally = adj.adjudicate(findings)
    assert tally["confirmed"] == 1 and tally["rejected"] == 1
    assert findings[0].confidence == "llm-confirmed"
    assert findings[1].confidence == "llm-rejected" and findings[1].severity == "low"


def test_adjudicator_keeps_lexical_verdict_on_unparsable_reply(cfg, monkeypatch):
    adj = ma.OllamaAdjudicator(cfg)
    adj.available, adj.model = True, "gemma4:12b"
    monkeypatch.setattr(adj, "_chat", lambda prompt: "I think maybe the first one?")
    findings = [ma.Finding("stale_value", "numeric", "high", "a", ["r1"], ["old", "new"])]
    tally = adj.adjudicate(findings)
    assert tally["unscored"] == 1 and findings[0].confidence == "lexical"


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------


def test_run_audit_end_to_end_is_deterministic(cfg, tmp_path):
    shards = [
        shard(1, "claim reconciliation", "Total claim amount 5321 dollars.",
              ts="2026-07-01T00:00:00+00:00", fhash="h1"),
        shard(2, "claim reconciliation", "Total claim amount 6120 dollars.",
              ts="2026-07-10T00:00:00+00:00", fhash="h2"),
        shard(3, "handoff note", _long_body(), fhash="dup"),
        shard(4, "handoff note", _long_body(), fhash="dup", db="nougen_shards_2.db"),
    ]
    hit = lambda q, k: []  # noqa: E731 - force a blind-spot signal too
    first = ma.run_audit(cfg, shards=shards, retriever=hit)
    second = ma.run_audit(cfg, shards=shards, retriever=hit)
    assert first["counts"] == second["counts"]
    assert [f["summary"] for f in first["findings"]] == \
           [f["summary"] for f in second["findings"]]
    assert first["read_only"] is True
    assert first["counts"]["stale_value"] >= 1
    assert first["counts"]["duplicate"] >= 1
    assert first["counts"]["retrieval_blind_spot"] >= 1
    assert first["adjudicator"]["available"] is False  # llm disabled in tests


def test_run_audit_clean_corpus_reports_nothing(cfg):
    shards = [
        shard(1, "alpha capture note", "Alpha throughput measured 12 units.",
              ts="2026-07-01T00:00:00+00:00", fhash="a1"),
        shard(2, "beta capture note", "Beta latency measured 30 milliseconds.",
              ts="2026-07-02T00:00:00+00:00", fhash="b2"),
    ]
    ok = lambda q, k: [{"id": s.id, "title": s.title} for s in shards]  # noqa: E731
    result = ma.run_audit(cfg, shards=shards, retriever=ok)
    assert result["counts"] == {}, result["counts"]


def test_write_outputs_emits_report_and_json(cfg, tmp_path):
    result = ma.run_audit(cfg, shards=[], retriever=lambda q, k: [])
    md_path, json_path = ma.write_outputs(result, cfg)
    assert md_path.exists() and json_path.exists()
    assert "MemOps taxonomy" in md_path.read_text(encoding="utf-8")
    import json as _json
    assert _json.loads(json_path.read_text(encoding="utf-8"))["read_only"] is True


def test_report_renders_counts_table(cfg):
    result = ma.run_audit(cfg, shards=[
        shard(1, "claim reconciliation", "Total claim amount 5321 dollars.",
              ts="2026-07-01T00:00:00+00:00"),
        shard(2, "claim reconciliation", "Total claim amount 6120 dollars.",
              ts="2026-07-10T00:00:00+00:00"),
    ], retriever=lambda q, k: [{"id": 1, "title": "claim reconciliation"},
                               {"id": 2, "title": "claim reconciliation"}])
    text = ma.render_report(result)
    assert "## Counts per failure class" in text
    assert "stale_value" in text

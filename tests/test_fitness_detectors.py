import pytest
from nougen_shards import fitness_corpus as fc
from nougen_shards.fitness_detectors import Sources, run_cases, run_detector


def _src(**kw):
    return Sources(**kw)


def test_proc_count_recurs_above_max():
    src = _src(process_names=lambda: ["node.exe"] * 815 + ["git.exe"])
    r = run_detector({"kind": "proc_count", "name": "node.exe", "max": 150}, src)
    assert r.status == "ok" and r.recurring and r.observed["count"] == 815
    r = run_detector({"kind": "proc_count", "name": "NODE.EXE", "max": 150}, _src(process_names=lambda: ["node.exe"] * 27))
    assert not r.recurring


def test_free_commit_below_floor():
    assert run_detector({"kind": "free_commit_gb", "min": 10}, _src(free_commit_gb=lambda: 4.8)).recurring
    assert not run_detector({"kind": "free_commit_gb", "min": 10}, _src(free_commit_gb=lambda: 29.4)).recurring


def test_relay_cadence_flags_five_minute_hourly_job():
    five_min = [i * 300.0 for i in range(10)]
    hourly = [i * 3600.0 for i in range(5)]
    d = {"kind": "relay_cadence", "suffix": "-hourly-delta", "min_interval_s": 3000}
    assert run_detector(d, _src(message_times=lambda s: five_min)).recurring
    assert not run_detector(d, _src(message_times=lambda s: hourly)).recurring
    assert not run_detector(d, _src(message_times=lambda s: [])).recurring


def test_claim_requires_evidence():
    d = {"kind": "claim_requires_evidence", "pattern": "not found|no .* entry"}
    bad = ["All 19 equations operationalized.", "There is no cloudflare entry in the config."]
    good = ["Merged in #705.", "Entry is at mcp_config.json:92."]
    r = run_detector(d, _src(recent_messages=lambda: bad + good))
    assert r.recurring and r.observed["unreferenced_claims"] == 2
    assert not run_detector(d, _src(recent_messages=lambda: good)).recurring


def test_unknown_kind_is_unsupported_not_pass():
    r = run_detector({"kind": "duplicate_pr_topic"})
    assert r.status == "unsupported" and not r.recurring


def test_broken_probe_reports_error():
    def boom():
        raise OSError("no access")
    r = run_detector({"kind": "proc_count", "name": "x", "max": 1}, _src(process_names=boom))
    assert r.status == "error" and "OSError" in r.observed["error"]


def test_run_cases_over_seed_corpus(tmp_path):
    corpus = fc.FitnessCorpus(tmp_path / "c.jsonl")
    fc.seed_from(corpus, fc.SEED_2026_10_04)
    src = _src(process_names=lambda: ["node.exe"] * 20, free_commit_gb=lambda: 25.0)
    results = run_cases(list(corpus._iter_all()), src)
    assert len(results) == len(fc.SEED_2026_10_04)
    statuses = {r.kind: r.status for r in results.values()}
    assert statuses["proc_count"] == "ok" and statuses["free_commit_gb"] == "ok"
    assert statuses["duplicate_pr_topic"] == "unsupported"
    assert not any(r.recurring for r in results.values())


def test_live_probes_run():
    pytest.importorskip("psutil")  # live probes need psutil; CI images may not ship it
    r = run_detector({"kind": "proc_count", "name": "python.exe", "max": 100000})
    assert r.status == "ok"
    r = run_detector({"kind": "free_commit_gb", "min": 0})
    assert r.status == "ok" and r.observed["free_gb"] > 0

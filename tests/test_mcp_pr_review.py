import json

from nougen_shards import mcp as srv


def test_review_pr_gated_by_default(monkeypatch):
    monkeypatch.delenv("NOUGEN_ENABLE_PR_REVIEW", raising=False)
    assert "disabled by default" in srv.review_pr("Who-Visions/NouGenShards", 1)


def test_review_pr_rejects_bad_repo(monkeypatch):
    monkeypatch.setenv("NOUGEN_ENABLE_PR_REVIEW", "1")
    assert "error" in json.loads(srv.review_pr("not a repo; rm -rf", 1))


def test_pr_review_status_filters(tmp_path, monkeypatch):
    led = tmp_path / "ledger.jsonl"
    led.write_text("\n".join(json.dumps(e) for e in [
        {"repo": "a/b", "pr": 1, "verdict": "APPROVE"},
        {"repo": "a/b", "pr": 2, "verdict": "REQUEST_CHANGES"},
        "garbage-not-json"]) + "\n", encoding="utf-8")
    monkeypatch.setattr(srv, "_pr_review_ledger", lambda: led)
    out = json.loads(srv.pr_review_status(repo="a/b", pr=2))
    assert [r["verdict"] for r in out["reviews"]] == ["REQUEST_CHANGES"]
    assert len(json.loads(srv.pr_review_status())["reviews"]) == 2


def test_review_pr_refuses_dot_segments(monkeypatch):
    monkeypatch.setenv("NOUGEN_ENABLE_PR_REVIEW", "1")
    for bad in ("../x", "x/..", "./x", "x/."):
        assert "error" in json.loads(srv.review_pr(bad, 1)), bad


def test_review_pr_keeps_stderr(monkeypatch):
    import subprocess

    class R:
        returncode, stdout, stderr = 1, "partial out", "boom: token refused"
    monkeypatch.setenv("NOUGEN_ENABLE_PR_REVIEW", "1")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    out = json.loads(srv.review_pr("o/r", 1))
    assert out["log"] == "partial out" and "token refused" in out["stderr"]


def test_rsi_mutators_gated(monkeypatch):
    monkeypatch.delenv("NOUGEN_ENABLE_PR_REVIEW", raising=False)
    assert "disabled by default" in srv.rsi_evolve()
    assert "disabled by default" in srv.rsi_rollback(1)


def test_rsi_status_parses_cli_json(monkeypatch):
    monkeypatch.setattr(srv, "_run_review_ts", lambda args, timeout=900: {"exit": 0, "stdout": '{"active": 3}'})
    assert json.loads(srv.rsi_status()) == {"active": 3}
    monkeypatch.setattr(srv, "_run_review_ts", lambda args, timeout=900: {"exit": 1, "stdout": "not json"})
    assert json.loads(srv.rsi_status())["exit"] == 1


def test_rsi_rollback_validates(monkeypatch):
    monkeypatch.setenv("NOUGEN_ENABLE_PR_REVIEW", "1")
    assert "error" in json.loads(srv.rsi_rollback(0))


def test_pr_review_ledger_names_no_account(tmp_path, monkeypatch):
    monkeypatch.setattr(srv.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("NOUGEN_PR_REVIEWER", raising=False)
    assert srv._pr_review_ledger().parent.name == "reviewer"
    only = tmp_path / ".nougen" / "research" / "reviews" / "bot-a"
    only.mkdir(parents=True)
    (only / "ledger.jsonl").write_text("", encoding="utf-8")
    assert srv._pr_review_ledger() == only / "ledger.jsonl"
    monkeypatch.setenv("NOUGEN_PR_REVIEWER", "bot-b")
    assert srv._pr_review_ledger().parent.name == "bot-b"

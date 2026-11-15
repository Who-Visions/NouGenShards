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
    monkeypatch.setattr(srv, "_PR_REVIEW_LEDGER", led)
    out = json.loads(srv.pr_review_status(repo="a/b", pr=2))
    assert [r["verdict"] for r in out["reviews"]] == ["REQUEST_CHANGES"]
    assert len(json.loads(srv.pr_review_status())["reviews"]) == 2

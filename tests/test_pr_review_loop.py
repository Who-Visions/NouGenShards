"""Review-loop verdict parsing (tools/pr_reviewer/verdicts.py), fleet reverse helpers, and their MCP tools."""
import importlib.util
import json
import pathlib

import pytest

from nougen_shards import mcp as srv

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools" / "pr_reviewer"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


verdicts = _load("verdicts")
reverse = _load("reverse")

ROUND1 = "#7 — MERGE-WITH-NITS\n1. **P2** — a.py:1: x\n2. **P2** — b.py:2: y\n3. **P3** — c.py:3: z\nOverall: ok"
ROUND2 = ("#7 — MERGE-WITH-NITS\n1. **FIXED** — a.py\n2. **NOT FIXED** — b.py **P2** still\n3. **FIXED** — c.py\n"
          "1. **P3** — d.py:9: new nit\nOverall: close")
ROUND3 = "#7 — MERGE\n1. **FIXED** — b.py\n2. **FIXED** — d.py\nOverall: clean"


def test_parse_counts_fixed_not_fixed_and_open():
    r = verdicts.parse_log(ROUND2, 7)
    assert r["verdict"] == "MERGE-WITH-NITS"
    assert (r["fixed"], r["not_fixed"]) == (2, 1)
    assert r["open"] == {"P1": 0, "P2": 1, "P3": 1}


def test_verdict_is_per_pr():
    assert verdicts.parse_log("#6 — BLOCK\n#7 — MERGE", 7)["verdict"] == "MERGE"
    assert verdicts.parse_log("#6 — BLOCK", 7)["verdict"] is None


def test_loop_state_progresses_to_done(tmp_path):
    (tmp_path / "Repo-7-agy-20261115-1300.md").write_text(ROUND1, encoding="utf-8")
    s = verdicts.loop_state("o/Repo", 7, tmp_path)
    assert not s["done"] and "--prior" in s["next"]
    (tmp_path / "Repo-7-agy-20261115-1310.md").write_text(ROUND2, encoding="utf-8")
    assert not verdicts.loop_state("o/Repo", 7, tmp_path)["done"]  # NOT FIXED + open P2
    (tmp_path / "Repo-7-codex-20261115-1320.md").write_text("usage limit reached", encoding="utf-8")
    (tmp_path / "Repo-7-agy-20261115-1319.md").write_text(ROUND3, encoding="utf-8")
    s = verdicts.loop_state("o/Repo", 7, tmp_path)
    assert s["done"] and s["next"].startswith("merge")
    assert s["latest"]["stamp"] == "20261115-1319"  # verdict-less codex log does not count
    assert len(s["rounds"]) == 4


def test_loop_state_no_logs(tmp_path):
    s = verdicts.loop_state("o/Repo", 9, tmp_path)
    assert not s["done"] and s["next"].endswith("--agent both")


def test_block_is_never_done(tmp_path):
    (tmp_path / "Repo-7-agy-20261115-1300.md").write_text("#7 — BLOCK\nOverall: no", encoding="utf-8")
    assert not verdicts.loop_state("o/Repo", 7, tmp_path)["done"]


def test_reverse_chunks_and_targets():
    assert [len(c) for c in reverse.chunks("x" * 30000)] == [7000, 7000, 7000]
    assert reverse.chunks("") == []
    assert reverse.parse_target("a/b:x,y") == ("a/b", ["x", "y"])
    assert reverse.parse_target("a/b") == ("a/b", [])
    for bad in ("a", "a/b/c", "../b", "a/.."):
        with pytest.raises(ValueError):
            reverse.parse_target(bad)


def test_mcp_verdicts_validates_and_reads(monkeypatch):
    assert "error" in json.loads(srv.pr_review_verdicts("../x", 1))

    class Fake:
        @staticmethod
        def loop_state(repo, pr):
            return {"repo": repo, "pr": pr, "done": True}
    monkeypatch.setattr(srv, "_pr_tool", lambda name: Fake)
    assert json.loads(srv.pr_review_verdicts("o/r", 3)) == {"repo": "o/r", "pr": 3, "done": True}


def test_mcp_rsi_reverse_gated_and_validated(monkeypatch):
    monkeypatch.delenv("NOUGEN_ENABLE_PR_REVIEW", raising=False)
    assert "disabled by default" in srv.rsi_reverse(["a/b"])
    monkeypatch.setenv("NOUGEN_ENABLE_PR_REVIEW", "1")
    assert "error" in json.loads(srv.rsi_reverse(["../etc"]))
    assert "error" in json.loads(srv.rsi_reverse([]))

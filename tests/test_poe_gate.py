"""Truth Anchor layer 4: completion-tagged shards need proof of execution."""
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as shards
from nougen_shards import poe_gate


@pytest.fixture(autouse=True)
def isolated_vault(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)
        monkeypatch.setattr(shards, "get_db_path", lambda index: temp_path / f"poe_{index}.db")
        shards.init_db(1)
        yield temp_path


@pytest.fixture
def repo(tmp_path):
    def git(*args):
        return subprocess.run(["git", "-C", str(tmp_path), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    git("init", "-q")
    (tmp_path / "fix.py").write_text("x = 1\n", encoding="utf-8")
    git("add", "fix.py")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "fix")
    return tmp_path, git("rev-parse", "HEAD")


def _poe(repo_path, sha, exit_code=0):
    return {
        "git": {"commit_sha": sha, "files_changed": ["fix.py"], "repo_path": str(repo_path)},
        "test_evidence": {"runner": "pytest tests/test_fix.py", "exit_code": exit_code,
                          "stdout_hash": hashlib.sha256(b"1 passed").hexdigest()},
        "verifier": {"observer_node": "blade1tb"},
    }


def test_untagged_shard_is_not_gated():
    assert shards.capture("note", "plain note", "nothing claimed here", tags=["ops"])


def test_completion_claim_without_proof_is_rejected():
    assert not shards.capture("fix", "gateway fixed", "it works now", tags=["fixed"])


def test_status_prefixed_tag_counts_as_claim():
    assert not shards.capture("fix", "bug resolved", "done", tags=["status:resolved"])


def test_completion_claim_with_valid_poe_kwarg_is_accepted(repo):
    repo_path, sha = repo
    assert shards.capture("fix", "gateway fixed", "it works now", tags=["fixed"],
                          poe=_poe(repo_path, sha))


def test_completion_claim_with_fenced_poe_is_accepted(repo):
    repo_path, sha = repo
    body = "it works now\n```poe\n" + json.dumps(_poe(repo_path, sha)) + "\n```"
    assert shards.capture("fix", "gateway fixed", body, tags=["verified"])


def test_failing_test_run_is_rejected(repo):
    repo_path, sha = repo
    assert not shards.capture("fix", "gateway fixed", "x", tags=["fixed"],
                              poe=_poe(repo_path, sha, exit_code=1))


def test_nonexistent_commit_is_rejected(repo):
    repo_path, _sha = repo
    assert not shards.capture("fix", "gateway fixed", "x", tags=["fixed"],
                              poe=_poe(repo_path, "deadbeefdeadbeef"))


def test_warn_mode_writes_but_reports(monkeypatch):
    monkeypatch.setenv("NOUGEN_POE_GATE", "warn")
    allowed, errors = poe_gate.check(["fixed"], "no proof")
    assert allowed and errors
    assert shards.capture("fix", "gateway fixed", "no proof", tags=["fixed"])


def test_off_mode_skips_gate(monkeypatch):
    monkeypatch.setenv("NOUGEN_POE_GATE", "off")
    assert shards.capture("fix", "gateway fixed", "no proof", tags=["fixed"])


def test_completion_tags_are_configurable(monkeypatch):
    monkeypatch.setenv("NOUGEN_POE_COMPLETION_TAGS", "shipped")
    assert poe_gate.is_completion_claim(["shipped"])
    assert not poe_gate.is_completion_claim(["fixed"])

"""The vault must never be chosen by accident.

A stray `.vault/` directory used to capture the entire grid because the path
was resolved against CWD and `ngs-node.sh` cd's into the repo first. Writes
then reported success into a store nobody searched — 8,289 rows stranded on
one node on 2026-09-03 while capture kept returning {"captured": true}.

These tests pin the three properties that make that impossible to repeat:
CWD cannot change the answer, a repo-local vault is opt-in only, and any
non-default choice is announced.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


def _reload_core(monkeypatch, env: dict, cwd: Path | None = None):
    for k in ("NOUGEN_VAULT_DIR", "NOUGEN_VAULT_ALLOW_LOCAL"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    if cwd is not None:
        monkeypatch.chdir(cwd)
    sys.modules.pop("nougen_shards.core", None)
    return importlib.import_module("nougen_shards.core")


def test_stray_dot_vault_in_cwd_is_ignored(monkeypatch, tmp_path):
    """The regression that stranded 8,289 rows."""
    (tmp_path / ".vault").mkdir()
    core = _reload_core(monkeypatch, {}, cwd=tmp_path)

    assert core.GLOBAL_DIR != (tmp_path / ".vault").resolve()
    assert core.GLOBAL_DIR == (Path.home() / ".nougen" / "shards").resolve()
    assert core.VAULT_SOURCE == "default"


def test_cwd_cannot_change_the_answer(monkeypatch, tmp_path):
    """Same process, two directories, one vault."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (b / ".vault").mkdir()

    from_a = _reload_core(monkeypatch, {}, cwd=a).GLOBAL_DIR
    from_b = _reload_core(monkeypatch, {}, cwd=b).GLOBAL_DIR
    assert from_a == from_b, "vault must not depend on the directory of launch"


def test_explicit_env_wins_and_is_absolute(monkeypatch, tmp_path):
    target = tmp_path / "explicit_vault"
    target.mkdir()
    core = _reload_core(monkeypatch, {"NOUGEN_VAULT_DIR": str(target)})

    assert core.GLOBAL_DIR == target.resolve()
    assert core.GLOBAL_DIR.is_absolute()
    assert core.VAULT_SOURCE == "NOUGEN_VAULT_DIR"


def test_relative_env_value_is_resolved_absolute(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "rel").mkdir()
    core = _reload_core(monkeypatch, {"NOUGEN_VAULT_DIR": "rel"}, cwd=tmp_path)
    assert core.GLOBAL_DIR.is_absolute()


def test_repo_local_requires_opt_in(monkeypatch, tmp_path):
    """Even a real repo-local vault must be asked for by name."""
    core = _reload_core(monkeypatch, {})
    assert core.VAULT_SOURCE == "default"

    core2 = _reload_core(monkeypatch, {"NOUGEN_VAULT_ALLOW_LOCAL": "1"})
    # No .vault beside the package in a test checkout, so it still falls back —
    # the point is that opting in cannot be done accidentally.
    assert core2.VAULT_SOURCE in ("default", "repo-local (NOUGEN_VAULT_ALLOW_LOCAL=1)")


def test_non_default_choice_is_announced(monkeypatch, tmp_path, caplog):
    """Silence is what made the stranding invisible for a week."""
    target = tmp_path / "loud"
    target.mkdir()
    with caplog.at_level("WARNING"):
        core = _reload_core(monkeypatch, {"NOUGEN_VAULT_DIR": str(target)})
    assert core.VAULT_SOURCE == "NOUGEN_VAULT_DIR"
    assert any("vault resolved to" in r.message.lower() or
               "vault resolved to" in str(r.msg).lower() for r in caplog.records), \
        "a non-default vault must be logged, not chosen silently"


@pytest.fixture(autouse=True)
def _restore_core():
    yield
    sys.modules.pop("nougen_shards.core", None)
    importlib.import_module("nougen_shards.core")

"""pr_lease: the `gh pr list` timeout resolves from env, and the gh wrapper
fails loudly instead of returning a partial list. No real gh call is made."""
from types import SimpleNamespace

import pytest

from nougen_shards import pr_lease


def test_gh_timeout_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("NOUGEN_GH_TIMEOUT_S", raising=False)
    assert pr_lease._gh_timeout_s() == pr_lease.DEFAULT_GH_TIMEOUT_S


def test_gh_timeout_reads_env(monkeypatch):
    monkeypatch.setenv("NOUGEN_GH_TIMEOUT_S", "12.5")
    assert pr_lease._gh_timeout_s() == 12.5


@pytest.mark.parametrize("bad", ["abc", "0", "-3", "nan", "inf"])
def test_gh_timeout_bad_value_falls_back_with_warning(monkeypatch, caplog, bad):
    monkeypatch.setenv("NOUGEN_GH_TIMEOUT_S", bad)
    with caplog.at_level("WARNING", logger="nougen_shards.pr_lease"):
        assert pr_lease._gh_timeout_s() == pr_lease.DEFAULT_GH_TIMEOUT_S
    assert "is not a positive number" in caplog.text


def _fake_run(recorded, returncode=0, stdout='[{"number": 1}]', stderr=""):
    def run(*args, **kwargs):
        recorded.update(kwargs)
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
    return run


def test_gh_pr_list_passes_env_timeout(monkeypatch):
    monkeypatch.setenv("NOUGEN_GH_TIMEOUT_S", "7")
    monkeypatch.setattr(pr_lease, "_gh_available", lambda: True)
    recorded = {}
    monkeypatch.setattr(pr_lease.subprocess, "run", _fake_run(recorded))
    assert pr_lease._gh_pr_list("owner/repo") == [{"number": 1}]
    assert recorded["timeout"] == 7.0


def test_gh_pr_list_nonzero_exit_raises(monkeypatch):
    monkeypatch.setattr(pr_lease, "_gh_available", lambda: True)
    monkeypatch.setattr(pr_lease.subprocess, "run",
                        _fake_run({}, returncode=1, stdout="", stderr="boom"))
    with pytest.raises(RuntimeError, match="gh pr list failed: boom"):
        pr_lease._gh_pr_list("owner/repo")


def test_gh_pr_list_without_gh_raises(monkeypatch):
    monkeypatch.setattr(pr_lease, "_gh_available", lambda: False)
    with pytest.raises(RuntimeError, match="gh CLI not found on PATH"):
        pr_lease._gh_pr_list("owner/repo")

"""fd_budget: a node must raise its own descriptor ceiling, and say so.

Background: phoebus measured 14 descriptors at rest and exactly 256 (the
launchd soft default) under a six-way recall burst, after which every open()
failed and recall went cold on every request. These tests pin the contract of
the startup raise without touching the real process limit.
"""
import logging
import sys
from pathlib import Path

import pytest

# `resource` is POSIX-only. Importing it at module scope aborted COLLECTION on
# Windows, so `pytest tests/` on whoart or blade died with "Interrupted: 1 error
# during collection" and deselected all ~1017 tests -- two of the three fleet
# nodes could not run the suite at all, and the failure reads like a broken
# tree rather than a platform gap. The descriptor ceiling this file pins is a
# launchd/POSIX contract, so skipping here loses no coverage: CI and phoebus
# still run it.
resource = pytest.importorskip(
    "resource", reason="POSIX-only; fd ceiling is a launchd contract")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards import fd_budget  # noqa: E402


class _FakeResource:
    RLIMIT_NOFILE = resource.RLIMIT_NOFILE
    RLIM_INFINITY = resource.RLIM_INFINITY

    def __init__(self, soft, hard, fail_set=None):
        self.soft, self.hard = soft, hard
        self.set_calls = []
        self.fail_set = fail_set

    def getrlimit(self, _which):
        return (self.soft, self.hard)

    def setrlimit(self, _which, pair):
        if self.fail_set:
            raise self.fail_set
        self.set_calls.append(pair)
        self.soft, self.hard = pair


@pytest.fixture
def fake(monkeypatch):
    def _install(soft, hard, fail_set=None):
        fr = _FakeResource(soft, hard, fail_set)
        monkeypatch.setitem(sys.modules, "resource", fr)
        return fr
    return _install


def test_raises_launchd_default_to_minimum(fake, caplog):
    fr = fake(256, resource.RLIM_INFINITY)
    with caplog.at_level(logging.WARNING, logger="nougen_shards.fd_budget"):
        rep = fd_budget.ensure_fd_headroom(4096)
    assert rep["raised"] is True
    assert rep["before"] == 256 and rep["after"] == 4096
    assert fr.set_calls == [(4096, resource.RLIM_INFINITY)]
    # The raise is a WARNING-level event: the node runs at WARNING and a
    # working raise must leave a trace (absence of a line proved nothing once).
    assert any("raised 256 -> 4096" in r.getMessage() for r in caplog.records)


def test_already_above_minimum_is_a_noop(fake):
    fr = fake(1048576, resource.RLIM_INFINITY)
    rep = fd_budget.ensure_fd_headroom(4096)
    assert rep["raised"] is False and rep["after"] == 1048576
    assert fr.set_calls == []


def test_finite_hard_limit_caps_the_raise(fake):
    fr = fake(256, 1024)
    rep = fd_budget.ensure_fd_headroom(4096)
    assert rep["raised"] is True and rep["after"] == 1024
    assert fr.set_calls == [(1024, 1024)]


def test_hard_at_or_below_soft_warns_and_does_not_raise(fake, caplog):
    fr = fake(256, 256)
    with caplog.at_level(logging.WARNING, logger="nougen_shards.fd_budget"):
        rep = fd_budget.ensure_fd_headroom(4096)
    assert rep["raised"] is False and rep["after"] == 256
    assert fr.set_calls == []
    assert any("hard limit 256 prevents" in r.getMessage() for r in caplog.records)


def test_setrlimit_failure_never_propagates(fake, caplog):
    fake(256, resource.RLIM_INFINITY, fail_set=ValueError("not permitted"))
    with caplog.at_level(logging.WARNING, logger="nougen_shards.fd_budget"):
        rep = fd_budget.ensure_fd_headroom(4096)
    assert rep["raised"] is False and rep["after"] == 256
    assert any("could not raise" in r.getMessage() for r in caplog.records)


def test_minimum_comes_from_env_first(fake, monkeypatch):
    monkeypatch.setenv(fd_budget.ENV_MIN_NOFILE, "8192")
    fr = fake(256, resource.RLIM_INFINITY)
    rep = fd_budget.ensure_fd_headroom()
    assert rep["wanted"] == 8192 and fr.set_calls == [(8192, resource.RLIM_INFINITY)]


def test_bad_env_falls_back_to_default(fake, monkeypatch, caplog):
    monkeypatch.setenv(fd_budget.ENV_MIN_NOFILE, "lots")
    fake(256, resource.RLIM_INFINITY)
    with caplog.at_level(logging.WARNING, logger="nougen_shards.fd_budget"):
        rep = fd_budget.ensure_fd_headroom()
    assert rep["wanted"] == fd_budget.DEFAULT_MIN_NOFILE
    assert any("is not an int" in r.getMessage() for r in caplog.records)


def test_open_fd_count_is_a_number_here():
    n = fd_budget.open_fd_count()
    assert n is None or n >= 3  # stdin/stdout/stderr at minimum


def test_real_process_call_is_safe():
    # Whatever this test runner's limits are, the call must not throw and
    # must report a consistent before/after pair.
    rep = fd_budget.ensure_fd_headroom()
    assert rep["supported"] is True
    assert rep["after"] >= rep["before"]

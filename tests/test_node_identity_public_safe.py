"""A public clone must not impersonate a reference-fleet machine.

NouGenShards is public. get_current_node() used to decide identity by
ELIMINATION -- every non-Windows host was "phoebus", every other Windows host
was "blade" -- so a stranger cloning the repo emitted a fleet identity that was
never theirs. These tests pin the inverted default: membership is asserted by
matching, and everything else is standalone.
"""
import os
import socket

import pytest

from nougen_shards.nougenmsg import get_current_node, is_fleet_node, STANDALONE_NODE


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Neutral machine: no fleet env, no marker file, caller picks the hostname."""
    for key in ("NOUGEN_FLEET_NODE", "COMPUTERNAME", "HOSTNAME"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    def _set(hostname="", computername=None, marker=None, fleet_env=None):
        monkeypatch.setattr(socket, "gethostname", lambda: hostname)
        if computername is not None:
            monkeypatch.setenv("COMPUTERNAME", computername)
        if fleet_env is not None:
            monkeypatch.setenv("NOUGEN_FLEET_NODE", fleet_env)
        if marker is not None:
            d = tmp_path / ".nougen"
            d.mkdir(exist_ok=True)
            (d / "fleet_node").write_text(marker, encoding="utf-8")
    return _set


@pytest.mark.parametrize("hostname,computername", [
    ("ubuntu-dev-box", None),
    ("Johns-MacBook-Pro", None),
    ("DESKTOP-8891", "DESKTOP-8891"),
    ("ci-runner-7", "CI-RUNNER-7"),
])
def test_stranger_never_impersonates_a_fleet_node(env, hostname, computername):
    env(hostname=hostname, computername=computername)
    assert get_current_node() == STANDALONE_NODE
    assert is_fleet_node() is False


@pytest.mark.parametrize("hostname,computername,expected", [
    ("WhoArt", "WhoArt", "whoart"),
    ("ProArt-PX13", "ProArt-PX13", "whoart"),
    ("Blade1TB", "Blade1TB", "blade"),
])
def test_fleet_hosts_still_resolve_by_hostname(env, hostname, computername, expected):
    env(hostname=hostname, computername=computername)
    assert get_current_node() == expected
    assert is_fleet_node() is True


def test_fleet_host_whose_name_carries_no_marker_needs_the_marker_file(env):
    """Regression guard, measured not imagined.

    The reference fleet's macOS node really answers to
    'KushBoyGroups-Mac-mini.local' -- no 'phoebus' anywhere in it. Matching on
    hostname alone therefore demotes it to standalone. That hostname is NOT
    hardcoded in the source (it is private, and this repo is public); the
    operator declares identity locally instead.
    """
    env(hostname="KushBoyGroups-Mac-mini.local")
    assert get_current_node() == STANDALONE_NODE, "unmarked -> standalone, by design"

    env(hostname="KushBoyGroups-Mac-mini.local", marker="phoebus")
    assert get_current_node() == "phoebus"
    assert is_fleet_node() is True


def test_env_var_beats_hostname_and_marker(env):
    env(hostname="Blade1TB", computername="Blade1TB", marker="whoart", fleet_env="phoebus")
    assert get_current_node() == "phoebus"


def test_blank_marker_file_is_ignored(env):
    env(hostname="ubuntu-dev-box", marker="   \n")
    assert get_current_node() == STANDALONE_NODE

"""The receiver must not silently reopen when a provisioned secret stops resolving.

Observed live 2026-09-03 on a LAN-reachable node: one vault key stopped
resolving, the launch wrapper exported an empty string, and a routine reload
flipped the receiver from auth=required to auth=open for about 37 minutes.
Unauthenticated POSTs were accepted. Nothing announced it, because to the code
a node with no token has simply never been provisioned.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))


def load(monkeypatch, token: str = "", latch: str = None):
    """Re-import the receiver with a given token/latch pair, as a reload would."""
    monkeypatch.setenv("NOUGEN_AGY_MSG_TOKEN", token)
    if latch is None:
        monkeypatch.delenv("NOUGEN_AGY_MSG_AUTH", raising=False)
    else:
        monkeypatch.setenv("NOUGEN_AGY_MSG_AUTH", latch)
    for name in [m for m in sys.modules if m.startswith("nougenmsg_node")]:
        del sys.modules[name]
    return importlib.import_module("nougenmsg_node")


def test_unprovisioned_node_still_accepts(monkeypatch):
    """No token, no latch: a fresh node keeps working, so rollout is unaffected."""
    node = load(monkeypatch, token="", latch=None)
    assert node.AUTH_LATCH is False
    assert node._auth_mode() == "open(unlatched)"


def test_provisioned_and_healthy(monkeypatch):
    node = load(monkeypatch, token="a-token", latch="required")
    assert node.AUTH_TOKEN and node.AUTH_LATCH
    assert node._auth_mode() == "required(latch=on)"


def test_the_incident_latched_but_token_vanished(monkeypatch):
    """The regression this exists for: latched, secret gone, must NOT read open."""
    node = load(monkeypatch, token="", latch="required")
    assert node.AUTH_LATCH is True
    assert node.AUTH_TOKEN == ""
    mode = node._auth_mode()
    assert mode == "LATCHED-NO-TOKEN:refusing-mutations"
    assert "open" not in mode, "a latched node with no token must never print open"


@pytest.mark.parametrize("value", ["required", "yes", "1", "on", "typo", "REQUIRED"])
def test_latch_parsing_is_fail_safe(monkeypatch, value):
    """Any value but an explicit off-word latches, so a typo closes the door."""
    assert load(monkeypatch, token="", latch=value).AUTH_LATCH is True


@pytest.mark.parametrize("value", ["", "0", "off", "false", "optional", "  "])
def test_explicit_off_words_do_not_latch(monkeypatch, value):
    assert load(monkeypatch, token="", latch=value).AUTH_LATCH is False


def test_startup_line_reports_the_latch_this_code_read(monkeypatch):
    """A config-only change must not be able to masquerade as protection.

    A latch set in a service definition while the running build has no
    reference to it is worse than being openly unprotected, because the wrong
    belief stops anyone looking. This happened on this fleet. If the mode
    string cannot express the latch, this build is not reading it.
    """
    for token, latch, expect in (("t", "required", "latch=on"),
                                 ("t", None, "latch=off"),
                                 ("", "required", "LATCHED-NO-TOKEN")):
        assert expect in load(monkeypatch, token=token, latch=latch)._auth_mode()

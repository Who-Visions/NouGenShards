"""Which SESSION and which HOST sent a ping, distinct from get_current_node().

get_current_node() answers one of three hardcoded names -- "phoebus", "whoart",
or "blade" -- and every payload built from it names a LANE, not a writer. A
connector session inherits whichever branch fires and a box running several
sessions under one lane shows no difference between them in the record.

Measured on blade 2026-09-08 (the sibling defect on the relay side, same root
cause): 124 relay legs filed under one byline in a single day, 28 of them from
the session reading them back, and work misattributed four times on the
strength of the lane label alone. This file guards the NouGenMsg half of the
same fix: resolve_session()/resolve_origin_host() must be independent of
get_current_node(), and must degrade to absence rather than a guess.
"""
from __future__ import annotations

import pytest

from nougen_shards import nougenmsg as m


@pytest.fixture
def clean_session_env(monkeypatch):
    for var in m._SESSION_VARS:
        monkeypatch.delenv(var, raising=False)


def test_resolve_session_is_empty_rather_than_invented(clean_session_env):
    assert m.resolve_session() == ""


def test_an_explicit_session_is_read(clean_session_env, monkeypatch):
    monkeypatch.setenv("NOUGEN_SESSION", "sess-42")
    assert m.resolve_session() == "sess-42"


def test_resolve_origin_host_is_independent_of_get_current_node(monkeypatch):
    """The load-bearing property: origin_host must not just echo the lane
    label get_current_node() returns, or it adds nothing over what exists."""
    monkeypatch.setattr(m, "get_current_node", lambda: "claude-app")
    assert m.get_current_node() == "claude-app"
    assert m.resolve_origin_host() != "claude-app"
    assert m.resolve_origin_host() != ""


def test_resolve_origin_host_is_empty_rather_than_invented(monkeypatch):
    import socket

    monkeypatch.setattr(socket, "gethostname", lambda: (_ for _ in ()).throw(OSError()))
    assert m.resolve_origin_host() == ""


def test_a_ping_payload_carries_session_when_the_harness_has_one(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_SESSION", "sess-77")
    monkeypatch.setattr(m, "get_current_node", lambda: "blade")
    codex_inbox = tmp_path / "codex_inbox"
    monkeypatch.setenv("NOUGEN_CODEX_INBOX", str(codex_inbox))
    monkeypatch.setattr(m.os.path, "expanduser",
                         lambda p: str(codex_inbox) if p.endswith(".codex/inbox".replace("/", m.os.sep))
                         or "codex" in p else p)
    m.os.makedirs(codex_inbox, exist_ok=True)
    # Ensure it always hits the fallback inbox write in testing
    from nougen_shards import codex_pipe
    monkeypatch.setattr(codex_pipe, "deliver", lambda *a, **k: (_ for _ in ()).throw(OSError("mock fallback")))

    m.AgentPinger.ping_codex("hello", origin=None)
    files = list(codex_inbox.glob("ping_*.json"))
    assert files, "expected a codex ping file to be written"
    payload = __import__("json").loads(files[0].read_text(encoding="utf-8"))
    assert payload.get("session") == "sess-77"
    assert payload.get("origin_host"), "origin_host must be populated when the host resolves"
    assert payload["origin_host"] != "blade"


def test_a_ping_payload_omits_session_when_the_harness_has_none(clean_session_env, monkeypatch, tmp_path):
    monkeypatch.setattr(m, "get_current_node", lambda: "blade")
    codex_inbox = tmp_path / "codex_inbox2"
    monkeypatch.setenv("NOUGEN_CODEX_INBOX", str(codex_inbox))
    monkeypatch.setattr(m.os.path, "expanduser",
                         lambda p: str(codex_inbox) if p.endswith(".codex/inbox".replace("/", m.os.sep))
                         or "codex" in p else p)
    m.os.makedirs(codex_inbox, exist_ok=True)
    from nougen_shards import codex_pipe
    monkeypatch.setattr(codex_pipe, "deliver", lambda *a, **k: (_ for _ in ()).throw(OSError("mock fallback")))

    m.AgentPinger.ping_codex("hello", origin=None)
    files = list(codex_inbox.glob("ping_*.json"))
    assert files, "expected a codex ping file to be written"
    payload = __import__("json").loads(files[0].read_text(encoding="utf-8"))
    assert "session" not in payload

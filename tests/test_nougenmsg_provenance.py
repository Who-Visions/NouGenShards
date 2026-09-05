"""Origin provenance must survive a hop.

`original_sender` and `relay_path` existed in the envelope schema but were
never populated, so both stayed null/empty. read_inbox and the ping_* helpers
then fell through to `nougen-<current node>`, and every message arrived
labelled with the LAST HOP rather than its origin: whoart traffic reaching
phoebus read as `nougen-phoebus` with `origin.machine: phoebus`. The content
carried the origin; the envelope did not, so cross-machine provenance was
unrecoverable after one hop.

Measured 2026-09-05: a decoded outbound envelope showed
`original_sender: null, relay_path: []` — the payload self-reported that
provenance was unknown, and named the reason, in a field nobody read.
"""
from __future__ import annotations

import pytest

from nougen_shards.nougenmsg import NouGenMsgBus


@pytest.fixture
def on_node(monkeypatch):
    def _set(name):
        monkeypatch.setattr("nougen_shards.nougenmsg.get_current_node", lambda: name)
    return _set


def test_origin_is_stamped_when_absent(on_node):
    on_node("whoart")
    env = NouGenMsgBus._origin_envelope({})
    assert env["original_sender"] == "nougen-whoart"
    assert env["relay_path"] == ["whoart"]


def test_origin_survives_a_hop_and_is_not_relabelled(on_node):
    """The defect: phoebus re-enveloping whoart traffic must not claim it."""
    on_node("whoart")
    first = NouGenMsgBus._origin_envelope({})

    on_node("phoebus")
    second = NouGenMsgBus._origin_envelope(first)

    assert second["original_sender"] == "nougen-whoart", "origin was relabelled"
    assert second["transport_machine"] == "phoebus"
    assert second["relay_path"] == ["whoart", "phoebus"]


def test_three_hops_keep_the_full_path(on_node):
    on_node("whoart")
    env = NouGenMsgBus._origin_envelope({})
    for hop in ("blade", "phoebus"):
        on_node(hop)
        env = NouGenMsgBus._origin_envelope(env)
    assert env["original_sender"] == "nougen-whoart"
    assert env["relay_path"] == ["whoart", "blade", "phoebus"]


def test_reenveloping_on_the_same_node_does_not_stack(on_node):
    """emit_fleet envelopes locally and per-peer in one pass."""
    on_node("whoart")
    env = NouGenMsgBus._origin_envelope({})
    env = NouGenMsgBus._origin_envelope(env)
    env = NouGenMsgBus._origin_envelope(env)
    assert env["relay_path"] == ["whoart"]


def test_an_explicit_sender_is_never_overwritten(on_node):
    on_node("phoebus")
    env = NouGenMsgBus._origin_envelope({"original_sender": "codex-mac-mini"})
    assert env["original_sender"] == "codex-mac-mini"


def test_machine_conflict_still_recorded_alongside_origin(on_node):
    """The existing conflict contract must not regress."""
    on_node("phoebus")
    env = NouGenMsgBus._origin_envelope({"machine": "blade"})
    assert env["conflicts"] == [{
        "field": "machine", "claimed": "blade", "transport_observed": "phoebus",
    }]
    assert env["original_sender"] == "nougen-phoebus"


def test_session_identity_is_still_not_invented(on_node):
    """Stamping the sender must not fake a session id."""
    on_node("whoart")
    env = NouGenMsgBus._origin_envelope({})
    assert env["session_id"] is None
    assert env["provenance_state"] == "unknown"
    assert env["unknown_reason"] == "session_identity_not_supplied"

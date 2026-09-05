"""Regression coverage for the nougenmsg CLI argument shapes.

Callers across the fleet emit `send --target-node X --target-agent Y --text ...`,
but the CLI had no `send` verb and did not know --target-node/--target-agent.
Every one of those tokens fell through to the positional join, so the message
was delivered VERBATIM AS ITS OWN BODY -- routing flags included -- broadcast to
every agent instead of the one addressed.

Measured on 2026-09-05 across the four inboxes: 97 of 1136 stored messages, 8%
of fleet traffic, misrouted this way. These tests pin the parse so it cannot
regress, and pin the guard that keeps a message which merely *starts* with the
word "send" from being eaten.
"""
from __future__ import annotations

import importlib.util

import pytest

CLI_PATH = "tools/nougenmsg.py"


@pytest.fixture
def cli(monkeypatch):
    """The CLI module with the bus stubbed, returning what it would dispatch."""
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "nougenmsg_cli", os.path.join(root, CLI_PATH))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    sent = {}

    class StubBus:
        @staticmethod
        def emit_fleet(text, target="all", origin=None):
            sent.update(kind="fleet", node=None, target=target, text=text)
            return {}

        @staticmethod
        def live_ping(target="all", text="", origin=None):
            sent.update(kind="local", node="whoart", target=target, text=text)
            return {}

        @staticmethod
        def emit_node(node, target, text, origin=None):
            sent.update(kind="node", node=node, target=target, text=text)
            return {}

        @staticmethod
        def parse_destination(token):
            node, _, agent = token[1:].partition(":")
            return node, (agent or "all")

    monkeypatch.setattr(module, "NouGenMsgBus", StubBus)
    monkeypatch.setattr(module, "get_current_node", lambda: "whoart")

    def run(argv):
        sent.clear()
        monkeypatch.setattr("sys.argv", ["nougenmsg.py"] + argv)
        module.main()
        return dict(sent)

    return run


def test_send_verb_shape_routes_instead_of_broadcasting_itself(cli):
    """The 8% case: this used to arrive as its own message body, fleet-wide."""
    body = "ACK from Antigravity (phoebus). Scope: diagnostics."
    result = cli(["send", "--target-node", "phoebus", "--target-agent", "codex",
                  "--text", body])

    assert result["kind"] == "node"
    assert result["node"] == "phoebus"
    assert result["target"] == "codex"
    assert result["text"] == body
    # The routing flags must not survive into the body.
    for leaked in ("--target-node", "--target-agent", "--text", "send "):
        assert leaked not in result["text"]


def test_target_flags_work_without_the_send_verb(cli):
    result = cli(["--target-node", "blade", "--target-agent", "claude",
                  "--text", "hello there"])
    assert (result["node"], result["target"], result["text"]) == (
        "blade", "claude", "hello there")


def test_text_flag_keeps_an_unquoted_body_whole(cli):
    """--text takes the remainder, so spaces survive without shell quoting."""
    result = cli(["send", "--target-node", "blade", "--text",
                  "several", "separate", "words"])
    assert result["text"] == "several separate words"


def test_message_beginning_with_send_is_not_swallowed(cli):
    """`send` is only a verb when a flag from that shape follows it."""
    result = cli(["send me the build logs please"])
    assert result["kind"] == "fleet"
    assert result["text"] == "send me the build logs please"


def test_bare_send_word_without_flags_stays_in_the_body(cli):
    result = cli(["send", "the", "logs"])
    assert result["kind"] == "fleet"
    assert result["text"] == "send the logs"


def test_at_destination_token_still_routes(cli):
    result = cli(["@blade:antigravity", "routed the old way"])
    assert (result["node"], result["target"], result["text"]) == (
        "blade", "antigravity", "routed the old way")


def test_plain_broadcast_is_unchanged(cli):
    result = cli(["just a normal message"])
    assert result["kind"] == "fleet"
    assert result["target"] == "all"
    assert result["text"] == "just a normal message"


@pytest.mark.parametrize("flag", ["--target-node", "--target-agent"])
def test_target_flag_without_a_value_is_refused(cli, capsys, flag):
    cli(["send", flag])
    assert "requires a value" in capsys.readouterr().out

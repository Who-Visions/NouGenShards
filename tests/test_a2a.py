"""Tests for the A2A (agent-to-agent) message bus."""

import pytest

from nougen_shards import a2a
import nougen_shards.agents as agents_mod


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def clean_echo_handler():
    """Register an 'Echo' handler and guarantee cleanup."""
    def handler(message: a2a.A2AMessage) -> a2a.A2AMessage:
        return message.reply("echo:" + message.content, sender="Echo")

    a2a.register_handler("Echo", handler)
    try:
        yield handler
    finally:
        a2a.unregister_handler("Echo")


# --------------------------------------------------------------------------- #
# A2AMessage dataclass
# --------------------------------------------------------------------------- #
def test_reply_preserves_correlation_id_and_swaps_endpoints():
    msg = a2a.A2AMessage(sender="Alice", recipient="Bob", content="hi")
    rep = msg.reply("hello back")

    assert rep.correlation_id == msg.correlation_id
    assert rep.sender == "Bob"        # default sender == original recipient
    assert rep.recipient == "Alice"   # swap
    assert rep.content == "hello back"
    assert rep.intent == msg.intent


def test_reply_explicit_sender_and_metadata():
    msg = a2a.A2AMessage(sender="Alice", recipient="Bob", content="hi")
    rep = msg.reply("yo", sender="Carol", metadata={"k": "v"})

    assert rep.sender == "Carol"
    assert rep.recipient == "Alice"
    assert rep.metadata == {"k": "v"}
    assert rep.correlation_id == msg.correlation_id


def test_to_dict_round_trips_fields():
    msg = a2a.A2AMessage(
        sender="Alice",
        recipient="Bob",
        content="hi",
        intent=a2a.QUERY,
        metadata={"a": 1},
    )
    d = msg.to_dict()

    assert d["sender"] == "Alice"
    assert d["recipient"] == "Bob"
    assert d["content"] == "hi"
    assert d["intent"] == a2a.QUERY
    assert d["metadata"] == {"a": 1}
    assert d["correlation_id"] == msg.correlation_id
    # rebuild from dict
    rebuilt = a2a.A2AMessage(**d)
    assert rebuilt == msg


def test_intent_constants():
    assert a2a.CHAT == "chat"
    assert a2a.RECALL == "recall"
    assert a2a.CONSOLIDATE == "consolidate"
    assert a2a.QUERY == "query"


# --------------------------------------------------------------------------- #
# Handler registry
# --------------------------------------------------------------------------- #
def test_register_and_send_to_handler(clean_echo_handler):
    msg = a2a.A2AMessage(sender="Tester", recipient="Echo", content="ping")
    rep = a2a.send(msg)

    assert rep.content == "echo:ping"
    assert rep.sender == "Echo"
    assert rep.recipient == "Tester"
    assert rep.correlation_id == msg.correlation_id


def test_has_handler_case_insensitive(clean_echo_handler):
    assert a2a.has_handler("Echo") is True
    assert a2a.has_handler("echo") is True
    assert a2a.has_handler("ECHO") is True


def test_registered_handlers_includes_lowercased_name(clean_echo_handler):
    handlers = a2a.registered_handlers()
    assert "echo" in handlers
    assert handlers == sorted(handlers)


def test_unregister_handler_removes_it():
    def handler(message):
        return message.reply("x")

    a2a.register_handler("Temp", handler)
    assert a2a.has_handler("temp") is True
    a2a.unregister_handler("Temp")
    assert a2a.has_handler("temp") is False


# --------------------------------------------------------------------------- #
# Handler exception path
# --------------------------------------------------------------------------- #
def test_handler_exception_returns_error_reply():
    def boom(message):
        raise RuntimeError("kaboom")

    a2a.register_handler("Boomer", boom)
    try:
        msg = a2a.A2AMessage(sender="Tester", recipient="Boomer", content="x")
        rep = a2a.send(msg)
    finally:
        a2a.unregister_handler("Boomer")

    assert rep.sender == "a2a-bus"
    assert rep.metadata.get("error") == "handler_exception"
    assert rep.recipient == "Tester"
    assert rep.correlation_id == msg.correlation_id


# --------------------------------------------------------------------------- #
# Fallback to roster via run_agent
# --------------------------------------------------------------------------- #
def test_fallback_to_roster(monkeypatch):
    sentinel = "SENTINEL-ANSWER"

    class FakeSpec:
        name = "Fallbacker"

    monkeypatch.setattr(agents_mod, "get_agent", lambda name: FakeSpec())
    monkeypatch.setattr(agents_mod, "run_agent", lambda name, content: sentinel)

    # Ensure no handler shadows the fallback path.
    assert not a2a.has_handler("Fallbacker")

    msg = a2a.A2AMessage(sender="Tester", recipient="Fallbacker", content="q")
    rep = a2a.send(msg)

    assert rep.content == sentinel
    assert rep.sender == "Fallbacker"
    assert rep.recipient == "Tester"


def test_unknown_recipient(monkeypatch):
    monkeypatch.setattr(agents_mod, "get_agent", lambda name: None)

    msg = a2a.A2AMessage(sender="Tester", recipient="Nobody", content="q")
    rep = a2a.send(msg)

    assert rep.sender == "a2a-bus"
    assert rep.metadata.get("error") == "unknown_recipient"
    assert rep.recipient == "Tester"


# --------------------------------------------------------------------------- #
# ask() convenience
# --------------------------------------------------------------------------- #
def test_ask_returns_reply_text(clean_echo_handler):
    out = a2a.ask("Tester", "Echo", "hey")
    assert out == "echo:hey"


# --------------------------------------------------------------------------- #
# MESSAGE_LOG growth
# --------------------------------------------------------------------------- #
def test_message_log_grows(clean_echo_handler):
    before = len(a2a.MESSAGE_LOG)
    a2a.send(a2a.A2AMessage(sender="Tester", recipient="Echo", content="log-me"))
    after = len(a2a.MESSAGE_LOG)

    assert after == before + 1
    entry = a2a.MESSAGE_LOG[-1]
    assert "request" in entry and "reply" in entry
    assert entry["reply"]["content"] == "echo:log-me"

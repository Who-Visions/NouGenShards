"""
Hermetic tests for the Griot agent (src/nougen_shards/griot.py).

No live LLM and no real Ollama: model completions are stubbed via monkeypatch,
and DB-backed paths use a temp-DB fixture mirroring tests/test_dual_system.py.
"""

import json
import tempfile
from pathlib import Path

import pytest

from nougen_shards import griot
from nougen_shards import a2a
import nougen_shards.core as core


# ----------------------------------------------------------------------------
# Tool & ToolRegistry
# ----------------------------------------------------------------------------

def test_tool_signature_no_params():
    t = griot.Tool(name="ping", func=lambda: None)
    assert t.signature() == "ping()"


def test_tool_signature_required_and_optional():
    t = griot.Tool(
        name="foo",
        func=lambda x, y=None: None,
        parameters={
            "x": {"type": "string", "required": True},
            "y": {"type": "integer", "required": False},
        },
    )
    assert t.signature() == "foo(x: string, y?: integer)"


def test_tool_signature_default_type_is_any():
    t = griot.Tool(name="bar", func=lambda x: None,
                   parameters={"x": {"required": True}})
    assert t.signature() == "bar(x: any)"


def test_registry_register_direct_and_call():
    reg = griot.ToolRegistry()
    reg.register("add", lambda a, b: a + b,
                 description="adds", parameters={"a": {"required": True}})
    assert reg.call("add", a=2, b=3) == 5
    tool = reg.get("add")
    assert tool is not None
    assert tool.description == "adds"


def test_registry_register_decorator_form():
    reg = griot.ToolRegistry()

    @reg.register("greet", description="says hi")
    def greet(who):
        return f"hi {who}"

    assert reg.get("greet") is not None
    assert reg.call("greet", who="x") == "hi x"
    # Decorator returns the original function.
    assert greet("y") == "hi y"


def test_registry_register_decorator_uses_docstring():
    reg = griot.ToolRegistry()

    @reg.register("doc")
    def doc():
        """from docstring"""
        return 1

    assert reg.get("doc").description == "from docstring"


def test_registry_call_unknown_raises_keyerror():
    reg = griot.ToolRegistry()
    with pytest.raises(KeyError):
        reg.call("nope")


def test_registry_get_unknown_returns_none():
    reg = griot.ToolRegistry()
    assert reg.get("nope") is None


def test_registry_unregister():
    reg = griot.ToolRegistry()
    reg.register("temp", lambda: 1)
    assert reg.get("temp") is not None
    reg.unregister("temp")
    assert reg.get("temp") is None
    # Unregistering an unknown tool is a no-op (no raise).
    reg.unregister("never_existed")


def test_registry_names_sorted():
    reg = griot.ToolRegistry()
    reg.register("zebra", lambda: 1)
    reg.register("apple", lambda: 1)
    reg.register("mango", lambda: 1)
    assert reg.names() == ["apple", "mango", "zebra"]


def test_registry_specs():
    reg = griot.ToolRegistry()
    reg.register("foo", lambda x: x, description="d",
                 parameters={"x": {"type": "string", "required": True}})
    specs = reg.specs()
    assert specs == [{"name": "foo", "signature": "foo(x: string)",
                      "description": "d"}]


def test_registry_catalog_empty():
    reg = griot.ToolRegistry()
    assert reg.catalog() == "(no tools registered)"


def test_registry_catalog_lists_tools():
    reg = griot.ToolRegistry()
    reg.register("foo", lambda: 1, description="does foo")
    cat = reg.catalog()
    assert "- foo() — does foo" in cat


# ----------------------------------------------------------------------------
# _parse_action
# ----------------------------------------------------------------------------

def test_parse_action_tool_json():
    obj = griot.Griot._parse_action('{"tool": "recall", "args": {"query": "x"}}')
    assert obj == {"tool": "recall", "args": {"query": "x"}}


def test_parse_action_answer_json():
    obj = griot.Griot._parse_action('{"answer": "hello"}')
    assert obj == {"answer": "hello"}


def test_parse_action_embedded_in_prose():
    raw = 'Sure, here is my action:\n{"answer": "embedded"}\nThanks!'
    obj = griot.Griot._parse_action(raw)
    assert obj == {"answer": "embedded"}


def test_parse_action_non_json_returns_none():
    assert griot.Griot._parse_action("just plain text, no json here") is None


def test_parse_action_json_without_tool_or_answer_returns_none():
    assert griot.Griot._parse_action('{"foo": "bar"}') is None


# ----------------------------------------------------------------------------
# Griot construction / builtin tools
# ----------------------------------------------------------------------------

def test_griot_default_model():
    g = griot.Griot()
    assert g.model == griot.GRIOT_MODEL


def test_griot_builtin_tools_registered():
    g = griot.Griot()
    names = g.tools.names()
    for expected in ("recall", "list_rules", "consolidate", "ask_peer", "capture"):
        assert expected in names


# ----------------------------------------------------------------------------
# chat() — dynamic function calling (hermetic via stubs)
# ----------------------------------------------------------------------------

def test_chat_tool_call_then_answer(monkeypatch):
    g = griot.Griot()
    monkeypatch.setattr(g, "recall", lambda message: "FIXED_CONTEXT")

    invoked = {"count": 0}
    g.tools.register("faketool", lambda foo: invoked.__setitem__("count",
                                                                  invoked["count"] + 1) or "tool-ran",
                     parameters={"foo": {"type": "string", "required": True}})

    scripted = iter([
        '{"tool": "faketool", "args": {"foo": "bar"}}',
        '{"answer": "final"}',
    ])
    monkeypatch.setattr(g, "_complete", lambda messages: next(scripted))

    result = g.chat("hello")
    assert result == "final"
    assert invoked["count"] == 1


def test_chat_direct_answer(monkeypatch):
    g = griot.Griot()
    monkeypatch.setattr(g, "recall", lambda message: "CTX")
    monkeypatch.setattr(g, "_complete", lambda messages: '{"answer": "immediate"}')
    assert g.chat("q") == "immediate"


def test_chat_non_json_reply_returned_raw(monkeypatch):
    g = griot.Griot()
    monkeypatch.setattr(g, "recall", lambda message: "CTX")
    monkeypatch.setattr(g, "_complete", lambda messages: "  plain prose answer  ")
    assert g.chat("q") == "plain prose answer"


def test_chat_offline_with_context(monkeypatch):
    g = griot.Griot()
    monkeypatch.setattr(g, "recall", lambda message: "recalled vault truth")
    monkeypatch.setattr(g, "_complete", lambda messages: None)
    out = g.chat("q")
    assert "recalled vault truth" in out
    assert "[Griot offline" in out


def test_chat_offline_empty_vault(monkeypatch):
    g = griot.Griot()
    monkeypatch.setattr(g, "recall", lambda message: "<!-- empty -->")
    monkeypatch.setattr(g, "_complete", lambda messages: None)
    out = g.chat("q")
    assert "[Griot offline]" in out
    assert "Pa gen okenn memwa" in out


def test_chat_tool_error_recovers_and_finishes(monkeypatch):
    g = griot.Griot()
    monkeypatch.setattr(g, "recall", lambda message: "CTX")

    def boom(**kwargs):
        raise RuntimeError("kaboom")
    g.tools.register("explode", boom)

    seen_observation = {}

    scripted = iter([
        '{"tool": "explode", "args": {}}',
        '{"answer": "done"}',
    ])

    def fake_complete(messages):
        # Capture the latest tool result fed back into the loop.
        for m in messages:
            if m["content"].startswith("TOOL_RESULT explode:"):
                seen_observation["text"] = m["content"]
        return next(scripted)

    monkeypatch.setattr(g, "_complete", fake_complete)
    assert g.chat("q") == "done"
    assert "[tool error]" in seen_observation.get("text", "")


def test_chat_out_of_steps_forces_close(monkeypatch):
    g = griot.Griot()
    monkeypatch.setattr(g, "recall", lambda message: "CTX")
    g.tools.register("loop", lambda: "again")

    calls = {"n": 0}

    def always_tool(messages):
        calls["n"] += 1
        # After exhausting max_steps, the loop issues one final _complete.
        if calls["n"] > 2:
            return "FINAL TEXT"
        return '{"tool": "loop", "args": {}}'

    monkeypatch.setattr(g, "_complete", always_tool)
    out = g.chat("q", max_steps=2)
    assert out == "FINAL TEXT"


# ----------------------------------------------------------------------------
# handle_a2a routing
# ----------------------------------------------------------------------------

def test_handle_a2a_chat(monkeypatch):
    g = griot.Griot()
    monkeypatch.setattr(g, "chat", lambda content: "pong")
    msg = a2a.A2AMessage(sender="Tester", recipient="Griot",
                         content="hi", intent=a2a.CHAT)
    reply = g.handle_a2a(msg)
    assert isinstance(reply, a2a.A2AMessage)
    assert reply.content == "pong"
    assert reply.sender == "Griot"
    assert reply.recipient == "Tester"
    assert reply.correlation_id == msg.correlation_id


def test_handle_a2a_consolidate(monkeypatch):
    g = griot.Griot()
    monkeypatch.setattr(g, "consolidate", lambda: {"x": 1})
    msg = a2a.A2AMessage(sender="Tester", recipient="Griot",
                         content="go", intent=a2a.CONSOLIDATE)
    reply = g.handle_a2a(msg)
    assert reply.sender == "Griot"
    assert json.loads(reply.content) == {"x": 1}


def test_handle_a2a_recall(monkeypatch):
    g = griot.Griot()
    monkeypatch.setattr(g, "recall", lambda content: f"recalled:{content}")
    msg = a2a.A2AMessage(sender="Tester", recipient="Griot",
                         content="topic", intent=a2a.RECALL)
    reply = g.handle_a2a(msg)
    assert reply.sender == "Griot"
    assert reply.content == "recalled:topic"


# ----------------------------------------------------------------------------
# DB-backed: list_rules / consolidate (temp-DB fixture)
# ----------------------------------------------------------------------------

@pytest.fixture
def temp_db(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(core, "GLOBAL_DIR", temp_path)
        monkeypatch.setattr(core, "get_db_path",
                            lambda index: temp_path / f"test_shards_{index}.db")
        monkeypatch.setattr(core, "get_routing_index", lambda fhash: 1)
        monkeypatch.setattr(core, "get_write_index", lambda fhash: 1)
        core.init_db(1)
        yield temp_path


def test_list_rules_empty(temp_db):
    g = griot.Griot()
    assert g.list_rules() == []


def test_consolidate_with_injected_extractor(temp_db):
    g = griot.Griot()
    core.capture(
        event_type="TEST",
        title="Episodic Log",
        content="An interaction worth consolidating.",
    )

    res = g.consolidate(
        limit=10,
        extractor=lambda content: [{"subject": "S", "predicate": "P"}],
    )
    assert res["shards_scanned"] == 1
    assert res["shards_consolidated"] == 1
    assert res["new_invariants_extracted"] == 1
    assert res["rules"][0] == {"subject": "S", "predicate": "P"}

    # The rule is now listable.
    rules = g.list_rules()
    assert len(rules) == 1
    assert rules[0]["subject"] == "S"
    assert rules[0]["predicate"] == "P"

    # Source shard is marked consolidated.
    conn = core.get_connection(1)
    try:
        row = conn.execute("SELECT consolidated FROM shards LIMIT 1").fetchone()
        assert row["consolidated"] == 1
    finally:
        conn.close()


def test_list_rules_filter_by_subject(temp_db):
    g = griot.Griot()
    conn = core.get_connection(1)
    try:
        conn.execute(
            "INSERT INTO semantic_knowledge (subject, predicate, confidence_score, "
            "domain_key, updated_at) VALUES ('Docker', 'pred', 1.0, 'global', "
            "'2026-06-16T12:00:00Z')")
        conn.execute(
            "INSERT INTO semantic_knowledge (subject, predicate, confidence_score, "
            "domain_key, updated_at) VALUES ('SQLite', 'pred2', 1.0, 'global', "
            "'2026-06-16T12:00:00Z')")
        conn.commit()
    finally:
        conn.close()

    rules = g.list_rules(subject="Docker")
    assert len(rules) == 1
    assert rules[0]["subject"] == "Docker"

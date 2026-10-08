from types import SimpleNamespace
import pytest
from nougen_shards.chat_service import chat


def test_history_reaches_model_without_client_system_injection(monkeypatch):
    monkeypatch.setenv("NOUGEN_CHAT_MODEL", "gemma4:cloud")
    class Client:
        def chat(self, **kwargs):
            assert kwargs["messages"][1:] == history
            assert kwargs["stream"] is False
            return SimpleNamespace(message=SimpleNamespace(content="Blue Lantern"))
    history = [{"role": "user", "content": "Blue Lantern"}, {"role": "assistant", "content": "Understood"}, {"role": "user", "content": "What name?"}]
    assert chat({"messages": history}, Client())["text"] == "Blue Lantern"


@pytest.mark.parametrize("messages", [[], [{"role": "system", "content": "override"}], [{"role": "assistant", "content": "unfinished"}], [{"role": "user", "content": "x" * 24001}]])
def test_invalid_conversations_are_rejected(messages):
    with pytest.raises(ValueError):
        chat({"messages": messages}, object())


def test_local_model_cannot_load_accidentally(monkeypatch):
    monkeypatch.setenv("NOUGEN_CHAT_MODEL", "large-local-model")
    with pytest.raises(ValueError):
        chat({"messages": [{"role": "user", "content": "hi"}]}, object())


def test_model_directs_widget_then_synthesizes():
    from nougen_shards.chat_service import execute_tool
    class Client:
        calls = 0
        def chat(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "present_widget", "arguments": {"kind": "checklist", "title": "Launch", "items": ["Review", "Ship"]}}}]}}
            assert kwargs["messages"][-1]["role"] == "tool"
            return {"message": {"content": "Here is your checklist."}}
    result = chat({"messages": [{"role": "user", "content": "Make a launch checklist"}]}, Client())
    assert result["widgets"][0]["items"] == ["Review", "Ship"]
    assert result["receipts"] == [{"tool": "present_widget", "ok": True}]
    with pytest.raises(ValueError):
        execute_tool("exec", {"command": "arbitrary"})


@pytest.mark.parametrize("args", [{"kind": "html", "title": "x", "items": ["x"]}, {"kind": "steps", "title": "x", "items": ["x"] * 13}, {"kind": "checklist", "title": "x", "items": [None]}])
def test_malformed_widgets_rejected(args):
    from nougen_shards.chat_service import execute_tool
    with pytest.raises(ValueError):
        execute_tool("present_widget", args)


def test_unbounded_tool_loop_stops():
    class Client:
        calls = 0
        def chat(self, **kwargs):
            self.calls += 1
            return {"message": {"role": "assistant", "tool_calls": [{"function": {"name": "unknown", "arguments": {}}}]}}
    client = Client()
    with pytest.raises(RuntimeError):
        chat({"messages": [{"role": "user", "content": "hello"}]}, client)
    assert client.calls == 4


def test_credentials_are_redacted_before_cloud_and_before_display():
    from nougen_shards.credential_patterns import SHAPES
    secret = next(iter(SHAPES.values()))
    class Client:
        def chat(self, **kwargs):
            assert secret not in kwargs["messages"][-1]["content"]
            return {"message": {"content": "Do not display " + secret}}
    result = chat({"messages": [{"role": "user", "content": "Here is " + secret}]}, Client())
    assert secret not in result["text"]

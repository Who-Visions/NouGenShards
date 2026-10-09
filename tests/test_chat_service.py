from types import SimpleNamespace
import sys
import subprocess
import os
from pathlib import Path
import pytest
from nougen_shards.chat_service import GENERATION_OPTIONS, _is_dry_playful_reply, _is_formulaic_reasoning_reply, _is_playful_prompt, _is_repeated_reply, chat, discover_chat_model


def test_history_reaches_model_without_client_system_injection(monkeypatch):
    monkeypatch.setenv("NOUGEN_CHAT_MODEL", "gemma4:cloud")
    class Client:
        def chat(self, **kwargs):
            assert kwargs["messages"][1:] == history
            assert kwargs["stream"] is False
            assert kwargs["options"] == GENERATION_OPTIONS
            return SimpleNamespace(message=SimpleNamespace(content="Blue Lantern"))
    history = [{"role": "user", "content": "Blue Lantern"}, {"role": "assistant", "content": "Understood"}, {"role": "user", "content": "What name?"}]
    assert chat({"messages": history}, Client())["text"] == "Blue Lantern"


def test_chat_package_import_does_not_eagerly_load_memory_engine():
    code = (
        "import sys; import nougen_shards.chat_service; "
        "assert 'nougen_shards.core' not in sys.modules; "
        "assert 'nougen_shards.federation' not in sys.modules; "
        "assert 'nougen_shards.temporal_fabric' not in sys.modules; "
        "assert 'nougen_shards.cloudflare' not in sys.modules"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    subprocess.run([sys.executable, "-c", code], check=True, env=env)


def test_legacy_package_exports_remain_lazy_and_resolvable():
    code = (
        "from nougen_shards import capture, temporal_fabric; "
        "assert callable(capture); "
        "assert temporal_fabric.TemporalFabric"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    subprocess.run([sys.executable, "-c", code], check=True, env=env)


def test_live_chat_uses_model_reasoning_for_tool_selection(monkeypatch):
    import json
    import urllib.request

    monkeypatch.setenv("NOUGEN_CHAT_MODEL", "gemma4:cloud")
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return json.dumps({"message": {"content": "These approaches differ in their risk and timing."}}).encode()

    def fake_urlopen(request, timeout):
        calls.append(request)
        assert json.loads(request.data)["options"] == GENERATION_OPTIONS
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = chat({"messages": [{"role": "user", "content": "Compare two careful approaches to planning a large project."}]})
    assert result["text"] == "These approaches differ in their risk and timing."
    assert result["widgets"] == []
    assert len(calls) == 1


def test_chat_prompt_is_conversational_and_includes_selected_model(monkeypatch):
    monkeypatch.setenv("NOUGEN_CHAT_MODEL", "gemma4:e2b")

    class Client:
        def chat(self, **kwargs):
            system = kwargs["messages"][0]["content"]
            assert "Selected model identifier for this turn: gemma4:e2b" in system
            assert "canned introductions" in system
            assert "attentive, plainspoken collaborator" in system
            assert "Riff with the user" in system
            assert "don't explain your function, recast the joke as a request for product information" in system
            assert "Don't reveal private step-by-step chain-of-thought" in system
            assert "Do not copy or closely paraphrase earlier assistant replies" in system
            assert "one conversational, high-level sentence tied to the user's question" in system
            assert "Mention tools only when one was actually used this turn" in system
            assert "ALWAYS proactively call" not in system
            assert "Dave's high-caliber technical collaborator" not in system
            assert kwargs["options"] == GENERATION_OPTIONS
            return {"message": {"content": "I'm running gemma4:e2b."}}

    result = chat({"messages": [{"role": "user", "content": "Which model are you running?"}]}, Client())
    assert result["model"] == "gemma4:e2b"
    assert result["text"] == "I'm running gemma4:e2b."


def test_playful_chat_prefers_wittier_local_model_but_keeps_tool_lane(monkeypatch):
    import json
    import urllib.request

    monkeypatch.delenv("NOUGEN_CHAT_MODEL", raising=False)

    class Tags:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size):
            return json.dumps({"models": [{"name": "gemma4:e2b"}, {"name": "Yukiai:e4b"}]}).encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: Tags())
    assert _is_playful_prompt("Is NouGen sexy architecture?")
    assert discover_chat_model(playful=True) == "Yukiai:e4b"
    assert discover_chat_model(playful=False) == "gemma4:e2b"

    class Client:
        def chat(self, **kwargs):
            assert kwargs["model"] == "Yukiai:e4b"
            return {"message": {"content": "The memory grid has a little swagger, I'll give it that."}}

    response = chat({"messages": [{"role": "user", "content": "Is NouGen sexy architecture?"}]}, Client())
    assert response["model"] == "Yukiai:e4b"
    assert response["text"] == "The memory grid has a little swagger, I'll give it that."


def test_repeated_reply_is_rewritten_by_the_model(monkeypatch):
    monkeypatch.setenv("NOUGEN_CHAT_MODEL", "gemma4:e2b")
    earlier_reply = "I can help you work through the problem step by step and find a clear next move."
    history = [
        {"role": "user", "content": "Can you help me with this?"},
        {"role": "assistant", "content": earlier_reply},
        {"role": "user", "content": "I'm stuck on the same task. What should we do?"},
    ]

    class Client:
        calls = 0

        def chat(self, **kwargs):
            self.calls += 1
            assert kwargs["options"] == GENERATION_OPTIONS
            if self.calls == 1:
                return {"message": {"content": "I can help you work through the problem step by step and find a clear next move!"}}
            assert any("Your draft repeats an earlier assistant reply" in m.get("content", "") for m in kwargs["messages"])
            return {"message": {"content": "Let's look at the part that's blocking you first, then choose a next step."}}

    client = Client()
    result = chat({"messages": history}, client)
    assert client.calls == 2
    assert result["text"] == "Let's look at the part that's blocking you first, then choose a next step."


def test_repeated_reply_detector_catches_exact_and_close_echoes():
    original = "I can help you work through the problem step by step and find a clear next move."
    close_echo = "I can help you work through the problem step by step and find the next move."
    different = "Let's start with the part that feels hardest right now."
    assert _is_repeated_reply(original.upper(), [original])
    assert _is_repeated_reply(close_echo, [original])
    assert _is_repeated_reply(original, [original] + [f"Earlier answer {index}." for index in range(5)])
    assert not _is_repeated_reply(different, [original])


def test_formulaic_reasoning_detector_only_flags_process_reports():
    boilerplate = "I analyze your question, access memory, and formulate a coherent answer."
    natural = "I try to stay with what you're really asking and answer in the context of our conversation."
    assert _is_formulaic_reasoning_reply(boilerplate, "How do you reason?")
    assert _is_formulaic_reasoning_reply(
        "I arrive at answers by recognizing complex patterns in the information I have been trained on and predicting a response.",
        "How do you reason?",
    )
    assert not _is_formulaic_reasoning_reply(natural, "How do you reason?")
    assert _is_formulaic_reasoning_reply(
        "I figure out what you are asking by carefully looking at the words and context you provide.",
        "When you're answering me, what are you doing?",
    )
    assert _is_formulaic_reasoning_reply(
        "I process your requests by analyzing the words you use and the context of our conversation.",
        "I mean specifically when you're answering me, what are you doing?",
    )
    assert not _is_formulaic_reasoning_reply(boilerplate, "How do I fix my Python test?")


def test_playful_prompt_rejects_stock_disclaimer_and_rewrites_with_model(monkeypatch):
    monkeypatch.setenv("NOUGEN_CHAT_MODEL", "gemma4:e2b")
    dry = "I'm a large language model and don't have a body. I can tell you how NouGen works if you have questions."
    product_brochure = "I'm more focused on the memory hub than aesthetics. What part of the structure are you curious about?"
    long_riff = "A playful opening line. " + ("Then a long explanation of how the architecture works. " * 5)
    assert _is_dry_playful_reply(dry, "Is NouGen sexy architecture?")
    assert _is_dry_playful_reply(product_brochure, "Is NouGen sexy architecture?")
    assert _is_dry_playful_reply(long_riff, "Is NouGen sexy architecture?")
    assert _is_dry_playful_reply("It's all about making complex systems flow together smoothly.", "Is NouGen sexy architecture?")
    assert not _is_dry_playful_reply("Nine databases and a little swagger? I can see the appeal.", "Is NouGen sexy architecture?")

    class Client:
        calls = 0

        def chat(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {"message": {"content": dry}}
            assert "The user is playfully calling software architecture sexy" in kwargs["messages"][1]["content"]
            return {"message": {"content": "Nine databases and a little swagger? I can see the appeal."}}

    client = Client()
    result = chat({"messages": [{"role": "user", "content": "Is NouGen sexy architecture?"}]}, client)
    assert client.calls == 2
    assert result["text"] == "Nine databases and a little swagger? I can see the appeal."


def test_model_cannot_return_the_same_reply_after_rewrite(monkeypatch):
    monkeypatch.setenv("NOUGEN_CHAT_MODEL", "gemma4:e2b")
    repeated = "I can help you work through the problem step by step and find a clear next move."
    history = [
        {"role": "assistant", "content": repeated},
        {"role": "user", "content": "Can you help me move forward?"},
    ]

    class Client:
        calls = 0

        def chat(self, **kwargs):
            self.calls += 1
            return {"message": {"content": repeated}}

    client = Client()
    with pytest.raises(RuntimeError, match="repeated a recent reply"):
        chat({"messages": history}, client)
    assert client.calls == 4


def test_formulaic_reasoning_answer_is_rewritten_by_the_model(monkeypatch):
    monkeypatch.setenv("NOUGEN_CHAT_MODEL", "gemma4:e2b")
    history = [
        {"role": "user", "content": "How do you reason?"},
        {"role": "assistant", "content": "I reason by analyzing your question and context to give a clear answer."},
        {"role": "user", "content": "Explain how you approach a question like this."},
    ]

    class Client:
        calls = 0

        def chat(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {"message": {"content": "I analyze your request, use memory, and formulate a clear response."}}
            assert any("generic process boilerplate" in m.get("content", "") for m in kwargs["messages"])
            return {"message": {"content": "I try to stay with what you're really asking and answer in the context of our conversation."}}

    client = Client()
    result = chat({"messages": history}, client)
    assert client.calls == 2
    assert result["text"] == "I try to stay with what you're really asking and answer in the context of our conversation."


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


def test_model_receives_specific_calculator_repair_hint_and_retries(monkeypatch):
    monkeypatch.setenv("NOUGEN_CHAT_MODEL", "gemma4:cloud")

    class Client:
        calls = 0
        def chat(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "present_widget", "arguments": {
                    "kind": "calculator", "title": "Double", "inputs": [{"key": "x", "label": "X", "min": 0, "max": 10, "step": 1}],
                    "formula": {"op": "mul", "left": {"op": "input", "key": "x"}, "right": {"op": "const", "value": 2}}
                }}}]}}
            if self.calls == 2:
                hint = kwargs["messages"][-1]["content"]
                assert "numeric value" in hint
                return {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "present_widget", "arguments": {
                    "kind": "calculator", "title": "Double", "inputs": [{"key": "x", "label": "X", "value": 2, "min": 0, "max": 10, "step": 1}],
                    "formula": {"op": "mul", "left": {"op": "input", "key": "x"}, "right": {"op": "const", "value": 2}},
                    "resultLabel": "Double", "unit": "", "precision": 0
                }}}]}}
            return {"message": {"content": "The calculator is ready."}}

    result = chat({"messages": [{"role": "user", "content": "Make an editable calculator that doubles X."}]}, Client())
    assert len(result["widgets"]) == 1
    assert result["widgets"][0]["inputs"][0]["value"] == 2
    assert result["receipts"] == [{"tool": "present_widget", "ok": False}, {"tool": "present_widget", "ok": True}]


@pytest.mark.parametrize("args", [{"kind": "html", "title": "x", "items": ["x"]}, {"kind": "steps", "title": "x", "items": ["x"] * 13}, {"kind": "checklist", "title": "x", "items": [None]}])
def test_malformed_widgets_rejected(args):
    from nougen_shards.chat_service import execute_tool
    with pytest.raises(ValueError):
        execute_tool("present_widget", args)


def test_model_directs_safe_calculator_and_chart():
    from nougen_shards.chat_service import execute_tool, TOOLS
    from nougen_shards.chat_widget_ir import CHAT_WIDGET_IR_VERSION, PRESENT_WIDGET_PARAMETERS
    assert TOOLS[-1]["function"]["parameters"] == PRESENT_WIDGET_PARAMETERS
    formula_schema = PRESENT_WIDGET_PARAMETERS["properties"]["formula"]
    assert "input keys must match" in formula_schema["description"].lower()
    assert formula_schema["properties"]["op"]["enum"] == ["input", "const", "neg", "add", "sub", "mul", "div", "pow"]
    calc = execute_tool("present_widget", {"kind":"calculator","title":"Monthly payment","inputs":[{"key":"principal","label":"Loan amount","value":200000,"min":1000,"max":1000000,"step":1000,"unit":"$"},{"key":"rate","label":"Annual rate","value":0.06,"min":0,"max":0.2,"step":0.001}],"formula":{"op":"div","left":{"op":"mul","left":{"op":"input","key":"principal"},"right":{"op":"input","key":"rate"}},"right":{"op":"const","value":12}},"resultLabel":"Interest only","unit":"$ / month","precision":2})
    assert calc["contractVersion"] == CHAT_WIDGET_IR_VERSION and calc["kind"] == "calculator" and calc["formula"]["op"] == "div"
    chart = execute_tool("present_widget", {"kind":"chart","title":"Annual totals","chartType":"line","xLabel":"Year","yLabel":"Count","series":[{"label":"Actual","points":[{"x":"2024","y":4},{"x":"2025","y":6}]}]})
    assert chart["series"][0]["points"][1]["y"] == 6
    with pytest.raises(ValueError):
        execute_tool("present_widget", {"kind":"calculator","title":"Unsafe","inputs":[{"key":"x","label":"X","value":1,"min":0,"max":2,"step":1}],"formula":{"op":"exec","code":"x"}})
    with pytest.raises(ValueError):
        execute_tool("present_widget", {"kind":"chart","title":"Misaligned","chartType":"bar","xLabel":"X","yLabel":"Y","series":[{"label":"A","points":[{"x":"a","y":1},{"x":"b","y":2}]},{"label":"B","points":[{"x":"a","y":1},{"x":"c","y":2}]}]})


def test_model_selects_calculator_widget():
    class Client:
        calls = 0
        def chat(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {"message":{"role":"assistant","content":"","tool_calls":[{"function":{"name":"present_widget","arguments":{"kind":"calculator","title":"Double it","inputs":[{"key":"n","label":"Value","value":3,"min":0,"max":10,"step":1}],"formula":{"op":"mul","left":{"op":"input","key":"n"},"right":{"op":"const","value":2}},"resultLabel":"Result","unit":"","precision":0}}}]}}
            return {"message":{"content":"Change the value to explore the result."}}
    result=chat({"messages":[{"role":"user","content":"Make a what-if calculator"}]},Client())
    assert result["widgets"][0]["kind"] == "calculator"
    assert result["receipts"] == [{"tool":"present_widget","ok":True}]


def test_chat_widget_ir_generated_artifacts_are_current():
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "tools" / "compile_chat_widget_ir.py"), "--check"], cwd=root, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


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

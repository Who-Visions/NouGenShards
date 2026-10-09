from types import SimpleNamespace
import sys
import subprocess
import os
from pathlib import Path
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
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = chat({"messages": [{"role": "user", "content": "Compare two careful approaches to planning a large project."}]})
    assert result["text"] == "These approaches differ in their risk and timing."
    assert result["widgets"] == []
    assert len(calls) == 1


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

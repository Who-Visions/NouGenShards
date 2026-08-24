"""Rhea's bounded agent loop: exhausting rounds composes, it does not discard.

A deep archive sweep legitimately spends every round on tool calls; the fix
under test forces one compose-only pass so the gathered trace becomes a
best-effort answer instead of "(round limit hit before a final answer)".
"""
import rhea_noir


def test_round_limit_composes_from_tool_trace(monkeypatch):
    monkeypatch.setenv("NOUGEN_RHEA_MAX_ROUNDS", "2")
    calls = {"n": 0}

    def fake_chat(messages):
        calls["n"] += 1
        if calls["n"] <= 2:
            return '{"tool": "health"}', "test:brain"
        # Third call is the forced compose pass — no tools allowed.
        assert "ROUND LIMIT REACHED" in messages[-1]["content"]
        return '{"answer": "composed from trace"}', "test:brain"

    monkeypatch.setattr(rhea_noir, "_chat", fake_chat)
    monkeypatch.setattr(rhea_noir, "_run_tool", lambda call: {"ok": True})

    out = rhea_noir.ask("exhaustive seven-day sweep")
    assert out["answer"] == "composed from trace"
    assert out["note"] == "composed at round limit"
    assert out["tools_used"] == ["health", "health"]


def test_round_limit_placeholder_when_compose_fails(monkeypatch):
    monkeypatch.setenv("NOUGEN_RHEA_MAX_ROUNDS", "1")

    def fake_chat(messages):
        if any("ROUND LIMIT REACHED" in m["content"] for m in messages):
            raise RuntimeError("upstream down")
        return '{"tool": "health"}', "test:brain"

    monkeypatch.setattr(rhea_noir, "_chat", fake_chat)
    monkeypatch.setattr(rhea_noir, "_run_tool", lambda call: {"ok": True})

    out = rhea_noir.ask("sweep")
    assert out["answer"] == "(round limit hit before a final answer)"
    assert out["tools_used"] == ["health"]


def test_normal_answer_path_unchanged(monkeypatch):
    monkeypatch.setattr(
        rhea_noir, "_chat",
        lambda messages: ('{"answer": "direct"}', "test:brain"))
    out = rhea_noir.ask("hi")
    assert out["answer"] == "direct"
    assert "note" not in out

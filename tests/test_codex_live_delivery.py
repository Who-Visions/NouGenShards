"""Codex live delivery uses the supported queue surface, never a guessed socket protocol."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


TOOLS = Path(__file__).resolve().parent.parent / "tools"


@pytest.fixture()
def delivery(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_CC_SESSIONS", str(tmp_path / "claude-sessions.json"))
    monkeypatch.setenv("NOUGEN_CODEX_THREAD", "01a06ac6-8907-7d61-b012-ed8c084f5fd4")
    monkeypatch.setenv("NOUGEN_CODEX_CLI", str(tmp_path / "codex"))
    (tmp_path / "codex").write_text("stub", encoding="utf-8")
    sys.path.insert(0, str(TOOLS))
    sys.modules.pop("_agy_live_delivery", None)
    module = importlib.import_module("_agy_live_delivery")
    yield module
    sys.modules.pop("_agy_live_delivery", None)
    sys.path.remove(str(TOOLS))


def test_approved_message_uses_native_codex_queue(delivery, monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="Queued message q1", stderr="")

    monkeypatch.setattr(delivery.subprocess, "run", fake_run)
    result = delivery.deliver_to_codex_session("hello", "relay-test")

    assert result["delivered"] is True
    assert calls[0][0][:4] == [
        delivery.os.environ["NOUGEN_CODEX_CLI"], "queue", "--thread",
        "01a06ac6-8907-7d61-b012-ed8c084f5fd4",
    ]
    assert calls[0][0][4] == "--message"
    assert "hello" in calls[0][0][5]
    assert "shell" not in calls[0][1]


def test_missing_target_fails_closed_without_starting_codex(delivery, monkeypatch, tmp_path):
    monkeypatch.delenv("NOUGEN_CODEX_THREAD")
    monkeypatch.setenv("NOUGEN_CODEX_TARGET_FILE", str(tmp_path / "missing.json"))
    monkeypatch.setattr(delivery.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("ran Codex"))

    result = delivery.deliver_to_codex_session("hello", "relay-test")

    assert result == {
        "attempted": False,
        "delivered": False,
        "reason": "no Codex target configured",
    }


def test_relay_notice_never_includes_the_relay_body(delivery, monkeypatch):
    captured = []
    monkeypatch.setattr(delivery, "_queue_codex", lambda message: captured.append(message) or {})

    delivery.deliver_relay_notice("leg-1\nmalicious", "peer/name", "complete")

    assert "metadata only" in captured[0]
    assert "leg-1_malicious" in captured[0]
    assert "relay body is intentionally withheld" in captured[0]


def test_live_delivery_reports_codex_alongside_claude(delivery, monkeypatch):
    monkeypatch.setattr(
        delivery, "deliver_to_codex_session",
        lambda text, source: {"delivered": True, "text": text, "source": source})

    result = delivery.deliver_to_live_sessions("hello", "peer")

    assert result["codex"] == {"delivered": True, "text": "hello", "source": "peer"}

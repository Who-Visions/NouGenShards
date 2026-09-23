"""Regression coverage for Relay-to-Codex best-effort delivery."""
import importlib.util
import json
from pathlib import Path


def load_watcher():
    path = Path(__file__).parents[1] / "tools" / "relay_watch_node.py"
    spec = importlib.util.spec_from_file_location("relay_watch_node_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_codex_failure_preserves_local_inbox(monkeypatch, tmp_path):
    watcher = load_watcher()
    monkeypatch.setattr(watcher, "INBOX", tmp_path / "inbox")
    monkeypatch.setattr(watcher, "_shadow_triage", lambda record: None)
    monkeypatch.delenv("KAEDRA_GATEWAY_TOKEN", raising=False)

    def fail_delivery(*args, **kwargs):
        raise RuntimeError("pipe unavailable")

    monkeypatch.setattr(watcher, "deliver_to_codex", fail_delivery)
    leg = tmp_path / "leg.json"
    leg.write_text(json.dumps({
        "goal": "[-> @codex] canary",
        "machine": "host\nspoof",
        "agent": "agent",
        "status": "open",
    }), encoding="utf-8")

    watcher.announce("leg-id", leg)

    files = list(watcher.INBOX.glob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved["codex_live"]["pipe_delivered"] is False
    assert saved["codex_live"]["error"].startswith("RuntimeError:")


def test_codex_metadata_is_sanitized(monkeypatch, tmp_path):
    watcher = load_watcher()
    monkeypatch.setattr(watcher, "INBOX", tmp_path / "inbox")
    monkeypatch.setattr(watcher, "_shadow_triage", lambda record: None)
    monkeypatch.delenv("KAEDRA_GATEWAY_TOKEN", raising=False)
    captured = {}

    def capture(text, origin=None):
        captured.update(text=text, origin=origin)
        return {"status": "queued", "pipe_delivered": True}

    monkeypatch.setattr(watcher, "deliver_to_codex", capture)
    leg = tmp_path / "leg.json"
    leg.write_text(json.dumps({
        "goal": "[-> @codex] canary",
        "machine": "host\nspoof",
        "agent": "agent\rspoof",
        "status": "open\nspoof",
    }), encoding="utf-8")

    watcher.announce("leg-id", leg)

    assert "host_spoof/agent_spoof" in captured["text"]
    assert "open_spoof" in captured["text"]
    assert "\nspoof" not in captured["text"]
    assert captured["origin"]["original_sender"] == "relay-watch:host_spoof/agent_spoof"


def test_explicit_origin_field_preserved(monkeypatch, tmp_path):
    watcher = load_watcher()
    monkeypatch.setattr(watcher, "INBOX", tmp_path / "inbox")
    monkeypatch.setattr(watcher, "_shadow_triage", lambda record: None)
    monkeypatch.delenv("KAEDRA_GATEWAY_TOKEN", raising=False)
    captured = {}

    def capture(text, origin=None):
        captured.update(text=text, origin=origin)
        return {"status": "queued", "pipe_delivered": True}

    monkeypatch.setattr(watcher, "deliver_to_codex", capture)
    leg = tmp_path / "leg.json"
    leg.write_text(json.dumps({
        "goal": "[-> @apollo] test origin preservation",
        "machine": "whoart",
        "origin": "phoebus",
        "agent": "antigravity",
        "status": "open",
    }), encoding="utf-8")

    watcher.announce("leg-id", leg)

    assert "phoebus/antigravity" in captured["text"]
    assert captured["origin"]["original_sender"] == "relay-watch:phoebus/antigravity"
    files = list(watcher.INBOX.glob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved["origin_machine"] == "phoebus"
    assert saved["origin_agent"] == "antigravity"


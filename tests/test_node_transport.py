"""Tests for the portable node transport tools.

The receiver names an inbox file after a sender that arrived over the network,
so the sanitizer is a security boundary and gets the most attention here.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
BACKSLASH = chr(92)
NUL = chr(0)


def _load(name: str, monkeypatch, tmp_path: Path):
    """Import a tool module with its inbox and state pointed at a temp dir."""
    monkeypatch.setenv("NOUGEN_AGY_INBOX", str(tmp_path / "inbox"))
    monkeypatch.setenv("NOUGEN_MSG_STATE", str(tmp_path / "state" / "last.json"))
    monkeypatch.setenv("NOUGEN_RELAY_CURSOR", str(tmp_path / "state" / "cursor.json"))
    monkeypatch.setenv("NOUGEN_NODE_NAME", "testnode")
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def receiver(monkeypatch, tmp_path):
    return _load("nougenmsg_node", monkeypatch, tmp_path)


@pytest.fixture()
def watch(monkeypatch, tmp_path):
    return _load("relay_watch_node", monkeypatch, tmp_path)


@pytest.mark.parametrize("raw", [
    "../../etc/passwd",
    "a/b" + BACKSLASH + "c",
    "C:" + BACKSLASH + "Windows" + BACKSLASH + "system32",
    NUL + "evil",
    "..%2f..%2fetc",
    "sender name!@#$",
])
def test_sender_label_cannot_escape_the_inbox(receiver, raw):
    """A hostile sender never yields a path separator, drive letter, or NUL."""
    label = receiver.safe_sender(raw)
    assert not any(c in label for c in ("/", BACKSLASH, ":", NUL))
    assert label not in ("", ".", "..")
    assert len(label) <= receiver.SENDER_LABEL_CHARS


@pytest.mark.parametrize("raw", ["", None, "..", "...", "___", "!!!"])
def test_empty_or_stripped_sender_falls_back(receiver, raw):
    assert receiver.safe_sender(raw) == "unknown"


def test_ordinary_sender_survives_unchanged(receiver):
    assert receiver.safe_sender("claude-cli") == "claude-cli"
    assert receiver.safe_sender("relay-watch") == "relay-watch"


def test_long_sender_is_truncated(receiver):
    assert len(receiver.safe_sender("x" * 500)) == receiver.SENDER_LABEL_CHARS


def test_record_writes_inside_the_inbox(receiver):
    """Even with a traversal-shaped sender, the file lands in the inbox."""
    path = receiver.record({"text": "hello", "sender": "../../escape"})
    assert path.parent == receiver.INBOX
    assert json.loads(path.read_text(encoding="utf-8"))["text"] == "hello"
    assert json.loads(receiver.STATE.read_text(encoding="utf-8"))["text"] == "hello"


def test_default_bind_is_loopback(receiver):
    """A LAN bind is opt-in, so an unconfigured node is not exposed."""
    assert receiver.DEFAULT_BIND == "127.0.0.1"


def test_port_resolution_prefers_env(receiver, monkeypatch):
    monkeypatch.setenv("NOUGEN_AGY_MSG_PORT", "9001")
    assert receiver.resolve_port() == (9001, "env")
    monkeypatch.setenv("NOUGEN_AGY_MSG_PORT", "not-a-port")
    assert receiver.resolve_port() == (receiver.DEFAULT_PORT, "fallback")


def _registry(tmp_path: Path, *leg_ids: str) -> Path:
    root = tmp_path / "registry"
    (root / ".handoffs").mkdir(parents=True, exist_ok=True)
    for leg_id in leg_ids:
        (root / ".handoffs" / f"{leg_id}.json").write_text(
            json.dumps({"goal": "g", "machine": "m", "agent": "a", "status": "open"}),
            encoding="utf-8")
    return root


def test_watch_lists_legs_by_id(watch, tmp_path):
    root = _registry(tmp_path, "20260101T000000Z__m__a", "20260102T000000Z__m__a")
    assert set(watch.legs(root)) == {"20260101T000000Z__m__a", "20260102T000000Z__m__a"}


def test_watch_cursor_round_trips(watch, tmp_path):
    _registry(tmp_path)
    watch.save_seen({"one", "two"})
    assert watch.load_seen() == {"one", "two"}


def test_watch_announce_writes_an_inbox_message(watch, tmp_path):
    root = _registry(tmp_path, "20260101T000000Z__m__a")
    leg = root / ".handoffs" / "20260101T000000Z__m__a.json"
    watch.announce("20260101T000000Z__m__a", leg)
    written = list(watch.INBOX.glob("*.json"))
    assert len(written) == 1
    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert payload["leg_id"] == "20260101T000000Z__m__a"
    assert "not permission" in payload["text"]


def test_watch_interval_prefers_env(watch, monkeypatch):
    monkeypatch.setenv("NOUGEN_RELAY_WATCH_SECS", "15")
    assert watch.resolve_interval() == (15, "env")
    monkeypatch.setenv("NOUGEN_RELAY_WATCH_SECS", "0")
    assert watch.resolve_interval() == (watch.DEFAULT_INTERVAL_SECS, "fallback")


def test_inbox_path_refuses_an_escape(receiver):
    """The containment check is independent of the sender sanitizer."""
    with pytest.raises(ValueError):
        receiver.inbox_path(".." + "/" + "escaped.json")
    with pytest.raises(ValueError):
        receiver.inbox_path("nested/child.json")


def test_inbox_path_accepts_a_plain_name(receiver):
    resolved = receiver.inbox_path("msg_1_claude-cli.json")
    assert resolved.parent == receiver.INBOX.resolve()

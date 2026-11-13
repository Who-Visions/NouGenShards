"""Idempotent delivery on the :8766 bus: the same event sent twice is stored once.

The key comes from the event (sender, target, thread, text) or from a sender-supplied
message_id, is claimed with a set-if-absent marker, and a repeat is answered with the
original delivery instead of a second inbox file. A fresh random key per attempt is what
used to let a retry look like a new message.
"""
from __future__ import annotations

import importlib
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

TOKEN = "idem-test-token"
PORT = 8796
AUTH = {"Content-Type": "application/json", "X-NGS-Token": TOKEN}


@pytest.fixture()
def server(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_AGY_MSG_TOKEN", TOKEN)
    monkeypatch.setenv("NOUGEN_AGY_MSG_AUTH", "required")
    monkeypatch.setenv("NOUGEN_AGY_INBOX", str(tmp_path / "inbox"))
    monkeypatch.setenv("NOUGEN_MSG_STATE", str(tmp_path / "state.json"))
    for name in [m for m in sys.modules if m.startswith(("nougenmsg_node", "_agy_live"))]:
        del sys.modules[name]
    node = importlib.import_module("nougenmsg_node")
    srv = node.ThreadingHTTPServer(("127.0.0.1", PORT), node.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.4)
    yield node, tmp_path / "inbox"
    srv.shutdown()


def _req(path, headers=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request("http://127.0.0.1:{}{}".format(PORT, path), data=data,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def _send(**extra):
    body = {"text": "leg 20261021T040416Z is open", "sender": "relay-watch", "target": "nobody"}
    body.update(extra)
    return _req("/msg", AUTH, body)


def _inbox_files(inbox):
    return sorted(p.name for p in inbox.glob("msg_*.json"))


def test_same_message_twice_is_stored_once(server):
    _, inbox = server
    code1, first = _send()
    code2, second = _send()
    assert code1 == code2 == 200
    assert first["delivered"] is True and first["duplicate"] is False
    assert second["delivered"] is True and second["duplicate"] is True
    assert second["message_id"] == first["message_id"]
    assert second["file"] == first["file"]
    assert len(_inbox_files(inbox)) == 1


def test_receipt_for_the_key_still_resolves_after_a_repeat(server):
    _, first = _send()
    _send()
    code, receipt = _req(first["receipt"], AUTH)
    assert code == 200
    assert receipt["state"] == "unread"


def test_different_text_is_a_different_event(server):
    _, inbox = server
    _send(text="one")
    _, second = _send(text="two")
    assert second["duplicate"] is False
    assert len(_inbox_files(inbox)) == 2


def test_different_sender_is_a_different_event(server):
    _, inbox = server
    _send(sender="a-lane")
    _, second = _send(sender="b-lane")
    assert second["duplicate"] is False
    assert len(_inbox_files(inbox)) == 2


def test_sender_supplied_id_dedupes_even_when_text_changes(server):
    _, inbox = server
    _send(message_id="evt-0001-abcd", text="first wording")
    _, second = _send(message_id="evt-0001-abcd", text="second wording")
    assert second["duplicate"] is True
    assert second["message_id"] == "evt-0001-abcd"
    assert len(_inbox_files(inbox)) == 1


def test_allow_duplicate_lets_a_deliberate_repeat_through(server):
    _, inbox = server
    _send(allow_duplicate=True)
    _, second = _send(allow_duplicate=True)
    assert second["duplicate"] is False
    assert len(_inbox_files(inbox)) == 2


def test_an_expired_key_delivers_again(server):
    node, inbox = server
    _send()
    node.DEDUP_TTL_S = 0.0
    time.sleep(0.05)
    _, again = _send()
    assert again["duplicate"] is False
    assert len(_inbox_files(inbox)) == 2


def test_concurrent_copies_deliver_exactly_once(server):
    _, inbox = server
    results = []

    def go():
        # A refused or dropped connection under burst load is retried, as a real sender
        # would; the retry is safe only because delivery is idempotent.
        for _ in range(10):
            try:
                results.append(_send(text="burst")[1])
                return
            except (ConnectionError, urllib.error.URLError, OSError):
                time.sleep(0.25)

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 8
    assert sum(1 for r in results if r["duplicate"] is False) == 1
    assert len(_inbox_files(inbox)) == 1


def test_no_partial_files_are_left_in_the_inbox(server):
    _, inbox = server
    _send()
    assert not list(inbox.glob(".*.tmp"))
    assert not list(inbox.glob("*.tmp"))


def test_derived_key_is_a_valid_message_id_and_stable(server):
    node, _ = server
    msg = {"sender": "s", "target": "t", "type": "live_message", "text": "same"}
    assert node.derive_message_key(dict(msg)) == node.derive_message_key(dict(msg))
    assert node.MESSAGE_ID_RE.match(node.derive_message_key(dict(msg)))
    assert node.derive_message_key(dict(msg, text="other")) != node.derive_message_key(dict(msg))

"""HTTP bus parity with cc-msg: every send gets an id, a read receipt, a reply thread.

cc-msg senders get a message id back and can address a reply; the :8766 bus
returned only {"delivered": true}. Receipts are OBSERVED from where the file
is, because since the auth latch (2026-09-23) consumers read inbox files and
archive them instead of draining /pop.
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

TOKEN = "receipt-test-token"
PORT = 8795
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
    yield node
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
    return _req("/msg", AUTH, {"text": "hello", "sender": "probe", "target": "nobody", **extra})


def test_send_returns_message_id_and_receipt_path(server):
    code, body = _send()
    assert code == 200
    mid = body["message_id"]
    assert server.MESSAGE_ID_RE.match(mid)
    assert body["receipt"] == "/msg/{}".format(mid)
    assert "_{}_".format(mid) in body["file"] and body["file"].endswith("_probe.json")


def test_receipt_tracks_unread_then_read(server):
    _, body = _send()
    mid = body["message_id"]
    assert _req("/msg/" + mid, AUTH)[1]["state"] == "unread"
    inbox = server.INBOX
    (inbox / "archive").mkdir(exist_ok=True)
    (inbox / body["file"]).rename(inbox / "archive" / body["file"])
    assert _req("/msg/" + mid, AUTH)[1]["state"] == "read"


def test_processed_suffix_counts_as_read(server):
    _, body = _send()
    f = server.INBOX / body["file"]
    f.rename(f.with_name(f.name + ".processed"))
    assert _req("/msg/" + body["message_id"], AUTH)[1]["state"] == "read"


def test_reply_threads_and_safe_sender_id_is_kept(server):
    _, first = _send(message_id="orig-abc123")
    assert first["message_id"] == "orig-abc123"
    _, reply = _send(in_reply_to="orig-abc123")
    assert reply["in_reply_to"] == "orig-abc123"
    assert reply["message_id"] != "orig-abc123"


def test_unsafe_sender_id_is_replaced_not_trusted_into_a_path(server):
    _, body = _send(message_id="../../evil")
    assert body["message_id"] != "../../evil" and ".." not in body["file"]


def test_receipts_need_auth_and_unknown_is_honest(server):
    _, body = _send()
    assert _req("/msg/" + body["message_id"])[0] == 401
    assert _req("/msg/nosuchid123", AUTH)[1]["state"] == "unknown"

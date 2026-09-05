"""GET /pop must not be an unauthenticated read-and-destroy.

Found on a live LAN-reachable node: with auth fully working on POST, an
unauthenticated GET /pop returned every queued message AND emptied the queue.
One request, and an attacker both steals fleet traffic and deletes it from the
recipient, who never learns it existed.

The HTTP verb is not the security boundary. What the handler DOES is.
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

TOKEN = "pop-test-token"
PORT = 8794


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


def _req(path, headers=None, data=None):
    req = urllib.request.Request("http://127.0.0.1:{}{}".format(PORT, path),
                                 data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def _post(text):
    return _req("/msg", {"Content-Type": "application/json", "X-NGS-Token": TOKEN},
                json.dumps({"text": text, "sender": "probe", "target": "nobody"}).encode())


def test_unauthenticated_pop_is_refused(server):
    """THE VULNERABILITY: steal and delete in one unauthenticated request."""
    _post("secret one")
    _post("secret two")
    assert _req("/status")[1]["pending_messages"] == 2

    status, body = _req("/pop")                      # no token
    assert status == 401, "unauthenticated /pop must be refused"
    assert not body.get("messages"), "no message bodies may leak"

    # and crucially the queue must be INTACT: a refused drain must not drain
    assert _req("/status")[1]["pending_messages"] == 2


def test_wrong_token_cannot_pop(server):
    _post("secret three")
    assert _req("/pop", {"X-NGS-Token": "wrong"})[0] == 401
    assert _req("/status")[1]["pending_messages"] >= 1


def test_authorized_pop_still_works(server):
    """The guard must not break the legitimate drain."""
    _post("legitimate")
    status, body = _req("/pop", {"X-NGS-Token": TOKEN})
    assert status == 200 and body["count"] >= 1
    assert _req("/status")[1]["pending_messages"] == 0


def test_liveness_probes_stay_open(server):
    """/health and /status are deliberately unauthenticated: probes need them."""
    assert _req("/health")[0] == 200
    assert _req("/status")[0] == 200

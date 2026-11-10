"""POST /msg answers once the inbox file is written; the slow gate runs afterwards.

The Kaedra gate is a local model call. On a CPU-only node one verdict outlasts a
sender's 10 s peer timeout, so answering only after it made authenticated sends look
failed (fleet leg 20261110T054609Z). The verdict is now reported on the receipt.
"""
import importlib.util
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"


def _load_node(monkeypatch, tmp_path, token="t0k"):
    monkeypatch.setenv("NOUGEN_AGY_INBOX", str(tmp_path / "inbox"))
    monkeypatch.setenv("NOUGEN_AGY_MSG_TOKEN", token)
    sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location("nougenmsg_node_ack_fast_t", TOOLS / "nougenmsg_node.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _serve(node):
    server = node.BoundedThreadingHTTPServer(("127.0.0.1", 0), node.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def _call(port, method, path, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request("http://127.0.0.1:{}{}".format(port, path), data=data, method=method,
                                 headers={"X-NGS-Token": token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def test_reply_does_not_wait_for_the_gate_and_the_receipt_reports_it(monkeypatch, tmp_path):
    node = _load_node(monkeypatch, tmp_path)
    release = threading.Event()
    calls = []

    def slow_gate(text, sender, message_id=None, origin="peer", origin_proof=None):
        calls.append((text, sender, message_id))
        release.wait(5)
        return {"attempted": True, "kaedra_approved": False, "reason_code": "test"}

    monkeypatch.setattr(node, "gate_and_deliver", slow_gate)
    server, port = _serve(node)
    try:
        started = time.monotonic()
        reply = _call(port, "POST", "/msg", "t0k", {"text": "hello phoebus", "sender": "blade", "message_id": "abc123"})
        assert time.monotonic() - started < 2, "the reply waited for the gate"
        assert reply["delivered"] is True
        assert reply["elevated"] == {"state": "pending", "attempted": True}
        assert list((tmp_path / "inbox").glob("msg_*abc123*.json")), "inbox file written before the reply"
        assert _call(port, "GET", "/msg/abc123", "t0k")["elevated"]["state"] == "pending"

        release.set()
        for _ in range(100):
            receipt = _call(port, "GET", "/msg/abc123", "t0k")
            if receipt["elevated"]["state"] == "done":
                break
            time.sleep(0.05)
        assert receipt["state"] == "unread"
        assert receipt["elevated"]["kaedra_approved"] is False
        assert receipt["elevated"]["wake"]["attempted"] is False  # unapproved: never woken
        assert calls == [("hello phoebus", "blade", "abc123")]
    finally:
        release.set()
        server.shutdown()


def test_a_gate_that_raises_is_reported_and_the_worker_keeps_going(monkeypatch, tmp_path):
    node = _load_node(monkeypatch, tmp_path)
    seen = []

    def gate(text, sender, **kw):
        seen.append(text)
        if text == "boom":
            raise RuntimeError("kaedra down")
        return {"attempted": True, "kaedra_approved": False}

    monkeypatch.setattr(node, "gate_and_deliver", gate)
    server, port = _serve(node)
    try:
        _call(port, "POST", "/msg", "t0k", {"text": "boom", "message_id": "first1"})
        _call(port, "POST", "/msg", "t0k", {"text": "fine", "message_id": "second"})
        for _ in range(100):
            a = _call(port, "GET", "/msg/first1", "t0k")["elevated"]
            b = _call(port, "GET", "/msg/second", "t0k")["elevated"]
            if a["state"] != "pending" and b["state"] != "pending":
                break
            time.sleep(0.05)
        assert a["state"] == "error" and "kaedra down" in a["error"]
        assert b["state"] == "done"
        assert seen == ["boom", "fine"]  # one worker, in arrival order
    finally:
        server.shutdown()


def test_a_full_queue_skips_elevation_but_still_delivers_to_the_inbox(monkeypatch, tmp_path):
    node = _load_node(monkeypatch, tmp_path)
    block = threading.Event()
    monkeypatch.setattr(node, "gate_and_deliver", lambda *a, **k: (block.wait(5), {"attempted": True})[1])
    monkeypatch.setattr(node, "_ELEVATED", node.queue.Queue(maxsize=1))
    server, port = _serve(node)
    try:
        _call(port, "POST", "/msg", "t0k", {"text": "one", "message_id": "q00001"})  # taken by the worker
        for _ in range(100):
            if node._ELEVATED.empty():
                break
            time.sleep(0.02)
        _call(port, "POST", "/msg", "t0k", {"text": "two", "message_id": "q00002"})  # waits in the queue
        third = _call(port, "POST", "/msg", "t0k", {"text": "three", "message_id": "q00003"})
        assert third["delivered"] is True
        assert third["elevated"]["state"] == "skipped"
        assert list((tmp_path / "inbox").glob("msg_*q00003*.json"))
    finally:
        block.set()
        server.shutdown()


def test_without_a_token_nothing_is_elevated(monkeypatch, tmp_path):
    node = _load_node(monkeypatch, tmp_path, token="")
    monkeypatch.setattr(node, "gate_and_deliver", lambda *a, **k: (_ for _ in ()).throw(AssertionError("gated")))
    server, port = _serve(node)
    try:
        reply = _call(port, "POST", "/msg", "", {"text": "open node"})
        assert reply["elevated"] == {"attempted": False}
    finally:
        server.shutdown()

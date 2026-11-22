"""Any-to-any NouGenMsg friction fixes (Nov 22 2026).

- the node's nougenmsg tool reports what happened, not "delivered" for a queued
  or failed send;
- Codex sees recent lane-wide drops (the node's fallback inbox writes no thread);
- local senders carry the /msg token so a latched node does not answer 401.
"""
import importlib.util
import json
import time
from pathlib import Path

from nougen_shards import agy_msg
from nougen_shards.nougenmsg import delivery_status

ROOT = Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_delivery_status_is_honest():
    assert delivery_status({"delivered": False, "status": "not_resolvable"}) == "not_resolvable"
    assert delivery_status({"results": {"phoebus/codex": "ok"}}) == "delivered"
    assert delivery_status({"results": {"blade": {"queued": True, "via": "ssh"}}}) == "queued"
    assert delivery_status({"results": {"a": "ok", "b": "Error: ssh refused"}}) == "partial"
    assert delivery_status({"results": {"b": "Error: ssh refused"}}) == "failed"
    assert delivery_status({"results": {}}) == "failed"
    assert delivery_status(None) == "failed"


def test_node_tool_uses_delivery_status():
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    body = src[src.index("def nougenmsg(message: str"):]
    body = body[: body.index("\ndef ", 10)]
    assert '"status": delivery_status(res)' in body
    assert '"status": "delivered"' not in body


def test_codex_hook_shows_recent_lane_wide_drops(tmp_path, monkeypatch):
    hook = _load("codex_hook", "tools/eot_hooks/codex_nougen_lifecycle.py")
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    monkeypatch.setattr(hook, "CODEX_INBOXES", [inbox])
    monkeypatch.setattr(hook, "CODEX_EOT_CURSOR", tmp_path / "state" / "cursor.json")
    now = time.time()
    (inbox / "ping_1.json").write_text(json.dumps(
        {"message_id": "m1", "target": "codex", "text": "pair test from antigravity", "timestamp": now}))
    (inbox / "ping_0.json").write_text(json.dumps(
        {"message_id": "m0", "target": "codex", "text": "old backlog", "timestamp": now - 86400}))
    (inbox / "ping_2.json").write_text(json.dumps(
        {"message_id": "m2", "thread": "other-thread", "text": "not mine", "timestamp": now}))
    (inbox / "ping_3.json").write_text(json.dumps(
        {"message_id": "m3", "thread": "t-1", "text": "mine", "timestamp": now}))
    seen = hook.unread_codex_inbox(thread_id="t-1")
    joined = " ".join(seen)
    assert "pair test from antigravity" in joined and "mine" in joined
    assert "old backlog" not in joined and "not mine" not in joined
    assert hook.unread_codex_inbox(thread_id="t-1") == []  # shown once per thread


def test_local_senders_carry_the_msg_token(monkeypatch):
    monkeypatch.setenv("NOUGEN_AGY_MSG_TOKEN", "tok-123")
    assert agy_msg.msg_headers()["X-NGS-Token"] == "tok-123"
    assert "X-NGS-Token" not in agy_msg.msg_headers(token="")
    cc = _load("cc_msg_mod", "tools/cc_msg.py")
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(req, timeout):
        seen.update({k.lower(): v for k, v in req.header_items()})
        return Resp()

    monkeypatch.setattr(cc.urllib.request, "urlopen", fake_urlopen)
    assert cc.send_http("127.0.0.1", 8766, {"text": "x"}) == {"ok": True}
    assert seen["x-ngs-token"] == "tok-123"

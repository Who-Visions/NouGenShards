"""context_call: the NouGen context call every prompt runs (GM order 2026-11-22).

Invariants:
- every call recalls, inside one hard wall, and writes a receipt;
- the fleet gateway answers when the local node is down or absent;
- a refused node is diagnosed as node_down and restarted through the box's
  supervisor, detached, and the next call verifies the restart;
- a slow node is only refreshed after repeated misses;
- a blocker a hook cannot fix reaches the agent with the fix and the GM order;
- relay legs and inbox pings are shown once per session, lane legs flagged;
- identity is resolved at run time, never pinned.
"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nougen_shards import agent_hooks, context_call as cc, core, recall_hook  # noqa: E402


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_NODE", "0")
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path / "vault")
    monkeypatch.setenv("NOUGEN_QUERY_EMBED", "0")
    monkeypatch.setenv("NOUGEN_EMBED_CAPTURE_TIMEOUT_S", "0.2")
    monkeypatch.setenv("NOUGEN_RECON_SWEEP_TRIGGER", "never")
    monkeypatch.setenv("NOUGEN_LANE", "tester-lane")
    monkeypatch.setenv("NOUGEN_NODE_NAME", "tester-box")
    monkeypatch.setenv("NOUGEN_RELAY_CHECKOUT", str(tmp_path / "no-relay"))
    monkeypatch.setenv("NOUGEN_INBOX_DIR", str(tmp_path / "inbox"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("NGS_NODE_TOKEN", "test-token")
    return tmp_path


def _receipts(tmp: Path) -> list:
    path = Path(cc.state_dir()) / "receipts.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


# ------------------------------------------------------------- gateway lane

class _Search(BaseHTTPRequestHandler):
    hits: list = []
    seen: list = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).seen.append({"token": self.headers.get("X-NGS-Token"), "ua": self.headers.get("User-Agent"),
                                "path": self.path, "query": body.get("query")})
        data = json.dumps({"results": type(self).hits}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_a):
        pass


@pytest.fixture
def gateway(monkeypatch):
    _Search.hits = [{"id": 42, "_db_index": 5, "title": "gateway hit", "content": "from the fleet"}]
    _Search.seen = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Search)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_GATEWAY", "1")
    monkeypatch.setenv("NOUGEN_FLEET_GATEWAY_URL", url)
    monkeypatch.setenv("SHARD_GATEWAY_TOKEN", "gw-token")
    yield url
    srv.shutdown()


def test_gateway_answers_a_box_with_no_local_node(box, gateway):
    r = recall_hook.recall_hook("what did the fleet decide", budget_ms=2000)
    assert r["tier"] == "gateway" and not r["partial"], r
    assert r["shards"][0]["ref"] == "42@db5"
    seen = _Search.seen[0]
    assert seen["path"] == "/search" and seen["token"] == "gw-token"
    assert "Python-urllib" not in (seen["ua"] or "")  # Cloudflare 403s the default UA


def test_local_node_wins_over_the_gateway(box, gateway, monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_NODE", "1")
    monkeypatch.setattr(recall_hook, "_node_search",
                        lambda q, limit, timeout_s, token=None: [{"id": 7, "_db_index": 1, "title": "local"}])
    r = recall_hook.recall_hook("local first", budget_ms=2000)
    assert r["tier"] == "node" and r["shards"][0]["ref"] == "7@db1"


def test_gateway_answers_when_local_node_is_down(box, gateway, monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_NODE", "1")

    def refused(*_a, **_k):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(recall_hook, "_node_search", refused)
    r = recall_hook.recall_hook("node down gateway up", budget_ms=2000)
    assert r["tier"] == "gateway" and "node" in r["errors"]


def test_gateway_never_points_back_at_the_local_node(box, monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_GATEWAY", "1")
    monkeypatch.setenv("NOUGEN_FLEET_GATEWAY_URL", "http://127.0.0.1:4444/")
    monkeypatch.setenv("NOUGEN_NODE_URL", "http://127.0.0.1:4444")
    assert recall_hook._gateway_url() is None  # pylint: disable=protected-access


# ------------------------------------------------------- diagnose + repair

def _refused_node(monkeypatch, port: int):
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_NODE", "1")
    monkeypatch.setenv("NOUGEN_NODE_URL", f"http://127.0.0.1:{port}")

    def refused(*_a, **_k):
        raise OSError("<urlopen error [Errno 111] Connection refused>")

    monkeypatch.setattr(recall_hook, "_node_search", refused)


def _free_port() -> int:
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_refused_node_is_restarted_and_the_next_call_verifies_it(box, monkeypatch):
    port = _free_port()
    _refused_node(monkeypatch, port)
    flag = box / "repaired.flag"
    monkeypatch.setenv("NOUGEN_CONTEXT_CALL_REPAIR", "1")
    monkeypatch.setenv("NOUGEN_NODE_REPAIR_CMD",
                       f'"{sys.executable}" -c "open(r\'{flag}\', \'w\').write(\'up\')"')
    call = cc.context_call("why is recall empty", session_id="s1", budget=1500)
    kinds = {b["kind"] for b in call["blockers"]}
    assert "node_down" in kinds, call["blockers"]
    started = [r for r in call["repairs"] if r["action"] == "started"]
    assert started and started[0]["kind"] == "node_down"
    block = cc.format_block(call)
    assert "BLOCKER node_down" in block and "auto-repair started" in block
    for _ in range(50):  # the repair runs detached
        if flag.exists():
            break
        time.sleep(0.1)
    assert flag.read_text() == "up"

    # Cooldown: a second refused call does not restart again.
    again = cc.context_call("still empty", session_id="s1", budget=1500)
    assert not [r for r in again["repairs"] if r["action"] == "started" and r["kind"] == "node_down"]

    # The node comes back: the next call says the repair took.
    monkeypatch.setattr(recall_hook, "_node_search",
                        lambda q, limit, timeout_s, token=None: [{"id": 1, "_db_index": 1, "title": "back"}])
    ok = cc.context_call("is it back", session_id="s1", budget=1500)
    assert ok["verified"] and ok["verified"]["verified"] is True
    assert "REPAIRED: node_down" in cc.format_block(ok)
    rows = _receipts(box)
    assert len(rows) == 3 and rows[0]["blockers"][0]["kind"] == "node_down" and rows[2]["tier"] == "node"


def test_slow_node_is_refreshed_only_after_repeated_misses(box, monkeypatch):
    import socket
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    port = listener.getsockname()[1]
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_NODE", "1")
    monkeypatch.setenv("NOUGEN_NODE_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setattr(recall_hook, "_node_search", lambda *a, **k: time.sleep(3) or [])
    monkeypatch.setenv("NOUGEN_CONTEXT_CALL_REPAIR", "1")
    monkeypatch.setenv("NOUGEN_CONTEXT_CALL_SLOW_STRIKES", "2")
    monkeypatch.setenv("NOUGEN_NODE_REPAIR_CMD", f'"{sys.executable}" -c "pass"')
    try:
        first = cc.context_call("slow one", session_id="s2", budget=600)
        assert first["elapsed_ms"] < 2000, first["elapsed_ms"]  # the wall holds
        assert any(b["kind"] == "node_slow" for b in first["blockers"])
        assert first["repairs"][0]["action"] == "watching"
        second = cc.context_call("slow two", session_id="s2", budget=600)
        assert any(r["action"] == "started" and r["kind"] == "node_slow" for r in second["repairs"])
    finally:
        listener.close()


def test_missing_token_is_handed_to_the_agent_with_the_fix(box, monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_NODE", "1")
    monkeypatch.delenv("NGS_NODE_TOKEN", raising=False)
    monkeypatch.setattr(recall_hook, "_node_token", lambda: None)
    monkeypatch.setattr(recall_hook, "_node_search",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no NGS_NODE_TOKEN")))
    call = cc.context_call("anything", session_id="s3", budget=1500)
    block = cc.format_block(call)
    assert any(b["kind"] == "node_token_missing" and not b["repairable"] for b in call["blockers"])
    assert "keymaker" in block
    assert "GM order: a recall timeout is a blocker" in block


def test_healthy_call_names_no_blocker(box, monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_NODE", "1")
    monkeypatch.setattr(recall_hook, "_node_search",
                        lambda q, limit, timeout_s, token=None: [{"id": 3, "_db_index": 2, "title": "ok"}])
    call = cc.context_call("all good", session_id="s4", budget=1500)
    assert call["blockers"] == [] and "BLOCKER" not in cc.format_block(call)
    assert call["identity"] == {"lane": "tester-lane", "node": "tester-box"}


# --------------------------------------------------------- relay + inbox

def test_relay_legs_and_inbox_show_once_per_session(box, monkeypatch):
    checkout = box / "relay"
    (checkout / ".handoffs").mkdir(parents=True)
    (checkout / ".handoffs" / "20261122T010000Z__a.json").write_text(json.dumps(
        {"goal": "general cleanup", "status": "open", "created_utc": "2026-11-22T01:00:00Z"}))
    (checkout / ".handoffs" / "20261122T020000Z__b.json").write_text(json.dumps(
        {"goal": "fix recall for tester-lane", "status": "open", "created_utc": "2026-11-22T02:00:00Z"}))
    (checkout / ".handoffs" / "20261122T030000Z__c.json").write_text(json.dumps(
        {"goal": "done already", "status": "closed"}))
    monkeypatch.setenv("NOUGEN_RELAY_CHECKOUT", str(checkout))
    inbox = box / "inbox"
    inbox.mkdir()
    (inbox / "m1.json").write_text(json.dumps({"sender": "peer-lane", "message": "roll call at noon"}))

    first = cc.context_call("hello", session_id="s5", budget=1500)
    local = first["local"]
    assert local["legs_open"] == 2 and local["legs_for_lane"] == 1
    assert local["legs"][0]["mine"] is True and "tester-lane" in local["legs"][0]["goal"]
    assert local["inbox"][0]["text"] == "roll call at noon"
    block = cc.format_block(first)
    assert "<-- YOUR LANE" in block and "roll call at noon" in block

    second = cc.context_call("again", session_id="s5", budget=1500)
    assert second["local"]["legs"] == [] and second["local"]["inbox"] == []
    assert "nothing new since your last prompt" in cc.format_block(second)


# ----------------------------------------------------------------- hook

def test_prompt_hook_runs_the_context_call(box, monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_NODE", "1")
    monkeypatch.setattr(recall_hook, "_node_search",
                        lambda q, limit, timeout_s, token=None: [{"id": 9, "_db_index": 4, "title": "hooked"}])
    out = json.loads(agent_hooks.run("prompt", json.dumps({"prompt": "what changed", "session_id": "s6"})))
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "[NouGen context call cc-" in ctx and "9@db4" in ctx
    assert _receipts(box)[-1]["shards"] == ["9@db4"]


def test_kill_switch_falls_back_to_plain_recall(box, monkeypatch):
    monkeypatch.setenv("NOUGEN_CONTEXT_CALL", "0")
    out = json.loads(agent_hooks.run("prompt", json.dumps({"prompt": "plain recall please"})))
    assert "[NouGen context call" not in out["hookSpecificOutput"]["additionalContext"]


def test_prompt_installs_on_the_fast_path():
    planned = agent_hooks.plan_settings({}, "/x/python")
    cmd = planned["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert agent_hooks.FAST_SIGNATURE in cmd and cmd.endswith(" prompt")

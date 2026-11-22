"""Wire v2 on the msgs node: adapters, the HTTP service, and the node's /wire routes."""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

from nougen_shards.wire import Hub, WireStore, make
from nougen_shards.wire import adapters as A
from nougen_shards.wire.service import WireService

TOOLS = Path(__file__).resolve().parents[1] / "tools"
KEY = b"k"


class FakePinger:
    def __init__(self, **results):
        self.results, self.calls = results, []

    def _hit(self, name, *a, **kw):
        self.calls.append((name, a, kw))
        return self.results.get(name, {})

    def ping_claude(self, prompt, origin=None, target_session=None):
        return self._hit("claude", prompt, origin=origin, target_session=target_session)

    def ping_antigravity(self, prompt, origin=None):
        return self._hit("antigravity", prompt, origin=origin)

    def ping_codex(self, prompt, origin=None):
        return self._hit("codex", prompt, origin=origin)

    def ping_ollama(self, prompt, node="local", model=None, origin=None):
        return self._hit("ollama", prompt, node=node, model=model, origin=origin)

    def ping_openrouter(self, prompt, model=None, origin=None):
        return self._hit("openrouter", prompt, model=model, origin=origin)


# -- adapters ----------------------------------------------------------------
def test_claude_socket_write_is_pushed_never_verified_and_pins_the_session():
    p = FakePinger(claude={"delivered": [{"session_id": "4936"}], "inbox_file": "x.json"})
    env = make("codex", "claude-code/4936@phoebus", "hi")
    res = A.build(p)["claude-code"](env, "TURN")
    assert res["pushed"] and not res["verified"]
    name, args, kw = p.calls[0]
    assert args[0] == "TURN" and kw["target_session"] == "4936"
    assert kw["origin"]["wire_id"] == env["id"]


def test_antigravity_needs_its_pipe_ack_to_be_verified():
    acked = A.build(FakePinger(antigravity={"pipe_delivered": True, "files": ["a"]}))["antigravity"]
    dropped = A.build(FakePinger(antigravity={"pipe_delivered": False, "files": ["a"]}))["antigravity"]
    env = make("codex", "antigravity", "hi")
    assert acked(env, "t")["verified"] is True
    r = dropped(env, "t")
    assert r["pushed"] is True and r["verified"] is False


def test_codex_nothing_reached_is_not_pushed():
    res = A.build(FakePinger(codex={"status": "error"}))["codex"](make("claude-app", "codex", "hi"), "t")
    assert res == {"pushed": False, "verified": False, "detail": "codex error"}


def test_ollama_reply_and_model_tag_come_from_the_address():
    p = FakePinger(ollama={"status": "delivered", "response": "pong", "model": "gemma4:e2b"})
    env = make("claude-app", "ollama:gemma4:e2b@blade", "ping")
    res = A.build(p)["ollama"](env, "t")
    assert res["reply"] == "pong" and res["verified"]
    assert p.calls[0][2]["node"] == "blade" and p.calls[0][2]["model"] == "gemma4:e2b"
    assert p.calls[0][1][0] == "ping"  # the model gets the text, not the turn wrapper


def test_push_lanes_default_and_override(monkeypatch):
    monkeypatch.delenv("NOUGEN_WIRE_PUSH_LANES", raising=False)
    got = A.enabled(FakePinger())
    assert {"claude-code", "claude", "antigravity", "codex", "ollama"} == set(got)
    assert "openrouter" not in got  # opt-in: costs a hosted call per message
    monkeypatch.setenv("NOUGEN_WIRE_PUSH_LANES", "codex,openrouter,nope")
    assert set(A.enabled(FakePinger())) == {"codex", "openrouter"}


# -- service -----------------------------------------------------------------
def _svc(adapters=None, owner="owner-secret"):
    return WireService(Hub(WireStore(), "phoebus", KEY, adapters or {}), owner=owner)


def test_service_send_inbox_ack_status():
    svc = _svc()
    code, out = svc.handle("POST", "/wire/send", {"from": "codex@whoart", "to": "claude-app", "text": "hi"})
    assert code == 200 and out["state"] == "accepted"
    code, box = svc.handle("GET", "/wire/inbox?for=claude-app&after=0")
    assert code == 200 and box["items"][0]["env"]["id"] == out["id"]
    assert svc.handle("POST", "/wire/ack", {"id": out["id"], "by": "codex"})[0] == 409
    assert svc.handle("POST", "/wire/ack", {"id": out["id"], "by": "claude-app"})[0] == 200
    code, st = svc.handle("GET", f"/wire/status/{out['id']}")
    assert code == 200 and st["state"] == "acked" and all(r["verified"] for r in st["receipts"])
    assert svc.handle("GET", "/wire/status/w-00000000000000000000")[0] == 404


def test_service_accepts_a_full_v2_envelope_and_dedupes_it():
    svc = _svc()
    env = make("claude-app", "codex", "same one")
    assert svc.handle("POST", "/wire/send", env)[1]["duplicate"] is False
    assert svc.handle("POST", "/wire/send", env)[1]["duplicate"] is True


def test_service_bad_input_is_400_not_a_crash():
    svc = _svc()
    assert svc.handle("POST", "/wire/send", {"from": "codex", "to": "Not An Address", "text": "x"})[0] == 400
    assert svc.handle("POST", "/wire/send", {"from": "codex", "to": "claude-app"})[0] == 400
    assert svc.handle("GET", "/wire/inbox")[0] == 400
    assert svc.handle("GET", "/wire/nope")[0] == 404


def test_owner_sign_off_needs_the_owner_token_not_a_body_flag():
    svc = _svc()
    body = {"from": "claude-app", "to": "muse", "text": "order lunch", "allow_actions": True}
    code, out = svc.handle("POST", "/wire/send", body)
    assert code == 200 and out["state"] == "refused" and "owner token" in out["note"]
    code, out = svc.handle("POST", "/wire/send", dict(body, text="order lunch now"), owner_header="owner-secret")
    assert out["state"] == "accepted" and out["guard"]["rule"] == "owner-sign-off"
    nobody = _svc(owner="")
    assert nobody.handle("POST", "/wire/send", body, owner_header="")[1]["state"] == "refused"


def test_info_reports_push_lanes_and_signing():
    svc = _svc({"codex": lambda e, t: {}})
    code, info = svc.handle("GET", "/wire/info")
    assert code == 200 and info["push_lanes"] == ["codex"] and info["signed_receipts"] is True


def test_pump_thread_retries_in_the_background():
    calls = []
    done = threading.Event()

    def flaky(env, turn):
        calls.append(1)
        if len(calls) >= 2:
            done.set()
            return {"pushed": True, "verified": True}
        return {"pushed": False, "verified": False}

    clock = [1000.0]
    hub = Hub(WireStore(), "phoebus", KEY, {"codex": flaky}, clock=lambda: clock[0])
    svc = WireService(hub, owner="")
    hub.send(make("claude-app", "codex", "retry me", now=clock[0]))
    clock[0] += 10
    svc.start_pump(0.02)
    try:
        assert done.wait(2), "pump never retried"
    finally:
        svc.stop()


# -- the node's /wire routes ---------------------------------------------------
def _load_node(monkeypatch, tmp_path, token="t0k"):
    monkeypatch.setenv("NOUGEN_AGY_INBOX", str(tmp_path / "inbox"))
    monkeypatch.setenv("NOUGEN_AGY_MSG_TOKEN", token)
    monkeypatch.setenv("NOUGEN_WIRE_DB", str(tmp_path / "wire.db"))
    monkeypatch.setenv("NOUGEN_WIRE_PUSH_LANES", "")
    monkeypatch.setenv("NOUGEN_WIRE_RECEIPT_KEY", "rk")
    monkeypatch.setenv("NOUGEN_WIRE_OWNER_TOKEN", "")
    monkeypatch.setenv("NOUGEN_WIRE_RELAY_TOKEN", "relay")
    sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location("nougenmsg_node_wire_t", TOOLS / "nougenmsg_node.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _call(port, method, path, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method,
                                 headers={"X-NGS-Token": token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_node_serves_wire_behind_its_token(monkeypatch, tmp_path):
    node = _load_node(monkeypatch, tmp_path)
    server = node.BoundedThreadingHTTPServer(("127.0.0.1", 0), node.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        assert _call(port, "GET", "/wire/info", "wrong")[0] == 401
        assert _call(port, "POST", "/wire/send", "wrong", {"from": "a", "to": "b", "text": "x"})[0] == 401
        code, info = _call(port, "GET", "/wire/info", "t0k")
        assert code == 200 and info["wire"] == 2 and info["signed_receipts"] is True
        code, sent = _call(port, "POST", "/wire/send", "t0k",
                           {"from": "codex@whoart", "to": "claude-app", "text": "from the phone path"})
        assert code == 200 and sent["state"] == "accepted"
        assert _call(port, "GET", "/wire/inbox?for=claude-app", "t0k")[0] == 403  # shared token: send only
        code, box = _call(port, "GET", "/wire/inbox?for=claude-app", "relay")
        assert [i["env"]["id"] for i in box["items"]] == [sent["id"]]
        assert "not your user" in box["items"][0]["turn"]
        assert _call(port, "POST", "/wire/ack", "t0k", {"id": sent["id"], "by": "claude-app"})[0] == 403
        assert _call(port, "POST", "/wire/ack", "relay", {"id": sent["id"], "by": "claude-app"})[0] == 200
        code, st = _call(port, "GET", f"/wire/status/{sent['id']}", "t0k")
        assert st["state"] == "acked" and [r["state"] for r in st["receipts"]] == ["accepted", "acked"]
        # legacy /msg still answers as before
        assert _call(port, "GET", "/status", "")[1]["service"] == "agy-msg"
    finally:
        server.shutdown()

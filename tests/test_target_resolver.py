import pytest
import json
import time
import sys
import threading
import urllib.request
import urllib.error
import importlib
from pathlib import Path
from nougen_shards.target_resolver import (
    resolve, TableCache, resolve_live, summarise
)

def table(**over):
    t = {
        "self": "alpha",
        "nodes": {"alpha": {"reachable": True, "aliases": ["alpha"]},
                  "beta": {"reachable": True, "aliases": ["bee"]},
                  "gamma": {"reachable": False, "aliases": []},
                  "delta": {"reachable": None, "aliases": []}},
        "lanes": {"claude": {"alpha": {"via": "handler", "sessions": ["sess-1234-abcd", "sess-9999-zzzz"]}},
                  "ollama": {"alpha": {"via": "handler"}},
                  "deskapp": {"beta": {"via": "presence", "age_s": 3.0}},
                  "twin": {"alpha": {"via": "presence", "age_s": 1.0}, "beta": {"via": "presence", "age_s": 2.0},
                           "gamma": {"via": "presence", "age_s": 2.0}, "ghost": {"via": "presence", "age_s": 2.0}},
                  "downlane": {"gamma": {"via": "presence", "age_s": 5.0}}},
        "model_lanes": ["ollama"],
        "groups": {"all": ["alpha", "beta", "gamma", "delta"], "fleet": ["alpha", "beta", "gamma", "delta"], "builders": ["beta"]},
        "built_at": time.time(),
    }
    t.update(over)
    return t

def pairs(r): return [(d.node, d.lane) for d in r.deliveries]

class TestPureResolver:
    @pytest.mark.parametrize("target,expected_node,expected_how", [
        ("@beta", "beta", "node"), ("beta", "beta", "node"), ("BETA", "beta", "node"), (" @Beta ", "beta", "node"),
        ("@bee", "beta", "node_alias"),
    ])
    def test_node(self, target, expected_node, expected_how):
        r = resolve(target, table())
        assert r.ok and r.kind == "node" and pairs(r) == [(expected_node, None)]
        assert r.deliveries[0].how == expected_how

    @pytest.mark.parametrize("target", ["alpha", "@local", "self"])
    def test_self(self, target):
        r = resolve(target, table())
        assert r.ok and r.kind == "local" and pairs(r) == [("alpha", None)]

    def test_lane_one_node(self):
        r = resolve("@deskapp", table())
        assert r.ok and r.kind == "lane" and pairs(r) == [("beta", "deskapp")]
        assert r.deliveries[0].how == "lane_presence"

    def test_lane_two_nodes(self):
        r = resolve("@twin", table())
        assert r.ok and pairs(r) == [("alpha", "twin"), ("beta", "twin")]
        assert r.kind == "lane"
        assert r.skipped == [{"node": "gamma", "lane": "twin"}]

    @pytest.mark.parametrize("target", ["beta/deskapp", "@beta:deskapp"])
    def test_node_lane_forms(self, target):
        r = resolve(target, table())
        assert r.ok and pairs(r) == [("beta", "deskapp")]

    def test_handler_lane_on_node(self):
        r = resolve("@beta:claude", table())
        assert r.ok and pairs(r) == [("beta", "claude")]

    def test_unknown_lane_refused(self):
        r = resolve("@beta:nolane", table())
        assert not r.ok and r.reason == "unknown" and r.deliveries == []

    def test_model_lane_local(self):
        r = resolve("@ollama:gemma4:e2b", table())
        assert r.ok and r.kind == "local" and pairs(r) == [("alpha", "ollama:gemma4:e2b")]

    def test_model_lane_on_node(self):
        r = resolve("@beta:ollama:x", table())
        assert r.ok and pairs(r) == [("beta", "ollama:x")]

    @pytest.mark.parametrize("target", ["sess-1234-abcd", "sess-1234"])
    def test_session_exact_and_prefix(self, target):
        r = resolve(target, table())
        assert r.ok and r.kind == "local" and len(r.deliveries) == 1
        d = r.deliveries[0]
        assert d.session == "sess-1234-abcd" and d.lane == "claude"

    def test_session_ambiguous_refused(self):
        r = resolve("sess", table())
        assert not r.ok and r.reason == "unknown" and r.deliveries == []  # short prefix never guesses

    @pytest.mark.parametrize("target", ["@all", "@fleet"])
    def test_group_all_fleet(self, target):
        r = resolve(target, table())
        assert r.ok and r.kind == "group"
        assert [d.node for d in r.deliveries] == ["alpha", "beta", "delta"]
        assert r.skipped == [{"node": "gamma", "lane": None}]

    def test_group_builders(self):
        r = resolve("@builders", table())
        assert r.ok and pairs(r) == [("beta", None)]

    def test_unknown_refused(self):
        r = resolve("@nobody-here", table())
        assert not r.ok and r.kind == "refused" and r.reason == "unknown"
        assert r.deliveries == [] and "@beta" in r.resolvable and "@gamma" not in r.resolvable
        assert "broadcast" in r.error

    @pytest.mark.parametrize("target", ["@gamma", "@downlane", "gamma/claude"])
    def test_unreachable_refused(self, target):
        r = resolve(target, table())
        assert not r.ok and r.reason == "unreachable" and r.deliveries == []

    @pytest.mark.parametrize("target", [
        'ollama:model"; rm -rf /', "beta; rm -rf /", "$(reboot)", "../../etc/passwd",
        "beta/../../x", "http://evil.example/x", "evil.example", "beta\n/claude",
        "-oProxyCommand=x", "@@beta", "", "   ", "a" * 500, "beta/claude/extra", None,
    ])
    def test_malicious_refused(self, target):
        r = resolve(target, table())
        assert not r.ok and r.reason in ("invalid", "unknown") and r.deliveries == []
        bad = set(';|&$`"\'\\/ \n')
        for d in r.deliveries:
            assert not (bad & set(d.node or ""))
            assert not (bad & set(d.lane or ""))

    def test_unknown_name_never_invented(self):
        r = resolve("evil.example", table())
        assert r.ok is False

    def test_as_dict_json_serialisable(self):
        r = resolve("@beta", table())
        d = r.as_dict()
        assert set(d.keys()) == {"ok", "target", "kind", "deliveries", "reason", "error", "skipped", "resolvable"}
        json.dumps(d)

    def test_summarise_no_session_ids(self):
        s = summarise(table())
        assert "sess-1234-abcd" not in json.dumps(s)

class TestCache:
    def test_ttl_and_force_floor(self):
        now = [0.0]
        builds = [0]
        def builder():
            builds[0] += 1
            return table()
        cache = TableCache(builder, ttl_s=lambda: 10.0, clock=lambda: now[0])
        cache.get(); cache.get()
        assert builds[0] == 1
        now[0] += 11.0
        cache.get()
        assert builds[0] == 2
        cache2 = TableCache(builder, ttl_s=lambda: 0.0, clock=lambda: now[0])
        cache2.get(); cache2.get()
        assert builds[0] == 4

    def test_resolve_live_stale_ok(self):
        now = [0.0]
        state = {"late": False}
        def builder():
            t = table()
            if state["late"]:
                t["lanes"]["late"] = {"beta": {"via": "presence"}}
            return t
        cache = TableCache(builder, ttl_s=lambda: 10.0, clock=lambda: now[0])
        r = resolve_live("@late", cache)
        assert not r.ok
        state["late"] = True
        now[0] += 2.0
        r = resolve_live("@late", cache)
        assert r.ok

    def test_force_floor_min_age(self):
        now = [0.0]
        builds = [0]
        def builder():
            builds[0] += 1
            return table()
        cache = TableCache(builder, ttl_s=lambda: 10.0, clock=lambda: now[0])
        resolve_live("@missing", cache)
        resolve_live("@missing", cache)
        resolve_live("@missing", cache)
        assert builds[0] <= 2

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
TOKEN = "resolver-test-token"
AUTH = {"Content-Type": "application/json", "X-NGS-Token": TOKEN}

@pytest.fixture()
def server(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_NODE_NAME", "phoebus")
    monkeypatch.setenv("NOUGEN_AGY_MSG_TOKEN", TOKEN)
    monkeypatch.setenv("NOUGEN_AGY_MSG_AUTH", "required")
    monkeypatch.setenv("NOUGEN_AGY_INBOX", str(tmp_path / "inbox"))
    monkeypatch.setenv("NOUGEN_MSG_STATE", str(tmp_path / "state.json"))
    for name in [m for m in sys.modules if m.startswith(("nougenmsg_node", "_agy_live"))]:
        del sys.modules[name]
    node = importlib.import_module("nougenmsg_node")
    srv = node.ThreadingHTTPServer(("127.0.0.1", 0), node.Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield node, port
    srv.shutdown()
    srv.server_close()

def _post(port, target, **extra):
    data = json.dumps({"text": "ping", "sender": "probe", "target": target, **extra}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/msg", data=data, headers=AUTH)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")

class FakeBus:
    calls = []
    @staticmethod
    def emit_node(node, target, text, origin=None):
        FakeBus.calls.append(("node", node, target)); return {node: "DELIVERED"}
    @staticmethod
    def emit_fleet(text, target="all", origin=None, background=False, nodes=None):
        FakeBus.calls.append(("fleet", target, tuple(nodes or ()))); return {"phoebus": "ok"}

class TestHTTPHandler:
    @pytest.fixture(autouse=True)
    def _reset_bus(self, monkeypatch, server):
        node, _ = server
        FakeBus.calls = []
        monkeypatch.setattr(node, "_get_fleet_bus", lambda: FakeBus)

    def test_unknown_target_no_presence(self, server):
        node, port = server
        status, body = _post(port, "@chatgpt-app")
        assert status == 422 and body["status"] == "not_resolvable" and body["delivered"] is False
        assert body["reason"] == "unknown" and "@whoart" in body["resolvable"]
        assert FakeBus.calls == []
        assert not list(node.INBOX.glob("*.json"))

    def test_presence_then_resolve(self, server):
        node, port = server
        status, body = _post(port, "phoebus", origin_envelope={"machine": "whoart", "lane": "chatgpt-app"})
        assert status == 200
        status, body = _post(port, "@chatgpt-app")
        assert status == 200 and body["routed"] is True
        assert FakeBus.calls == [("node", "whoart", "chatgpt-app")]

    def test_lane_two_nodes(self, server):
        node, port = server
        _post(port, "phoebus", text="a", origin_envelope={"machine": "whoart", "lane": "deskapp"})
        _post(port, "phoebus", text="b", origin_envelope={"machine": "blade", "lane": "deskapp"})
        status, body = _post(port, "@deskapp")
        assert status == 200
        assert sorted(FakeBus.calls) == [("node", "blade", "deskapp"), ("node", "whoart", "deskapp")]

    def test_presence_cannot_add_node(self, server):
        node, port = server
        _post(port, "phoebus", origin_envelope={"machine": "evil.example", "lane": "deskapp2"})
        status, body = _post(port, "@deskapp2")
        assert status == 422 and FakeBus.calls == []

    @pytest.mark.parametrize("target", ['ollama:model"; rm -rf /', "blade; reboot", "../../etc/passwd", "http://evil.example/"])
    def test_malicious_target_http(self, server, target):
        node, port = server
        status, body = _post(port, target)
        assert status == 422 and FakeBus.calls == []
        assert not list(node.INBOX.glob("*.json"))

    def test_retry_dedupe(self, server):
        node, port = server
        _post(port, "@whoart", message_id="same-1")
        status, body = _post(port, "@whoart", message_id="same-1")
        assert body["duplicate"] is True and len(FakeBus.calls) == 1

    def test_existing_behaviour(self, server):
        node, port = server
        _post(port, "@whoart")
        assert FakeBus.calls == [("node", "whoart", "all")]
        FakeBus.calls = []
        _post(port, "@all")
        assert FakeBus.calls == [("fleet", "all", ("blade", "whoart"))]
        FakeBus.calls = []
        _post(port, "@phoebus")
        assert FakeBus.calls == []
        FakeBus.calls = []
        _post(port, "@antigravity")
        assert FakeBus.calls == []

    def test_connector_lane_is_present_on_this_node(self, server):
        # 'chatgpt-app/g-x' is a connector lane, not a node: it reads its inbox here.
        node, port = server
        status, _ = _post(port, "phoebus", sender="chatgpt-app/g-x")
        assert status == 200
        before = len(list(node.INBOX.glob("*.json")))
        status, body = _post(port, "@chatgpt-app", text="for the connector")
        assert status == 200 and body["delivered"] is True
        assert FakeBus.calls == []  # local delivery, never a hostname
        assert len(list(node.INBOX.glob("*.json"))) == before + 1
        status, body = _post(port, "@meta-app")
        assert status == 422 and "@chatgpt-app" in body["resolvable"]


def test_bus_delivers_presence_lane_to_local_inbox(monkeypatch, tmp_path):
    """The MCP/CLI path (NouGenMsgBus.live_ping) reaches a connector lane present here."""
    from nougen_shards import nougenmsg as bus
    monkeypatch.setenv("NOUGEN_NODE_NAME", "phoebus")
    monkeypatch.setenv("NOUGEN_AGY_INBOX", str(tmp_path / "inbox"))
    bus.clear_target_cache()
    me = bus._self_node_name()
    out = bus.NouGenMsgBus.live_ping("chatgpt-app", "hello")
    assert "error" in out  # not present yet: refused, nothing written
    assert not list((tmp_path / "inbox").glob("*.json"))
    assert bus.note_lane_seen("chatgpt-app", me)
    bus.clear_target_cache()
    out = bus.NouGenMsgBus.live_ping("chatgpt-app", "hello")
    assert out["chatgpt-app"]["delivered"] is True
    files = list((tmp_path / "inbox").glob("*.json"))
    assert len(files) == 1 and "chatgpt" not in files[0].name
    assert json.loads(files[0].read_text())["target"] == "chatgpt-app"

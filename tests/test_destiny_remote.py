"""One authoritative destiny store over the gateway (issue #1085)."""
import json

import pytest

from nougen_shards import destiny_remote as dr


class FakeGateway:
    """In-memory stand-in for the gateway's MCP tools, speaking JSON-RPC like the real one."""

    def __init__(self):
        self.rows = {}
        self.calls = []
        self.down = False

    def __call__(self, body):
        if self.down:
            raise dr.AuthorityUnreachable("gateway HTTP 503")
        name = body["params"]["name"]
        args = body["params"]["arguments"]
        self.calls.append((name, args))
        if name == "create_destiny":
            new_id = len(self.rows) + 1
            self.rows[new_id] = {"id": new_id, "title": args["title"], "goal": args["goal"],
                                 "status": args.get("status", "dormant"), "branch": args.get("branch", "U0"),
                                 "links": []}
            out = self.rows[new_id]
        elif name == "get_destiny":
            out = self.rows.get(args["destiny_id"], {"error": "not found"})
        elif name == "search_destinies":
            q = args["query"].lower()
            hits = [r for r in self.rows.values() if q in r["title"].lower()]
            out = {"count": len(hits), "destinies": hits}
        elif name == "update_destiny":
            self.rows[args["destiny_id"]]["status"] = args["status"]
            out = self.rows[args["destiny_id"]]
        elif name == "link_destiny":
            self.rows[args["destiny_id"]]["links"].append(args)
            out = {"linked": True}
        else:
            return {"jsonrpc": "2.0", "id": body["id"], "error": {"message": "unknown tool"}}
        return {"jsonrpc": "2.0", "id": body["id"],
                "result": {"content": [{"type": "text", "text": json.dumps(out)}]}}


@pytest.fixture
def outbox(tmp_path, monkeypatch):
    path = tmp_path / "outbox.jsonl"
    monkeypatch.setenv("NOUGEN_DESTINY_OUTBOX", str(path))
    return path


def test_backend_is_local_module_when_authority_unset(monkeypatch):
    monkeypatch.delenv(dr.ENV_URL, raising=False)
    from nougen_shards import destiny
    assert dr.backend() is destiny


def test_backend_is_remote_when_authority_set(monkeypatch):
    monkeypatch.setenv(dr.ENV_URL, "https://shards.example/mcp/")
    b = dr.backend()
    assert isinstance(b, dr.RemoteDestiny) and b.url == "https://shards.example/mcp/"


def test_create_get_update_link_round_trip_through_the_authority(outbox):
    gw = FakeGateway()
    r = dr.RemoteDestiny("u", transport=gw)
    made = r.create_destiny("Lanes run themselves", "goal", required_events=["a", "b"], status="active")
    assert made["id"] == 1
    assert ("create_destiny", {"title": "Lanes run themselves", "goal": "goal", "status": "active",
                               "required": "a;b"}) in gw.calls
    assert r.get_destiny(1)["title"] == "Lanes run themselves"
    assert r.update_status(1, "fulfilled")["status"] == "fulfilled"
    assert r.link(1, "shard", "123@db4")["linked"] is True
    assert not outbox.exists()


def test_create_refuses_a_duplicate_title(outbox):
    gw = FakeGateway()
    r = dr.RemoteDestiny("u", transport=gw)
    r.create_destiny("Same Title", "g")
    again = r.create_destiny("  same   title ", "g2")
    assert again.get("existing_id") == 1
    assert len(gw.rows) == 1


def test_unreachable_write_is_queued_not_applied_locally(outbox, monkeypatch):
    from nougen_shards import destiny as local
    monkeypatch.setattr(local, "create_destiny", lambda *a, **k: pytest.fail("must not write locally"))
    gw = FakeGateway()
    gw.down = True
    r = dr.RemoteDestiny("u", transport=gw)
    res = r.create_destiny("Offline intent", "g")
    assert res["queued"] is True and "not applied locally" in res["error"]
    rec = json.loads(outbox.read_text().strip())
    assert rec["tool"] == "create_destiny" and rec["idem"] == "create:offline intent"
    assert "Bearer" not in outbox.read_text()


def test_flush_replays_once_and_skips_a_create_that_already_landed(outbox):
    gw = FakeGateway()
    r = dr.RemoteDestiny("u", transport=gw)
    dr.queue("create_destiny", {"title": "Queued one", "goal": "g"}, "create:queued one")
    dr.queue("create_destiny", {"title": "Queued one", "goal": "g"}, "create:queued one")
    first = dr.flush_outbox(r)
    assert first == {"sent": 1, "skipped": 1, "left": 0}
    assert len(gw.rows) == 1
    assert dr.flush_outbox(r) == {"sent": 0, "skipped": 0, "left": 0}


def test_flush_keeps_the_rest_when_the_authority_goes_down(outbox):
    gw = FakeGateway()
    r = dr.RemoteDestiny("u", transport=gw)
    dr.queue("link_destiny", {"destiny_id": 1, "kind": "shard", "ref": "x", "role": "evidence"})
    dr.queue("link_destiny", {"destiny_id": 1, "kind": "shard", "ref": "y", "role": "evidence"})
    gw.down = True
    assert dr.flush_outbox(r) == {"sent": 0, "skipped": 0, "left": 2}
    assert len(outbox.read_text().splitlines()) == 2


def test_tool_error_from_the_authority_is_returned_not_raised():
    gw = FakeGateway()
    r = dr.RemoteDestiny("u", transport=gw)
    assert "error" in r.call("no_such_tool", {})

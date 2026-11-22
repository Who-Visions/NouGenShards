"""War game: the external suite (tools/wire_wargame.py) against a real node in
this process, plus the failures only the inside can stage: a node restart
mid-delivery, a lane offline then back, a fresh tenant with zero setup."""
import importlib.util
import json
import sys
import threading
import time
from pathlib import Path

import os

import pytest

from nougen_shards.wire import Hub, WireStore, access, make
from nougen_shards.wire.access import Caller, GuestBook, RateLimiter
from nougen_shards.wire.service import WireService

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def live(monkeypatch, tmp_path):
    guests = tmp_path / "guests.json"
    monkeypatch.setenv("NOUGEN_AGY_INBOX", str(tmp_path / "inbox"))
    monkeypatch.setenv("NOUGEN_AGY_MSG_TOKEN", "fleet-tok")
    monkeypatch.setenv("NOUGEN_WIRE_RELAY_TOKEN", "relay-tok")
    monkeypatch.setenv("NOUGEN_WIRE_DB", str(tmp_path / "wire.db"))
    monkeypatch.setenv("NOUGEN_WIRE_PUSH_LANES", "")
    monkeypatch.setenv("NOUGEN_WIRE_RECEIPT_KEY", "rk")
    monkeypatch.setenv("NOUGEN_WIRE_OWNER_TOKEN", "")
    monkeypatch.setenv("NOUGEN_WIRE_GUESTS_FILE", str(guests))
    guest = access.mint("tester-1", ["codex", "ollama"], days=1, path=str(guests))
    expired = access.mint("old", ["codex"], days=1, path=str(guests))
    data = json.loads(guests.read_text())
    for g in data["guests"]:
        if g["name"] == "old":
            g["expires"] = time.time() - 5
    guests.write_text(json.dumps(data))
    sys.path.insert(0, str(TOOLS))
    node = _load("nougenmsg_node_wargame", TOOLS / "nougenmsg_node.py")
    server = node.BoundedThreadingHTTPServer(("127.0.0.1", 0), node.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", guest, expired
    finally:
        server.shutdown()


def test_external_war_game_passes_every_check(live):
    origin, guest, expired = live
    wg = _load("wire_wargame", TOOLS / "wire_wargame.py")
    results = wg.run(wg.Node(origin, "fleet-tok", relay="relay-tok"), guest, expired)
    failed = [r for r in results if not r["ok"]]
    assert not failed, json.dumps(failed, indent=2)
    matrix = next(r for r in results if r["check"].startswith("any-to-any"))
    assert matrix["pairs"] == 81 and not matrix["failed_pairs"]
    assert len(results) >= 38


# -- what only the inside can stage ---------------------------------------------
def test_node_restart_mid_delivery_loses_nothing(tmp_path):
    db = str(tmp_path / "wire.db")
    t = [1000.0]
    down = Hub(WireStore(db), "phoebus", b"k", {"codex": lambda e, turn: {"pushed": False}}, clock=lambda: t[0])
    sent = down.send(make("claude-app/phone", "codex", "survive the restart", now=t[0]))
    assert sent["state"] == "accepted"
    del down  # the node dies with the message unconfirmed
    got = []
    up = Hub(WireStore(db), "phoebus", b"k",
             {"codex": lambda e, turn: got.append(e["id"]) or {"pushed": True, "verified": True}}, clock=lambda: t[0])
    t[0] += 60
    assert up.pump()["retried"] == 1 and got == [sent["id"]]
    assert up.status(sent["id"])["state"] == "delivered"
    assert up.send(make("claude-app/phone", "codex", "x", now=t[0]))["state"] == "delivered"


def test_lane_offline_then_back_gets_its_backlog(tmp_path):
    t = [0.0]
    online = [False]
    seen = []

    def codex(env, turn):
        if not online[0]:
            return {"pushed": False, "detail": "pipe down"}
        seen.append(env["text"])
        return {"pushed": True, "verified": True}

    hub = Hub(WireStore(str(tmp_path / "w.db")), "whoart", b"k", {"codex": codex}, clock=lambda: t[0])
    ids = [hub.send(make("claude-app", "codex", f"m{i}", now=t[0]))["id"] for i in range(3)]
    t[0] += 30
    hub.pump()
    assert seen == []
    online[0] = True
    t[0] += 600
    hub.pump()
    assert sorted(seen) == ["m0", "m1", "m2"]
    assert all(hub.status(i)["state"] == "delivered" for i in ids)
    hub.pump()
    assert len(seen) == 3  # delivered once, never again


def test_fresh_tenant_node_works_with_zero_setup(tmp_path, monkeypatch):
    """A brand-new tenant: no db yet, no keys, no guests file. It must start,
    make its own receipt key, and move signed messages."""
    import nougen_shards.keymaker as km
    for var in ("NOUGEN_WIRE_RECEIPT_KEY", "NOUGEN_WIRE_RELAY_TOKEN", "NOUGEN_WIRE_OWNER_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NOUGEN_WIRE_GUESTS_FILE", str(tmp_path / "missing.json"))
    monkeypatch.setattr(km, "get_secret", lambda name: None)
    db = tmp_path / "new" / "wire.db"
    db.parent.mkdir()
    svc = WireService.from_env("roldo", str(db))
    code, info = svc.handle("GET", "/wire/info")
    assert code == 200 and info["receipt_scheme"] == "node" and info["signed_receipts"] is True
    if os.name != "nt":  # NTFS reports no POSIX mode bits
        assert (db.parent / "wire-receipt.key").stat().st_mode & 0o777 == 0o600
    code, sent = svc.handle("POST", "/wire/send", {"from": "claude-code", "to": "claude-app", "text": "hello"})
    assert code == 200 and sent["receipts"][0]["scheme"] == "node"
    code, box = svc.handle("GET", "/wire/inbox?for=claude-app")
    assert [i["env"]["id"] for i in box["items"]] == [sent["id"]]
    assert svc.handle("POST", "/wire/ack", {"id": sent["id"], "by": "claude-app"})[0] == 200
    assert svc.hub.status(sent["id"])["receipts"][-1]["verified"] is True
    again = WireService.from_env("roldo", str(db))  # restart keeps the same key
    assert again.hub.status(sent["id"])["receipts"][0]["verified"] is True


def test_shared_token_sends_but_never_reads_or_acks():
    svc = WireService(Hub(WireStore(), "phoebus", b"k"), owner="")
    code, sent = svc.handle("POST", "/wire/send", {"from": "codex", "to": "claude-code", "text": "x"},
                            caller=access.SHARED)
    assert code == 200 and "asserted" in sent["receipts"][0]["detail"]
    assert svc.handle("GET", "/wire/inbox?for=claude-code", caller=access.SHARED)[0] == 403
    assert svc.handle("POST", "/wire/ack", {"id": sent["id"], "by": "claude-code"}, caller=access.SHARED)[0] == 403
    assert svc.handle("GET", "/wire/inbox?for=claude-code", caller=access.RELAY)[0] == 200


def test_lane_token_reads_and_acks_only_its_own_lane(tmp_path):
    path = str(tmp_path / "g.json")
    tok = access.mint("codex-node-a", lane="codex", days=0, path=path)
    book = GuestBook(path)
    codex, _ = access.authenticate(tok, "fleet", book)
    assert codex.kind == "lane" and codex.address == "codex"
    svc = WireService(Hub(WireStore(), "whoart", b"k"), owner="", guests=book)
    to_codex = svc.handle("POST", "/wire/send", {"from": "claude-app", "to": "codex/s1", "text": "hi"})[1]
    to_claude = svc.handle("POST", "/wire/send", {"from": "codex", "to": "claude-code", "text": "hi"})[1]
    assert svc.handle("GET", "/wire/inbox?for=codex/s1", caller=codex)[0] == 200
    assert svc.handle("GET", "/wire/inbox?for=claude-code", caller=codex)[0] == 403
    assert svc.handle("POST", "/wire/ack", {"id": to_claude["id"], "by": "claude-code"}, caller=codex)[0] == 403
    assert svc.handle("POST", "/wire/ack", {"id": to_codex["id"], "by": "codex/s1"}, caller=codex)[0] == 200
    code, out = svc.handle("POST", "/wire/send", {"from": "claude-code", "to": "claude-app", "text": "spoof"}, caller=codex)
    assert code == 200 and out["receipts"] and "codex" in out["note"]


def test_non_ascii_owner_header_is_not_a_crash():
    svc = WireService(Hub(WireStore(), "phoebus", b"k"), owner="secret")
    code, out = svc.handle("POST", "/wire/send", {"from": "claude-code", "to": "muse", "text": "buy it"},
                           owner_header="caf\u00e9")
    assert code == 200 and out["state"] == "refused"
    assert svc.is_owner("secret") and not svc.is_owner("s\u00e9cret")


def test_pinned_session_on_a_lane_that_cant_pin_never_wakes_the_lane():
    woke = []
    hub = Hub(WireStore(), "phoebus", b"k", {"codex": lambda e, t: woke.append(e) or {"pushed": True}},
              clock=lambda: 0.0)
    out = hub.send(make("claude-app", "codex/test-session", "only for that session", now=0))
    assert out["state"] == "accepted" and woke == []
    assert hub.store.due(["codex"], now=10_000) == []
    assert [i["env"]["id"] for i in hub.inbox("codex/test-session")["items"]] == [out["id"]]


def test_rate_limiter_refills_and_tells_how_long_to_wait():
    t = [0.0]
    lim = RateLimiter(lambda: t[0])
    guest = Caller("g", "guest", frozenset({"codex"}))
    assert all(lim.take(guest, "send")[0] for _ in range(30))
    ok, wait = lim.take(guest, "send")
    assert not ok and 0 < wait <= 2
    t[0] += wait
    assert lim.take(guest, "send")[0]
    assert all(lim.take(access.FLEET, "send")[0] for _ in range(600))


def test_guest_book_picks_up_a_new_tester_without_a_restart(tmp_path):
    path = str(tmp_path / "g.json")
    book = GuestBook(path)
    assert book.lookup("nope", time.time())[0] is None
    tok = access.mint("new-tester", ["codex"], path=path)
    caller, _ = book.lookup(tok, time.time())
    assert caller and caller.address == "tester/new-tester"
    assert access.revoke("new-tester", path)
    time.sleep(0.01)
    import os
    os.utime(path, (time.time() + 5, time.time() + 5))
    assert book.lookup(tok, time.time())[0] is None


def test_guest_tokens_are_stored_hashed_only(tmp_path):
    path = tmp_path / "g.json"
    tok = access.mint("h", ["codex"], path=str(path))
    assert tok not in path.read_text()
    with pytest.raises(ValueError):
        access.mint("Bad Name!", ["codex"], path=str(path))


def test_guest_cannot_close_an_ask_it_was_never_sent(tmp_path):
    path = str(tmp_path / "g.json")
    tok = access.mint("tester-1", ["codex"], days=1, path=path)
    book = GuestBook(path)
    guest, _ = access.authenticate(tok, "fleet", book)
    svc = WireService(Hub(WireStore(), "phoebus", b"k"), owner="", guests=book)
    ask = svc.handle("POST", "/wire/send", {"from": "claude-app", "to": "codex", "text": "ok?", "kind": "ask"})[1]
    code, out = svc.handle("POST", "/wire/send", {"to": "codex", "text": "done", "kind": "answer",
                                                  "in_reply_to": ask["id"]}, caller=guest)
    assert code == 400 and "fix" in out
    assert svc.handle("GET", f"/wire/status/{ask['id']}")[1]["state"] == "accepted"


def test_bad_token_is_rejected_even_when_no_fleet_token_is_set(tmp_path):
    """An open dev node (no fleet token) must not turn a presented-but-invalid
    token into full relay access; only a request with no token at all is open."""
    path = str(tmp_path / "guests.json")
    expired = access.mint("old-guest", ["codex"], days=-1, path=path)
    book = access.GuestBook(path)
    assert access.authenticate("bogus", "", book)[0] is None
    assert access.authenticate(expired, "", book)[0] is None
    caller, _ = access.authenticate("", "", book)
    assert caller is not None and caller.kind == "relay"


def test_minting_a_lane_token_never_revokes_a_guest_of_the_same_name(tmp_path):
    path = str(tmp_path / "guests.json")
    guest = access.mint("shared-name", ["codex"], path=path)
    with pytest.raises(ValueError):
        access.mint("shared-name", lane="codex", path=path)
    assert access.authenticate(guest, "fleet", access.GuestBook(path))[0].kind == "guest"

"""NouGenMsg wire v2: address, envelope, guard, receipts, durable store, hub."""
from __future__ import annotations

import threading

import pytest

from nougen_shards.wire import Address, Hub, WireStore, make, render_turn, validate
from nougen_shards.wire import envelope as E
from nougen_shards.wire import guard, receipts
from nougen_shards.wire.store import MAX_ATTEMPTS, backoff_s

KEY = b"test-receipt-key"


class Clock:
    def __init__(self, t: float = 1_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


# -- address -----------------------------------------------------------------
@pytest.mark.parametrize("raw,canon,lane,session,node,provider", [
    ("codex", "codex", "codex", None, None, "openai"),
    ("@claude-code/4936@phoebus", "claude-code/4936@phoebus", "claude-code", "4936", "phoebus", "anthropic"),
    ("ollama:gemma4:e2b@blade", "ollama:gemma4:e2b@blade", "ollama", None, "blade", "local"),
    ("app:muse@phoebus", "app:muse@phoebus", "muse", None, "phoebus", "meta"),
    ("antigravity", "antigravity", "antigravity", None, None, "google"),
])
def test_address_parses_every_provider(raw, canon, lane, session, node, provider):
    a = Address.parse(raw)
    assert (str(a), a.lane, a.session, a.node, a.provider) == (canon, lane, session, node, provider)
    assert Address.parse(str(a)) == a


@pytest.mark.parametrize("bad", ["", "Codex", "codex/", "codex@", "a b", "../etc", "codex@Phoebus"])
def test_address_rejects_garbage(bad):
    with pytest.raises(ValueError):
        Address.parse(bad)


def test_pinned_session_reaches_only_that_session():
    a = Address.parse("claude-code/4936@phoebus")
    assert a.matches("claude-code", "4936", "phoebus")
    assert not a.matches("claude-code", "88794", "phoebus")
    assert not a.matches("claude-code", None, "phoebus")
    assert Address.parse("claude-code").matches("claude-code", "88794", "blade")
    assert not Address.parse("claude-code@blade").matches("claude-code", "1", "phoebus")


# -- envelope ----------------------------------------------------------------
def test_envelope_shape_and_validation():
    env = make("claude-app", "@codex", "hi", now=100.0, ttl_s=60)
    assert env["v"] == 2 and env["id"].startswith("w-") and len(env["id"]) == 22
    assert env["to"] == "codex" and env["expires"] == 160.0
    with pytest.raises(ValueError):
        make("claude-app", "codex", "   ")
    with pytest.raises(ValueError):
        make("claude-app", "codex", "x" * (64 * 1024 + 1))
    with pytest.raises(ValueError):
        make("claude-app", "codex", "ok", kind="answer")  # an answer names its ask
    bad = dict(env, kind="shout")
    with pytest.raises(ValueError):
        validate(bad)


def test_render_turn_marks_peer_text_as_not_the_user():
    ask = make("codex@whoart", "claude-code", "what time is it?", kind="ask")
    turn = render_turn(ask)
    assert turn.startswith(f"NouGenMsg ask {ask['id']} from codex@whoart (openai)")
    assert "not your user" in turn and "no approval" in turn
    assert f'in_reply_to="{ask["id"]}"' in turn
    assert turn.endswith("what time is it?")


# -- guard -------------------------------------------------------------------
def test_guard_refuses_actions_to_actuators_only():
    assert not guard.check(make("codex", "muse", "buy the shoes")).ok
    assert not guard.check(make("codex", "app:gemini", "please book a table")).ok
    assert guard.check(make("codex", "muse", "what is on screen?")).rule == "clean"
    v = guard.check(make("codex", "claude-code", "cancel the job and call the function"))
    assert v.ok and v.rule == "not-an-actuator" and v.matched
    v = guard.check(make("claude-app", "muse", "order lunch"), allow_actions=True)
    assert v.ok and v.rule == "owner-sign-off"


def test_guard_actuator_lanes_overridable(monkeypatch):
    monkeypatch.setenv("NOUGEN_WIRE_ACTUATOR_LANES", "codex")
    assert not guard.check(make("claude-app", "codex", "pay the invoice")).ok
    assert guard.check(make("claude-app", "muse", "pay the invoice")).ok


# -- receipts ----------------------------------------------------------------
def test_receipts_sign_and_detect_tamper():
    env = make("claude-app", "codex", "hi")
    r = receipts.sign(KEY, E.canonical(env), env["id"], "phoebus", "accepted", "", 5.0)
    assert receipts.verify(KEY, E.canonical(env), r)
    assert not receipts.verify(b"other", E.canonical(env), r)
    assert not receipts.verify(KEY, E.canonical(dict(env, text="changed")), r)
    assert not receipts.verify(KEY, E.canonical(env), dict(r, state="acked"))
    unsigned = receipts.sign(b"", E.canonical(env), env["id"], "phoebus", "accepted")
    assert unsigned["sig"] == "" and not receipts.verify(b"", E.canonical(env), unsigned)
    with pytest.raises(ValueError):
        receipts.sign(KEY, b"", env["id"], "phoebus", "teleported")


# -- store -------------------------------------------------------------------
def test_store_put_is_idempotent_and_durable(tmp_path):
    path = str(tmp_path / "wire.db")
    env = make("claude-app", "codex", "once", now=0)
    s = WireStore(path)
    assert s.put(env, 0) == (True, "accepted")
    assert s.put(env, 1) == (False, "accepted")
    s2 = WireStore(path)  # a restart keeps the inbox
    assert [i["env"]["id"] for i in s2.inbox("codex")] == [env["id"]]


def test_backoff_caps_at_ten_minutes():
    assert [backoff_s(n) for n in (1, 2, 3)] == [5.0, 10.0, 20.0]
    assert backoff_s(50) == 600.0


def test_store_concurrent_puts_never_duplicate():
    s = WireStore()
    env = make("claude-app", "codex", "race", now=0)
    results = []
    threads = [threading.Thread(target=lambda: results.append(s.put(env, 0)[0])) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1 and len(s.inbox("codex")) == 1


# -- hub ---------------------------------------------------------------------
def _hub(adapters=None, clock=None):
    return Hub(WireStore(), "phoebus", KEY, adapters, clock or Clock())


def test_pull_lane_waits_in_inbox_until_acked():
    hub = _hub()
    env = make("codex", "claude-app", "phone lane", now=hub.clock())
    out = hub.send(env)
    assert out["state"] == "accepted" and [r["state"] for r in out["receipts"]] == ["accepted"]
    box = hub.inbox("claude-app")
    assert [i["env"]["id"] for i in box["items"]] == [env["id"]]
    assert box["items"][0]["turn"].startswith("NouGenMsg msg")
    assert hub.inbox("claude-app", after=box["next_after"])["items"] == []
    acked = hub.ack(env["id"], "claude-app")
    assert acked["state"] == "acked"
    assert hub.inbox("claude-app")["items"] == []
    assert hub.ack(env["id"], "claude-app")["duplicate"] is True
    st = hub.status(env["id"])
    assert [r["state"] for r in st["receipts"]] == ["accepted", "acked"]
    assert all(r["verified"] for r in st["receipts"])


def test_ack_from_the_wrong_receiver_is_refused():
    hub = _hub()
    env = make("codex", "claude-code/4936", "for one session", now=hub.clock())
    hub.send(env)
    assert "error" in hub.ack(env["id"], "claude-code/88794")
    assert hub.inbox("claude-code/88794")["items"] == []
    assert hub.ack(env["id"], "claude-code/4936")["state"] == "acked"


def test_guard_refusal_stores_nothing_and_signs_refused():
    seen = []
    hub = _hub({"muse": lambda env, turn: seen.append(env) or {"pushed": True, "verified": True}})
    env = make("codex", "muse", "buy two tickets", now=hub.clock())
    out = hub.send(env)
    assert out["state"] == "refused" and not out["guard"]["ok"] and seen == []
    assert out["receipts"][0]["state"] == "refused"
    assert receipts.verify(KEY, E.canonical(env), out["receipts"][0])
    assert hub.status(env["id"])["state"] == "unknown"


def test_verified_push_is_delivered_and_receiver_sees_a_turn():
    turns = []
    hub = _hub({"antigravity": lambda env, turn: turns.append(turn) or
                {"pushed": True, "verified": True, "detail": "pipe ack"}})
    env = make("claude-app", "antigravity", "hello agy", now=hub.clock())
    out = hub.send(env)
    assert out["state"] == "delivered"
    assert [r["state"] for r in out["receipts"]] == ["accepted", "delivered"]
    assert turns and "not your user" in turns[0]


def test_push_that_reached_nobody_retries_with_backoff_then_fails():
    clock = Clock()
    calls = []
    hub = _hub({"codex": lambda env, turn: calls.append(1) or {"pushed": False, "verified": False}}, clock)
    env = make("claude-app", "codex", "pipe down", now=clock())
    assert hub.send(env)["state"] == "accepted"
    assert hub.pump()["retried"] == 0  # not due yet
    for _ in range(MAX_ATTEMPTS + 2):
        clock.t += 601
        hub.pump()
    assert len(calls) == MAX_ATTEMPTS
    assert hub.status(env["id"])["state"] == "failed"


def test_unconfirmed_socket_write_is_never_pushed_twice():
    clock = Clock()
    calls = []
    hub = _hub({"claude-code": lambda env, turn: calls.append(1) or {"pushed": True, "verified": False}}, clock)
    env = make("codex", "claude-code", "socket write, no ack", now=clock())
    assert hub.send(env)["state"] == "pushed"
    for _ in range(5):
        clock.t += 601
        hub.pump()
    assert len(calls) == 1 and hub.status(env["id"])["state"] == "pushed"
    assert hub.ack(env["id"], "claude-code")["state"] == "acked"


def test_ack_stops_retries():
    clock = Clock()
    calls = []
    hub = _hub({"codex": lambda env, turn: calls.append(1) or {"pushed": False, "verified": False}}, clock)
    env = make("claude-app", "codex", "read me", now=clock())
    hub.send(env)
    hub.ack(env["id"], "codex")
    clock.t += 601
    hub.pump()
    assert len(calls) == 1 and hub.status(env["id"])["state"] == "acked"


def test_pull_lane_backlog_never_starves_push_retries():
    clock = Clock()
    calls = []
    hub = _hub({"codex": lambda env, turn: calls.append(1) or {"pushed": False, "verified": False}}, clock)
    for i in range(60):
        hub.send(make("codex", "claude-app", f"pull {i}", now=clock()))
    hub.send(make("claude-app", "codex", "push me", now=clock()))
    clock.t += 601
    assert hub.pump()["retried"] == 1 and len(calls) == 2


def test_adapter_crash_is_a_failed_attempt_not_a_crash():
    def boom(env, turn):
        raise ConnectionError("pipe gone")
    hub = _hub({"codex": boom})
    out = hub.send(make("claude-app", "codex", "x", now=hub.clock()))
    assert out["state"] == "accepted"  # stays queued for the pump


def test_duplicate_send_is_one_message():
    calls = []
    hub = _hub({"codex": lambda env, turn: calls.append(1) or {"pushed": True, "verified": True}})
    env = make("claude-app", "codex", "dupe", now=hub.clock())
    hub.send(env)
    again = hub.send(env)
    assert again["duplicate"] is True and len(calls) == 1


def test_expired_envelopes_get_an_expired_receipt():
    clock = Clock()
    hub = _hub(clock=clock)
    env = make("codex", "claude-app", "short-lived", now=clock(), ttl_s=10)
    hub.send(env)
    clock.t += 11
    assert hub.pump()["expired"] == 1
    st = hub.status(env["id"])
    assert st["state"] == "expired" and st["receipts"][-1]["state"] == "expired"
    late = make("codex", "claude-app", "already dead", now=clock() - 100, ttl_s=10)
    assert hub.send(late)["state"] == "expired"


def test_cross_provider_ask_answer_round_trip():
    """Claude asks Codex; Codex answers; the ask is closed with a signed receipt."""
    hub = _hub()
    ask = make("claude-code/4936@phoebus", "codex@whoart", "ping?", kind="ask", now=hub.clock())
    hub.send(ask)
    got = hub.inbox("codex@whoart")["items"]
    assert got[0]["env"]["id"] == ask["id"]
    ans = make("codex@whoart", "claude-code/4936@phoebus", "pong", kind="answer",
               in_reply_to=ask["id"], now=hub.clock())
    hub.send(ans)
    st = hub.status(ask["id"])
    assert st["state"] == "answered" and st["acked_by"] == "codex@whoart"
    assert [r["state"] for r in st["receipts"]] == ["accepted", "answered"]
    assert all(r["verified"] for r in st["receipts"])
    back = hub.inbox("claude-code/4936@phoebus")["items"]
    assert back[0]["env"]["in_reply_to"] == ask["id"]
    assert "answering " + ask["id"] in back[0]["turn"]


def test_model_lane_reply_comes_back_as_an_answer_and_never_loops():
    calls = []

    def model(env, turn):
        calls.append(env["id"])
        return {"pushed": True, "verified": True, "reply": "pong from gemma"}
    hub = _hub({"ollama": model, "codex": model})
    ask = make("claude-app", "ollama:gemma4:e2b@blade", "ping", kind="ask", now=hub.clock())
    out = hub.send(ask)
    assert out["state"] == "answered"
    back = hub.inbox("claude-app")["items"]
    assert back[0]["env"]["kind"] == "answer" and back[0]["env"]["text"] == "pong from gemma"
    assert back[0]["env"]["from"] == "ollama:gemma4:e2b@blade"
    # model to model: the reply is pushed once and never answered again
    hub.send(make("ollama", "codex", "hello", now=hub.clock()))
    assert len(calls) == 3

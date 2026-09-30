import base64
import hashlib
import hmac
import json


from nougen_shards.wake.chatgpt_transports import (
    FileSubscriptionStore, FutureMCPNativeWakeTransport, MCPEventSubscription,
    WakeEnvelope, wake_envelope_from_relay_id,
)

RELAY_ID = "20260930T000000Z__test__mcp-events"
SECRET = "whsec_" + base64.b64encode(b"unit-test-signing-key").decode()


class Store:
    def __init__(self, subs):
        self.subs, self.gone = list(subs), []

    def active(self):
        return [s for s in self.subs if s.subscription_id not in self.gone]

    def mark_gone(self, sid):
        self.gone.append(sid)


class Recorder:
    def __init__(self, *codes):
        self.codes, self.calls = list(codes), []

    def __call__(self, url, headers, body):
        self.calls.append((url, headers, body))
        return self.codes.pop(0) if self.codes else 200


def sub(i="sub_1"):
    return MCPEventSubscription(i, f"https://example.invalid/{i}", SECRET)


def transport(sender, subs=None, sleeps=None):
    return FutureMCPNativeWakeTransport(
        store=Store(subs if subs is not None else [sub()]), sender=sender,
        sleep=(sleeps.append if sleeps is not None else lambda _: None), clock=lambda: 1_790_000_000)


def test_signature_is_standard_webhooks_v1():
    rec = Recorder(200)
    transport(rec).notify(wake_envelope_from_relay_id(RELAY_ID))
    _, h, body = rec.calls[0]
    key = base64.b64decode(SECRET[6:])
    want = "v1," + base64.b64encode(hmac.new(
        key, f"{h['webhook-id']}.{h['webhook-timestamp']}.".encode() + body, hashlib.sha256).digest()).decode()
    assert h["webhook-signature"] == want
    assert h["X-MCP-Subscription-Id"] == "sub_1"


def test_body_is_the_minimal_envelope_only():
    rec = Recorder(200)
    transport(rec).notify(wake_envelope_from_relay_id(RELAY_ID, priority="high"))
    body = json.loads(rec.calls[0][2])
    assert set(body) == {"eventId", "type", "data"}
    assert body["data"] == WakeEnvelope(RELAY_ID, "high").to_dict()


def test_event_id_is_stable_across_transports():
    e = wake_envelope_from_relay_id(RELAY_ID)
    assert FutureMCPNativeWakeTransport.event_id(e) == FutureMCPNativeWakeTransport.event_id(e)


def test_2xx_is_receipt_and_repeat_notify_is_suppressed():
    rec = Recorder(202)
    t = transport(rec)
    e = wake_envelope_from_relay_id(RELAY_ID)
    r1, r2 = t.notify(e), t.notify(e)
    assert (r1.delivered, r1.status) == (True, "sent")
    assert r1.transport_metadata["receipt_only"] is True
    assert r2.status == "duplicate_suppressed" and len(rec.calls) == 1


def test_410_is_not_retried_and_drops_the_subscription():
    rec, store = Recorder(410), Store([sub()])
    t = FutureMCPNativeWakeTransport(store=store, sender=rec, sleep=lambda _: None)
    r = t.notify(wake_envelope_from_relay_id(RELAY_ID))
    assert len(rec.calls) == 1 and store.gone == ["sub_1"]
    assert r.delivered is False and "gone" in r.detail


def test_413_is_not_retried():
    rec = Recorder(413)
    r = transport(rec).notify(wake_envelope_from_relay_id(RELAY_ID))
    assert len(rec.calls) == 1 and r.delivered is False


def test_transient_failure_retries_with_backoff_then_succeeds():
    rec, sleeps = Recorder(500, 200), []
    r = transport(rec, sleeps=sleeps).notify(wake_envelope_from_relay_id(RELAY_ID))
    assert r.delivered and len(rec.calls) == 2 and sleeps == [0.5]
    # same webhook-id on the retry: the receiver can dedupe
    assert rec.calls[0][1]["webhook-id"] == rec.calls[1][1]["webhook-id"]


def test_persistent_failure_is_bounded():
    rec = Recorder(500, 500, 500, 500, 500)
    r = transport(rec).notify(wake_envelope_from_relay_id(RELAY_ID))
    assert len(rec.calls) == 3 and (r.delivered, r.status) == (False, "error")


def test_sender_exception_counts_as_retriable_failure():
    def boom(*a):
        raise OSError("down")
    r = transport(boom).notify(wake_envelope_from_relay_id(RELAY_ID))
    assert r.delivered is False


def test_no_subscription_is_unconfigured_and_plan_stays_unresolved():
    t = transport(Recorder(), subs=[])
    assert t.notify(wake_envelope_from_relay_id(RELAY_ID)).status == "unconfigured"
    caps = t.capabilities()
    assert caps["configured"] is False and caps["plan_eligible"] is None


def test_secret_never_appears_in_repr_or_result():
    r = transport(Recorder(200)).notify(wake_envelope_from_relay_id(RELAY_ID))
    assert SECRET not in repr(sub()) and SECRET not in json.dumps(r.to_dict(), default=str)


def test_file_store_resolves_secret_from_keymaker_name_and_persists_gone(tmp_path):
    f = tmp_path / "subs.json"
    f.write_text(json.dumps([{"subscription_id": "s1", "callback_url": "https://x.invalid/1", "secret_key": "K1"},
                             {"subscription_id": "s2", "callback_url": "https://x.invalid/2", "secret_key": "MISSING"}]))
    store = FileSubscriptionStore(str(f), secret_getter=lambda k: SECRET if k == "K1" else None)
    assert [s.subscription_id for s in store.active()] == ["s1"]  # unresolved secret => skipped
    store.mark_gone("s1")
    assert store.active() == []
    assert "secret" not in f.read_text().lower().replace("secret_key", "")


def test_broken_store_is_unconfigured_not_a_crash(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("{not json")
    assert FileSubscriptionStore(str(f), secret_getter=lambda k: SECRET).active() == []

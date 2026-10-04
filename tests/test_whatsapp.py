import hashlib
import hmac
import json

import pytest

from nougen_shards import whatsapp as wa

SECRET = "test-app-secret"
NOW = 1_800_000_000


def _payload(ts=NOW, frm="15550001111", text="hi"):
    return {"entry": [{"changes": [{"value": {"messages": [
        {"from": frm, "id": "wamid.1", "timestamp": str(ts),
         "type": "text", "text": {"body": text}}]}}]}]}


def _sign(body):
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def test_challenge_ok_and_bad():
    p = {"hub.mode": "subscribe", "hub.verify_token": "t", "hub.challenge": "42"}
    assert wa.verify_challenge(p, "t") == "42"
    assert wa.verify_challenge(p, "wrong") is None


def test_signature_rejects_tamper_and_missing():
    body = json.dumps(_payload()).encode()
    assert wa.verify_signature(body, _sign(body), SECRET)
    assert not wa.verify_signature(body + b" ", _sign(body), SECRET)
    assert not wa.verify_signature(body, "", SECRET)


def test_webhook_delivers_and_opens_window():
    body = json.dumps(_payload()).encode()
    got, w = [], wa.WindowTracker(clock=lambda: NOW + 60)
    assert wa.handle_webhook(body, _sign(body), SECRET, w, got.append) == 1
    assert got[0].text == "hi" and got[0].wa_id == "15550001111"
    assert w.is_open("15550001111")


def test_bad_signature_delivers_nothing():
    body = json.dumps(_payload()).encode()
    got = []
    with pytest.raises(PermissionError):
        wa.handle_webhook(body, "sha256=00", SECRET, wa.WindowTracker(), got.append)
    assert got == []


def test_send_text_blocked_outside_window_then_allowed_inside():
    sent = []
    def tr(method, url, headers, data):
        sent.append((method, url, headers, json.loads(data)))
        return {"messages": [{"id": "ok"}]}
    clock = {"t": NOW + 60}
    w = wa.WindowTracker(clock=lambda: clock["t"])
    c = wa.WhatsAppClient("KEY", "PNID", transport=tr, windows=w)
    with pytest.raises(wa.WindowClosed):
        c.send_text("15550001111", "x")
    w.record(wa.parse_inbound(_payload())[0])
    c.send_text("15550001111", "yo")
    assert sent[0][1].endswith("/PNID/messages") and sent[0][2]["X-API-Key"] == "KEY"
    clock["t"] = NOW + wa.SERVICE_WINDOW_S + 1
    with pytest.raises(wa.WindowClosed):
        c.send_text("15550001111", "late")
    c.send_template("15550001111", "hello")  # templates ignore the window
    assert sent[-1][3]["type"] == "template"

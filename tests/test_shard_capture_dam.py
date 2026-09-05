"""Acceptance tests A-I for the temporal shard capture dam (leg 20260904T040803Z).

The metaphor the leg asks us to prove: close the reservoir intake, submit a
shard, watch it accumulate behind the dam; reopen intake, watch the spillway
release it exactly once; confirm dedupe prevents doubles and the ACK closes
the event.
"""
from __future__ import annotations

import json

import pytest

from nougen_shards.dam import envelope as env_mod
from nougen_shards.dam.dam import Dam
from nougen_shards.dam.gate import classify
from nougen_shards.dam.spillway import Spillway
from nougen_shards.dam.store import LocalDamStore

KEY = b"\x11" * 32
HMAC_KEY = b"\x22" * 32
PAYLOAD = {"title": "Vol 3 SDX victory", "content": "canon body", "tags": ["canon"]}


@pytest.fixture()
def store(tmp_path):
    return LocalDamStore(tmp_path / "dam")


@pytest.fixture()
def dam(store):
    return Dam(store, key=KEY, lane="chatgpt-app", hmac_key=HMAC_KEY)


class Reservoir:
    """Primary shard API with an intake that can be closed."""

    def __init__(self, status=200):
        self.status = status
        self.open = True
        self.writes = []
        self.seen_ids = set()

    def __call__(self, operation, payload):
        if not self.open:
            return {"status": 503, "error": "intake closed"}
        key = json.dumps(payload, sort_keys=True)
        if key in self.seen_ids:
            return {"status": 409, "error": "duplicate"}
        self.seen_ids.add(key)
        self.writes.append((operation, payload))
        return {"status": self.status, "shard_ref": f"shard:{len(self.writes)}",
                "db_index": 2}


# --- A: outage spools, receipt is truthful ------------------------------
def test_A_outage_spools_and_receipt_never_claims_captured(dam, store):
    res = Reservoir()
    res.open = False
    receipt = dam.submit("shards_capture", PAYLOAD, res, local_retries=0)

    assert receipt["queued_fallback"] is True
    assert receipt["durable"] is True
    assert receipt["captured"] is False, "the dam must never claim capture"
    assert receipt["state"] == "DAM_PENDING"
    assert receipt["replay_required"] is True
    assert len(store.list_pending()) == 1


# --- B: healthy primary never touches the dam ---------------------------
def test_B_healthy_primary_writes_nothing_to_dam(dam, store):
    receipt = dam.submit("shards_capture", PAYLOAD, Reservoir())
    assert receipt["captured"] is True
    assert receipt["queued_fallback"] is False
    assert store.list_pending() == []


# --- C: same failed request twice is one event --------------------------
def test_C_duplicate_submission_is_one_event(dam, store):
    res = Reservoir()
    res.open = False
    r1 = dam.submit("shards_capture", PAYLOAD, res, local_retries=0)
    r2 = dam.submit("shards_capture", PAYLOAD, res, local_retries=0)
    assert r1["event_id"] == r2["event_id"]
    assert len(store.list_pending()) == 1, "identity is the request, not the clock"


# --- D: recovery drains exactly one shard and acks ----------------------
def test_D_drain_creates_exactly_one_shard_and_acks(dam, store):
    res = Reservoir()
    res.open = False
    receipt = dam.submit("shards_capture", PAYLOAD, res, local_retries=0)

    res.open = True
    spill = Spillway(store, key=KEY, hmac_key=HMAC_KEY, required_green=2)
    # One green probe is not enough by design.
    assert spill.drain(res, probe=lambda: True)["drained"] == 0
    summary = spill.drain(res, probe=lambda: True)

    assert summary["drained"] == 1
    assert len(res.writes) == 1
    assert res.writes[0][1] == PAYLOAD, "payload must survive the round trip"
    assert store.is_acked(receipt["event_id"], "") or store.list_pending() == []
    assert store.list_pending() == []

    # Draining again must not replay it.
    assert spill.drain(res, probe=lambda: True)["drained"] == 0
    assert len(res.writes) == 1


# --- E: tampered payload quarantines, never replays ---------------------
def test_E_tampered_ciphertext_quarantines(dam, store, tmp_path):
    res = Reservoir()
    res.open = False
    dam.submit("shards_capture", PAYLOAD, res, local_retries=0)

    p = next((tmp_path / "dam" / "pending").rglob("*.json"))
    env = json.loads(p.read_text())
    raw = bytearray(env["payload_ciphertext"].encode())
    raw[5] = raw[5] ^ 0x01 if raw[5] != 0x41 else 0x42
    env["payload_ciphertext"] = raw.decode(errors="ignore")
    p.write_text(json.dumps(env))

    res.open = True
    spill = Spillway(store, key=KEY, hmac_key=HMAC_KEY, required_green=1)
    summary = spill.drain(res, probe=lambda: True)

    assert summary["quarantined"] == 1
    assert summary["drained"] == 0
    assert res.writes == [], "tampered events must never reach the reservoir"


def test_E2_bad_hmac_quarantines(store):
    env = env_mod.seal("shards_capture", PAYLOAD, key=KEY, lane="l",
                       hmac_key=HMAC_KEY)
    env["ingress_sig"] = "0" * 64
    store.put_pending(env)
    res = Reservoir()
    spill = Spillway(store, key=KEY, hmac_key=HMAC_KEY, required_green=1)
    assert spill.drain(res, probe=lambda: True)["quarantined"] == 1
    assert res.writes == []


# --- F/G: forbidden operations never enter the dam ----------------------
@pytest.mark.parametrize("op", ["shards_forget", "vault_put", "keymaker_ingest"])
def test_FG_forbidden_operations_never_spool(dam, store, op):
    res = Reservoir()
    res.open = False
    receipt = dam.submit(op, PAYLOAD, res, local_retries=0)
    assert receipt["queued_fallback"] is False
    assert receipt["durable"] is False
    assert store.list_pending() == []

    with pytest.raises(env_mod.NotSpoolable):
        env_mod.seal(op, PAYLOAD, key=KEY, lane="l")


# --- H: restart does not lose queued writes -----------------------------
def test_H_queue_survives_restart(tmp_path):
    root = tmp_path / "dam"
    d1 = Dam(LocalDamStore(root), key=KEY, lane="l", hmac_key=HMAC_KEY)
    res = Reservoir()
    res.open = False
    d1.submit("shards_capture", PAYLOAD, res, local_retries=0)

    # New process, same durable backing.
    reborn = LocalDamStore(root)
    assert len(reborn.list_pending()) == 1
    res.open = True
    spill = Spillway(reborn, key=KEY, hmac_key=HMAC_KEY, required_green=1)
    assert spill.drain(res, probe=lambda: True)["drained"] == 1


# --- I: both down is a truthful hard failure ----------------------------
def test_I_dam_failure_surfaces_hard_not_silent(store):
    class Broken(LocalDamStore):
        def put_pending(self, env):
            raise OSError("dam backend unreachable")

    d = Dam(Broken(store.root), key=KEY, lane="l", hmac_key=HMAC_KEY)
    res = Reservoir()
    res.open = False
    with pytest.raises(OSError):
        d.submit("shards_capture", PAYLOAD, res, local_retries=0)


def test_I2_nonretryable_is_hard_failure_not_queued(dam, store):
    def unauthorized(op, payload):
        return {"status": 401, "error": "unauthorized"}

    receipt = dam.submit("shards_capture", PAYLOAD, unauthorized)
    assert receipt["durable"] is False
    assert receipt["queued_fallback"] is False
    assert receipt["terminal"] is True
    assert store.list_pending() == [], "auth failures must not fill the dam"


# --- gate policy --------------------------------------------------------
@pytest.mark.parametrize("status,divert", [
    (502, True), (503, True), (504, True), (500, True),
    (400, False), (401, False), (403, False), (404, False), (409, False),
])
def test_gate_classification(status, divert):
    assert classify(status=status, retries_exhausted=True).divert is divert


def test_gate_429_needs_local_retries_first():
    assert classify(status=429, retries_exhausted=False).divert is False
    assert classify(status=429, retries_exhausted=True).divert is True


def test_gate_timeout_needs_local_retries_first():
    err = TimeoutError("read timed out")
    assert classify(error=err, retries_exhausted=False).divert is False
    assert classify(error=err, retries_exhausted=True).divert is True


# --- envelope properties ------------------------------------------------
def test_no_plaintext_content_in_stored_object(dam, store, tmp_path):
    res = Reservoir()
    res.open = False
    dam.submit("shards_capture", PAYLOAD, res, local_retries=0)
    blob = next((tmp_path / "dam" / "pending").rglob("*.json")).read_text()
    assert "canon body" not in blob
    assert "Vol 3 SDX victory" not in blob


def test_amend_without_identity_is_quarantined(store):
    env = env_mod.seal("shards_amend", {"content": "x"}, key=KEY, lane="l",
                       hmac_key=HMAC_KEY)
    store.put_pending(env)
    res = Reservoir()
    spill = Spillway(store, key=KEY, hmac_key=HMAC_KEY, required_green=1)
    summary = spill.drain(res, probe=lambda: True)
    assert summary["quarantined"] == 1
    assert res.writes == []


def test_peek_never_decrypts(dam, store):
    res = Reservoir()
    res.open = False
    dam.submit("shards_capture", PAYLOAD, res, local_retries=0)
    for row in dam.peek():
        assert "content" not in json.dumps(row)
        assert "canon body" not in json.dumps(row)


def test_gauge_reports_backpressure(dam, store):
    res = Reservoir()
    res.open = False
    dam.submit("shards_capture", PAYLOAD, res, local_retries=0)
    dam.submit("shards_capture", {"title": "b", "content": "c"}, res,
               local_retries=0)
    g = dam.status()
    assert g["queued"] == 2
    assert g["by_operation"]["shards_capture"] == 2
    assert g["bytes"] > 0

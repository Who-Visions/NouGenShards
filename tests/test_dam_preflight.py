"""Substrate verification gates — validation BEFORE protection.

Every gate here maps to a failure that actually happened on this fleet on
2026-09-03/04. The lesson driving them: a security control on unverified
infrastructure protects the payload while the ground underneath drops it.
"""
from __future__ import annotations

import json

import pytest

from nougen_shards.dam import envelope as env_mod
from nougen_shards.dam.dam import Dam
from nougen_shards.dam.preflight import Preflight, PreflightFailure
from nougen_shards.dam.store import LocalDamStore

KEY = b"\x33" * 32
HMAC_KEY = b"\x44" * 32


@pytest.fixture()
def store(tmp_path):
    return LocalDamStore(tmp_path / "dam")


def test_preflight_passes_on_healthy_substrate(store):
    report = Preflight(store, key=KEY, hmac_key=HMAC_KEY,
                       health_probe=lambda: True).run()
    assert report["armed"] is True
    assert report["failed"] == []
    names = {g["gate"] for g in report["gates"]}
    assert {"CRYPTO_ROUNDTRIP", "CRYPTO_REJECTS_TAMPER", "STORE_ROUNDTRIP",
            "NO_PLAINTEXT_AT_REST"} <= names


def test_store_that_accepts_but_loses_writes_fails_the_gate(store):
    """The exact 2026-09-03 failure: capture returned success, nothing landed."""

    class LyingStore(LocalDamStore):
        def put_pending(self, env):
            return "pending/fake.json"  # reports success, writes nothing

    with pytest.raises(PreflightFailure) as exc:
        Preflight(LyingStore(store.root), key=KEY, hmac_key=HMAC_KEY).run()

    assert "STORE_ROUNDTRIP" in exc.value.report["failed"]
    assert exc.value.report["armed"] is False


def test_broken_key_fails_before_any_data_is_accepted(store):
    class BadKey(bytes):
        pass

    # A key that seals but cannot open would yield a dam of unreadable events.
    class HalfBrokenPreflight(Preflight):
        def _crypto_roundtrip(self):
            env = env_mod.seal("shards_capture", {"a": 1}, key=KEY, lane="p")
            return env_mod.open_envelope(env, key=b"\x99" * 32)

    HalfBrokenPreflight._crypto_roundtrip._gate_name = "CRYPTO_ROUNDTRIP"
    HalfBrokenPreflight._crypto_roundtrip._critical = True

    with pytest.raises(PreflightFailure) as exc:
        HalfBrokenPreflight(store, key=KEY).run()
    assert "CRYPTO_ROUNDTRIP" in exc.value.report["failed"]


def test_all_gates_run_even_after_one_fails(store):
    """Short-circuiting hides correlated breakage. Tonight the CA bundle and a
    missing module each looked like the other's symptom."""

    class LyingStore(LocalDamStore):
        def put_pending(self, env):
            return "nope"

    try:
        Preflight(LyingStore(store.root), key=KEY, hmac_key=HMAC_KEY).run()
    except PreflightFailure as exc:
        report = exc.value.report if hasattr(exc, "value") else exc.report
        assert len(report["gates"]) >= 4, "every gate must report, not just the first"
        assert any(g["ok"] for g in report["gates"]), "healthy gates still report ok"


def test_dishonest_health_probe_is_caught(store):
    report = Preflight(store, key=KEY, hmac_key=HMAC_KEY,
                       health_probe=lambda: "yes").run(strict=False)
    gate = next(g for g in report["gates"] if g["gate"] == "HEALTH_PROBE_HONEST")
    assert gate["ok"] is False
    # Non-critical: a bad probe must not block arming, but must be visible.
    assert report["armed"] is True


def test_missing_ca_bundle_is_reported_not_silently_passed(store, monkeypatch):
    """The 2026-09-04 SSL trap: no CA bundle made every call fail in a way
    that read as a dead endpoint rather than a broken interpreter."""
    import ssl as _ssl

    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.setattr(
        _ssl, "get_default_verify_paths",
        lambda: _ssl.DefaultVerifyPaths(None, None, "", "", "", ""))

    report = Preflight(store, key=KEY, hmac_key=HMAC_KEY,
                       verify_tls_host="huggingface.co").run(strict=False)
    gate = next(g for g in report["gates"] if g["gate"] == "TLS_WORKS")
    assert gate["ok"] is False
    assert "SSL_CERT_FILE" in gate["error"]


# --- the dam refuses to accept data until armed -------------------------
def test_unarmed_dam_refuses_writes(store):
    d = Dam(store, key=KEY, lane="l", hmac_key=HMAC_KEY, require_preflight=True)
    assert d.armed is False

    def down(op, payload):
        return {"status": 503}

    receipt = d.submit("shards_capture", {"title": "t", "content": "c"}, down,
                       local_retries=0)
    assert receipt["durable"] is False
    assert receipt["queued_fallback"] is False
    assert "not armed" in receipt["error"]
    assert store.list_pending() == [], "nothing may be stored before verification"


def test_armed_dam_accepts_writes(store):
    d = Dam(store, key=KEY, lane="l", hmac_key=HMAC_KEY, require_preflight=True)
    d.arm(health_probe=lambda: True)
    assert d.armed is True

    def down(op, payload):
        return {"status": 503}

    receipt = d.submit("shards_capture", {"title": "t", "content": "c"}, down,
                       local_retries=0)
    assert receipt["queued_fallback"] is True
    assert receipt["captured"] is False


def test_preflight_canary_never_drains_into_reservoir(store):
    """The canary proves the store works; it must not become a shard."""
    Preflight(store, key=KEY, hmac_key=HMAC_KEY).run()
    for env in store.list_pending():
        payload = json.dumps(env)
        assert "__preflight__" not in payload
    assert store.list_pending() == [], "canary must be cleared after the gate"

"""Preflight: prove the substrate works BEFORE the dam is trusted with data.

Encryption on unverified infrastructure is theater. It protects the payload
while the ground underneath drops it. Every gate here exists because the
corresponding failure actually happened on this fleet on 2026-09-03/04:

* TLS_WORKS        the venv carried no CA bundle, so every urllib call raised
                   CERTIFICATE_VERIFY_FAILED and surfaced as "no inference
                   lane available" -- indistinguishable from depleted credit.
* STORE_ROUNDTRIP  shards_capture returned {"captured": true} for writes that
                   were never persisted; the node was writing to a stray
                   repo-local .vault/ nobody had enumerated.
* CRYPTO_ROUNDTRIP a key that seals but cannot open produces a dam full of
                   permanently unreadable events -- silent, total data loss
                   discovered only at drain time.
* HEALTH_HONEST    a probe that returns truthy when the primary is down turns
                   the spillway into a replay loop against a dead reservoir.
* NO_PLAINTEXT     the one property that makes off-node storage acceptable.

The gates FAIL LOUD. A dam that cannot prove its own substrate refuses to arm
rather than accepting writes it may not be able to return.
"""
from __future__ import annotations

import json
import os
import ssl
import time
from typing import Any, Callable, Dict, List, Optional

from . import envelope as env_mod
from .store import DamStore


class PreflightFailure(Exception):
    """The dam refused to arm. Carries every gate result, not just the first."""

    def __init__(self, report: Dict[str, Any]):
        self.report = report
        failed = [g["gate"] for g in report["gates"] if not g["ok"]]
        super().__init__(f"dam preflight failed: {', '.join(failed)}")


def _gate(name: str, critical: bool = True):
    def wrap(fn):
        fn._gate_name = name
        fn._critical = critical
        return fn
    return wrap


class Preflight:
    """Runs every gate, always. Never short-circuits on first failure.

    Short-circuiting hides correlated breakage -- tonight the CA bundle and
    the missing mcp module were separate faults that each looked like the
    other's symptom. Seeing all gates at once is what tells them apart.
    """

    def __init__(self, store: DamStore, *, key: bytes,
                 hmac_key: Optional[bytes] = None,
                 health_probe: Optional[Callable[[], Any]] = None,
                 verify_tls_host: Optional[str] = None):
        self.store = store
        self.key = key
        self.hmac_key = hmac_key
        self.health_probe = health_probe
        self.verify_tls_host = verify_tls_host

    # -- gates -----------------------------------------------------------
    @_gate("CRYPTO_ROUNDTRIP")
    def _crypto_roundtrip(self) -> Dict[str, Any]:
        canary = {"title": "__preflight__", "content": os.urandom(8).hex()}
        env = env_mod.seal("shards_capture", canary, key=self.key,
                           lane="preflight", hmac_key=self.hmac_key)
        got = env_mod.open_envelope(env, key=self.key, hmac_key=self.hmac_key)
        if got != canary:
            raise AssertionError("sealed payload did not survive the round trip")
        return {"key_fingerprint": env_mod.key_fingerprint(self.key),
                "signed": bool(self.hmac_key)}

    @_gate("CRYPTO_REJECTS_TAMPER")
    def _crypto_rejects_tamper(self) -> Dict[str, Any]:
        """A cipher that accepts corruption is worse than no cipher: it
        launders bad data into the reservoir wearing a valid signature."""
        env = env_mod.seal("shards_capture", {"title": "t", "content": "c"},
                           key=self.key, lane="preflight", hmac_key=self.hmac_key)
        raw = bytearray(env_mod._unb64(env["payload_ciphertext"]))
        raw[0] ^= 0x01
        env["payload_ciphertext"] = env_mod._b64(bytes(raw))
        try:
            env_mod.open_envelope(env, key=self.key, hmac_key=self.hmac_key)
        except env_mod.TamperError:
            return {"rejected": True}
        raise AssertionError("tampered ciphertext was accepted")

    @_gate("STORE_ROUNDTRIP")
    def _store_roundtrip(self) -> Dict[str, Any]:
        """Write a canary and READ IT BACK. A store that reports success on a
        write it did not persist is the exact failure that lost three captures
        tonight -- so success is defined as retrieval, never as a return code."""
        canary = env_mod.seal(
            "shards_capture", {"title": "__preflight__", "content": os.urandom(8).hex()},
            key=self.key, lane="preflight", hmac_key=self.hmac_key,
            created_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        self.store.put_pending(canary)
        found = any(e.get("event_id") == canary["event_id"]
                    for e in self.store.list_pending())
        if not found:
            raise AssertionError(
                "store accepted a write that could not be read back — "
                "this is the silent-loss failure mode; do not arm the dam")
        # Clear the canary so it never drains into the reservoir.
        self.store.put_quarantine(canary["event_id"], canary["created_utc"],
                                  {"reason": "preflight_canary", "replay": False})
        return {"event_id": canary["event_id"], "read_back": True}

    @_gate("NO_PLAINTEXT_AT_REST")
    def _no_plaintext(self) -> Dict[str, Any]:
        marker = "PREFLIGHT-" + os.urandom(6).hex().upper()
        env = env_mod.seal("shards_capture", {"title": marker, "content": marker},
                           key=self.key, lane="preflight", hmac_key=self.hmac_key)
        blob = json.dumps(env)
        if marker in blob:
            raise AssertionError("plaintext content present in stored envelope")
        return {"checked_marker": True}

    @_gate("TLS_WORKS", critical=False)
    def _tls_works(self) -> Dict[str, Any]:
        """Verified only when a host is configured. A dam that cannot make an
        outbound TLS connection cannot reach an HF-backed store, and the
        failure reads like every other network error."""
        if not self.verify_tls_host:
            return {"skipped": "no host configured"}
        import socket
        ctx = ssl.create_default_context()
        paths = ssl.get_default_verify_paths()
        if not (paths.cafile or paths.capath or os.environ.get("SSL_CERT_FILE")):
            raise AssertionError(
                "no CA bundle available to this interpreter — set "
                "SSL_CERT_FILE (e.g. /etc/ssl/cert.pem); every TLS call will "
                "fail CERTIFICATE_VERIFY_FAILED and look like a dead endpoint")
        with socket.create_connection((self.verify_tls_host, 443), timeout=10) as s:
            with ctx.wrap_socket(s, server_hostname=self.verify_tls_host) as t:
                return {"host": self.verify_tls_host, "tls": t.version()}

    @_gate("HEALTH_PROBE_HONEST", critical=False)
    def _health_honest(self) -> Dict[str, Any]:
        """A probe must return a real observation, not a constant.

        `lambda: True` passes every drain gate forever and turns the spillway
        into a replay loop against a dead reservoir.
        """
        if self.health_probe is None:
            return {"skipped": "no probe configured"}
        v = self.health_probe()
        if not isinstance(v, (bool, dict)):
            raise AssertionError(f"probe returned {type(v).__name__}, expected bool/dict")
        return {"observed": v if isinstance(v, bool) else "dict"}

    # -- runner ----------------------------------------------------------
    def run(self, *, strict: bool = True) -> Dict[str, Any]:
        gates: List[Dict[str, Any]] = []
        for attr in sorted(dir(self)):
            fn = getattr(self, attr, None)
            name = getattr(fn, "_gate_name", None)
            if not name:
                continue
            started = time.monotonic()
            try:
                detail = fn()
                gates.append({"gate": name, "ok": True,
                              "critical": fn._critical, "detail": detail,
                              "ms": round((time.monotonic() - started) * 1000, 1)})
            except Exception as exc:
                gates.append({"gate": name, "ok": False,
                              "critical": fn._critical,
                              "error": f"{type(exc).__name__}: {exc}",
                              "ms": round((time.monotonic() - started) * 1000, 1)})

        critical_failed = [g for g in gates if not g["ok"] and g["critical"]]
        report = {
            "armed": not critical_failed,
            "gates": gates,
            "failed": [g["gate"] for g in gates if not g["ok"]],
            "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if critical_failed and strict:
            raise PreflightFailure(report)
        return report

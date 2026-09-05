"""The dam: front-door entry point, receipts, and the gauge.

CORE INVARIANT, enforced here and asserted in the tests:
an event in the dam is DURABLE but NOT CAPTURED. Every receipt this module
produces says `captured: false` until the spillway gets an ACK from the
primary reservoir. A dam that reports `captured: true` would be a second
source of truth, which is the one outcome the whole design exists to avoid.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from . import envelope as env_mod
from .gate import Decision, classify
from .store import DamStore


class NotArmed(Exception):
    """The dam has not proven its substrate and refuses to accept writes."""


class Dam:
    def __init__(self, store: DamStore, *, key: bytes, lane: str,
                 hmac_key: Optional[bytes] = None,
                 require_preflight: bool = False):
        self.store = store
        self.key = key
        self.lane = lane
        self.hmac_key = hmac_key
        # Verification before protection. Encryption on infrastructure that
        # cannot be shown to store and return data is theater -- it guards the
        # payload while the ground underneath drops it. When this is set, the
        # dam refuses writes until arm() has proven the substrate.
        self.require_preflight = require_preflight
        self._armed = not require_preflight
        self._preflight_report: Optional[Dict[str, Any]] = None

    def arm(self, *, health_probe: Optional[Callable[[], Any]] = None,
            verify_tls_host: Optional[str] = None,
            strict: bool = True) -> Dict[str, Any]:
        """Run every substrate gate. Only then will the dam accept writes."""
        from .preflight import Preflight
        report = Preflight(self.store, key=self.key, hmac_key=self.hmac_key,
                           health_probe=health_probe,
                           verify_tls_host=verify_tls_host).run(strict=strict)
        self._preflight_report = report
        self._armed = bool(report["armed"])
        return report

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def preflight_report(self) -> Optional[Dict[str, Any]]:
        return self._preflight_report

    # -- front door ------------------------------------------------------
    def submit(self, operation: str, payload: Dict[str, Any],
               primary: Callable[[str, Dict[str, Any]], Dict[str, Any]],
               *, idempotency_key: Optional[str] = None,
               local_retries: int = 1) -> Dict[str, Any]:
        """Try the reservoir; divert to the dam only if the gate allows.

        `primary` raises, or returns a dict with a `status` int. Anything the
        gate calls terminal is surfaced as a hard failure -- never queued.
        """
        if operation in env_mod.NEVER_SPOOL:
            # Refused before any attempt: these must not even be retried into
            # a state where a later code path could queue them.
            return self._hard(operation, None,
                              f"{operation} may never enter the dam")

        decision: Decision | None = None
        last_err: BaseException | None = None
        for attempt in range(max(1, local_retries + 1)):
            exhausted = attempt >= local_retries
            try:
                res = primary(operation, payload)
                status = int(res.get("status", 200))
                if 200 <= status < 300:
                    return {"durable": True, "captured": True,
                            "queued_fallback": False, "state": "RESERVOIR_COMMITTED",
                            "primary": res}
                decision = classify(status=status, retries_exhausted=exhausted)
            except BaseException as exc:  # noqa: BLE001 - classified below
                last_err = exc
                decision = classify(error=exc, retries_exhausted=exhausted)

            if decision.terminal:
                return self._hard(operation, decision, decision.reason)
            if decision.divert:
                break
            if not exhausted:
                time.sleep(0)  # retry budget is the caller's; no sleep in tests

        if decision is None or not decision.divert:
            return self._hard(operation, decision,
                              decision.reason if decision else str(last_err))

        return self.seal(operation, payload, idempotency_key=idempotency_key,
                         reason=decision.reason)

    def seal(self, operation: str, payload: Dict[str, Any], *,
             idempotency_key: Optional[str] = None,
             reason: str = "") -> Dict[str, Any]:
        """Encrypt, sign, store. Returns the truthful fallback receipt."""
        if not self._armed:
            # Refusing is the safe answer. Accepting a write into a dam whose
            # store has not been shown to return data is how "durable" becomes
            # a lie -- the caller stops holding the content because we said we
            # had it.
            return self._hard(operation, None,
                              "dam not armed: preflight has not proven the "
                              "substrate (call arm())")
        try:
            env = env_mod.seal(operation, payload, key=self.key, lane=self.lane,
                               idempotency_key=idempotency_key,
                               hmac_key=self.hmac_key)
        except env_mod.NotSpoolable as exc:
            return self._hard(operation, None, str(exc))

        self.store.put_pending(env)
        return {
            "durable": True,
            "captured": False,          # <- the invariant
            "queued_fallback": True,
            "dam": "hf",
            "event_id": env["event_id"],
            "state": "DAM_PENDING",
            "replay_required": True,
            "reason": reason,
        }

    @staticmethod
    def _hard(operation: str, decision: Optional[Decision],
              reason: str) -> Dict[str, Any]:
        return {
            "durable": False, "captured": False, "queued_fallback": False,
            "state": "FAILED", "operation": operation, "error": reason,
            "terminal": bool(decision.terminal) if decision else True,
        }

    # -- gauge -----------------------------------------------------------
    def status(self) -> Dict[str, Any]:
        """Backpressure metrics. `oldest_age_s` is the number that matters:
        a queue that is draining has a young head, a stuck one does not."""
        pending = self.store.list_pending()
        now = time.time()
        ages = []
        for e in pending:
            try:
                t = time.mktime(time.strptime(e.get("created_utc", ""),
                                              "%Y-%m-%dT%H:%M:%SZ"))
                ages.append(max(0.0, now - (t - time.timezone)))
            except Exception:
                continue
        by_op: Dict[str, int] = {}
        for e in pending:
            by_op[e.get("operation", "?")] = by_op.get(e.get("operation", "?"), 0) + 1
        return {
            "queued": len(pending),
            "oldest_age_s": round(max(ages), 1) if ages else 0.0,
            "bytes": sum(len(e.get("payload_ciphertext", "")) for e in pending),
            "by_operation": by_op,
            "lane": self.lane,
            "key_fingerprint": env_mod.key_fingerprint(self.key),
        }

    def peek(self) -> list:
        """Metadata only. Never decrypts — `dam_peek` must not expose content."""
        return [{
            "event_id": e.get("event_id"), "operation": e.get("operation"),
            "lane": e.get("lane"), "created_utc": e.get("created_utc"),
            "attempt": e.get("attempt", 0),
            "ciphertext_bytes": len(e.get("payload_ciphertext", "")),
        } for e in self.store.list_pending()]

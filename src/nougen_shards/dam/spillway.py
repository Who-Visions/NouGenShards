"""The spillway: releases queued events back into the reservoir.

Two rules carry most of the safety here.

1. **N consecutive green probes, not one.** A single green ping during a flap
   reopens the gates into a primary that is about to fail again, and the queue
   thrashes. The dam holds until health is *stable*.

2. **Quarantine beats guessing.** Anything that fails authentication, schema,
   or identity goes to silt and is never replayed. A payload that does not
   verify will not verify on the next attempt, and replaying it blindly is how
   corrupted content reaches the authoritative store.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from . import envelope as env_mod
from .store import DamStore

HealthProbe = Callable[[], bool]
Replay = Callable[[str, Dict[str, Any]], Dict[str, Any]]


class Spillway:
    def __init__(self, store: DamStore, *, key: bytes,
                 hmac_key: Optional[bytes] = None,
                 required_green: int = 3, max_attempts: int = 5):
        self.store = store
        self.key = key
        self.hmac_key = hmac_key
        self.required_green = max(1, required_green)
        self.max_attempts = max_attempts
        self._green_streak = 0

    def observe_health(self, healthy: bool) -> bool:
        """Feed one probe result. True once the streak clears the threshold."""
        self._green_streak = self._green_streak + 1 if healthy else 0
        return self._green_streak >= self.required_green

    def wait_for_stable(self, probe: HealthProbe, *, interval_s: float = 0.0,
                        max_probes: int = 30) -> bool:
        for _ in range(max_probes):
            if self.observe_health(bool(probe())):
                return True
            if interval_s:
                time.sleep(interval_s)
        return False

    def drain(self, replay: Replay, *, probe: Optional[HealthProbe] = None,
              limit: Optional[int] = None) -> Dict[str, Any]:
        """Release pending events. Returns a summary fit for a relay leg."""
        if probe is not None and not self.observe_health(bool(probe())):
            return {"drained": 0, "skipped": "reservoir not stable yet",
                    "green_streak": self._green_streak,
                    "required_green": self.required_green}

        pending: List[Dict[str, Any]] = self.store.list_pending()
        if limit is not None:
            pending = pending[:limit]

        acked = duplicates = quarantined = failed = 0
        errors: List[Dict[str, str]] = []

        for env in pending:
            eid = str(env.get("event_id", ""))
            created = str(env.get("created_utc", ""))
            op = str(env.get("operation", ""))

            # Idempotency across drainer restarts: an event already acked in a
            # previous run must not be replayed a second time.
            if self.store.is_acked(eid, created):
                duplicates += 1
                continue

            try:
                payload = env_mod.open_envelope(env, key=self.key,
                                                hmac_key=self.hmac_key)
            except env_mod.TamperError as exc:
                self.store.put_quarantine(eid, created, {
                    "event_id": eid, "reason": "tamper", "detail": str(exc),
                    "quarantined_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                     time.gmtime()),
                })
                quarantined += 1
                errors.append({"event_id": eid, "error": f"quarantined: {exc}"})
                continue

            # An amendment must name what it amends. Guessing which shard to
            # rewrite is worse than not replaying at all.
            if op == "shards_amend":
                missing = [k for k in ("shard_id", "db_index", "confirm_title")
                           if not payload.get(k)]
                if missing:
                    self.store.put_quarantine(eid, created, {
                        "event_id": eid, "reason": "identity_incomplete",
                        "missing": missing,
                    })
                    quarantined += 1
                    continue

            try:
                res = replay(op, payload)
            except BaseException as exc:  # noqa: BLE001
                failed += 1
                errors.append({"event_id": eid, "error": f"{type(exc).__name__}: {exc}"})
                continue

            status = int(res.get("status", 200))
            if 200 <= status < 300:
                self.store.put_acked(eid, created, {
                    "event_id": eid, "operation": op,
                    "shard_ref": res.get("shard_ref"),
                    "db_index": res.get("db_index"),
                    "primary_status": status,
                    "acked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                })
                acked += 1
            elif status == 409:
                # Primary dedupe already holds it. That is success, not failure.
                self.store.put_acked(eid, created, {
                    "event_id": eid, "operation": op, "primary_status": 409,
                    "note": "primary reports duplicate; treated as committed",
                    "acked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                })
                duplicates += 1
            else:
                failed += 1
                errors.append({"event_id": eid, "error": f"primary HTTP {status}"})

        return {
            "drained": acked, "duplicates": duplicates,
            "quarantined": quarantined, "failed": failed,
            "remaining": len(self.store.list_pending()),
            "errors": errors[:20],
        }

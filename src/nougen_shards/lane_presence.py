"""Deterministic lane presence with a TTL, for reply routing.

A message from lane X should be answered on lane X only while X is live.
This keeps the registry tiny and pure: callers pass `now`, so behavior is
testable without a clock, a socket, or a daemon.
"""
from __future__ import annotations

from typing import Dict, Optional

DEFAULT_TTL_S = 300.0


class LanePresence:
    def __init__(self, ttl_s: float = DEFAULT_TTL_S) -> None:
        self.ttl_s = float(ttl_s)
        self._seen: Dict[str, float] = {}

    def heartbeat(self, lane: str, now: float) -> None:
        """Record that `lane` was seen at `now` (seconds since epoch)."""
        if lane:
            self._seen[lane.lower()] = float(now)

    def is_live(self, lane: str, now: float) -> bool:
        seen = self._seen.get((lane or "").lower())
        return seen is not None and (float(now) - seen) <= self.ttl_s

    def reply_target(self, envelope: dict, now: float) -> Optional[str]:
        """The lane a reply should go to, or None if it is not live.

        Prefers `origin_lane`, then `original_sender`'s lane, so a reply is
        never addressed to a lane that has gone quiet.
        """
        for key in ("origin_lane", "lane"):
            lane = envelope.get(key)
            if lane and self.is_live(lane, now):
                return lane.lower()
        return None

    def live_lanes(self, now: float) -> list:
        return sorted(name for name in self._seen if self.is_live(name, now))

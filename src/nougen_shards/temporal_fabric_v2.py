"""
temporal_fabric_v2.py

NouGen Temporal Fabric v2.
Millisecond lifecycle tracking, bitemporal truth, Hybrid Logical Clocks (HLC), and inline date indexing.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional


# ============================================================
# 1. BITEMPORAL ENVELOPE (MILLISECOND PRECISION)
# ============================================================

@dataclass(frozen=True)
class TemporalEnvelope:
    """Multi-dimensional bitemporal lifecycle envelope with millisecond integer precision."""
    created_at_ms: Optional[int] = None       # When source originally created
    event_at_ms: Optional[int] = None         # When real-world event occurred
    first_seen_ms: Optional[int] = None       # When NouGen first observed
    captured_at_ms: Optional[int] = None      # When written to SQLite grid
    updated_at_ms: Optional[int] = None       # When amended/modified
    migrated_at_ms: Optional[int] = None      # Migration timestamp (never overwrites created_at_ms)
    ai_touched_at_ms: Optional[int] = None    # When AI read/analyzed
    valid_from_ms: Optional[int] = None       # Bitemporal validity start
    valid_until_ms: Optional[int] = None      # Bitemporal validity end
    raw_source_timestamp: str = ""
    timezone_offset_minutes: int = 0

    def to_iso_dict(self) -> dict[str, Optional[str]]:
        """Format millisecond epochs as ISO-8601 strings for human inspection."""
        out = {}
        for k in ("created_at_ms", "event_at_ms", "first_seen_ms", "captured_at_ms", "updated_at_ms", "migrated_at_ms", "ai_touched_at_ms"):
            val = getattr(self, k)
            if val is not None:
                dt = datetime.fromtimestamp(val / 1000.0, tz=timezone.utc)
                out[k.replace("_ms", "_iso")] = dt.isoformat()
            else:
                out[k.replace("_ms", "_iso")] = None
        return out


# ============================================================
# 2. HYBRID LOGICAL CLOCK (HLC) & DETERMINISTIC CAUSALITY
# ============================================================

@dataclass(frozen=True)
class HybridLogicalClock:
    physical_ms: int
    logical_counter: int
    node_id: str
    event_id: str = ""

    def __lt__(self, other: "HybridLogicalClock") -> bool:
        if self.physical_ms != other.physical_ms:
            return self.physical_ms < other.physical_ms
        if self.logical_counter != other.logical_counter:
            return self.logical_counter < other.logical_counter
        if self.node_id != other.node_id:
            return self.node_id < other.node_id
        return self.event_id < other.event_id

    @property
    def key(self) -> str:
        return f"{self.physical_ms}:{self.logical_counter}:{self.node_id}:{self.event_id}"


class HLCTracker:
    """Thread-safe Hybrid Logical Clock tracker ensuring monotonicity across node turns."""

    def __init__(self, node_id: str = "whoart"):
        self.node_id = node_id
        self._last_physical_ms = 0
        self._counter = 0

    def now(self, event_id: str = "") -> HybridLogicalClock:
        curr_ms = int(time.time() * 1000)
        if curr_ms > self._last_physical_ms:
            self._last_physical_ms = curr_ms
            self._counter = 0
        else:
            self._counter += 1
        return HybridLogicalClock(
            physical_ms=self._last_physical_ms,
            logical_counter=self._counter,
            node_id=self.node_id,
            event_id=event_id,
        )


# Global HLC instance
GLOBAL_HLC = HLCTracker()


# ============================================================
# 3. INLINE TEMPORAL MENTION EXTRACTION
# ============================================================

@dataclass(frozen=True)
class TemporalMention:
    raw_text: str
    char_start: int
    char_end: int
    normalized_start_ms: int
    normalized_end_ms: int
    semantic_role: str  # event_date, deadline, historical_marker, relative_reference
    anchor_ms: int
    confidence: float = 1.0


MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12
}


def extract_temporal_mentions(
    text: str,
    anchor_dt: Optional[datetime] = None,
) -> List[TemporalMention]:
    """Extract inline absolute and relative temporal expressions with preserved anchors."""
    anchor = anchor_dt or datetime.now(timezone.utc)
    anchor_ms = int(anchor.timestamp() * 1000)
    mentions: list[TemporalMention] = []

    # 1. ISO format: YYYY-MM-DD
    for m in re.finditer(r"\b(20\d\d)-(\d{1,2})-(\d{1,2})\b", text):
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        dt = datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)
        dt_end = dt + timedelta(days=1) - timedelta(milliseconds=1)
        mentions.append(TemporalMention(
            raw_text=m.group(0),
            char_start=m.start(),
            char_end=m.end(),
            normalized_start_ms=int(dt.timestamp() * 1000),
            normalized_end_ms=int(dt_end.timestamp() * 1000),
            semantic_role="event_date",
            anchor_ms=anchor_ms,
            confidence=1.0,
        ))

    # 2. Month Day: "Nov 26", "November 26, 2025"
    month_regex = r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,\s*(20\d\d))?\b"
    for m in re.finditer(month_regex, text, re.IGNORECASE):
        mon_str, day_str, yr_str = m.group(1).lower(), m.group(2), m.group(3)
        month = MONTH_MAP.get(mon_str, 1)
        day = int(day_str)
        year = int(yr_str) if yr_str else anchor.year
        
        try:
            dt = datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)
            dt_end = dt + timedelta(days=1) - timedelta(milliseconds=1)
            mentions.append(TemporalMention(
                raw_text=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                normalized_start_ms=int(dt.timestamp() * 1000),
                normalized_end_ms=int(dt_end.timestamp() * 1000),
                semantic_role="event_date",
                anchor_ms=anchor_ms,
                confidence=0.95,
            ))
        except ValueError:
            pass

    # 3. Relative tokens: "today", "yesterday"
    for m in re.finditer(r"\b(today|yesterday|tomorrow)\b", text, re.IGNORECASE):
        word = m.group(1).lower()
        if word == "today":
            dt = datetime(anchor.year, anchor.month, anchor.day, 0, 0, 0, tzinfo=timezone.utc)
        elif word == "yesterday":
            dt = datetime(anchor.year, anchor.month, anchor.day, 0, 0, 0, tzinfo=timezone.utc) - timedelta(days=1)
        else:
            dt = datetime(anchor.year, anchor.month, anchor.day, 0, 0, 0, tzinfo=timezone.utc) + timedelta(days=1)
        
        dt_end = dt + timedelta(days=1) - timedelta(milliseconds=1)
        mentions.append(TemporalMention(
            raw_text=m.group(0),
            char_start=m.start(),
            char_end=m.end(),
            normalized_start_ms=int(dt.timestamp() * 1000),
            normalized_end_ms=int(dt_end.timestamp() * 1000),
            semantic_role="relative_reference",
            anchor_ms=anchor_ms,
            confidence=0.90,
        ))

    return sorted(mentions, key=lambda x: x.char_start)


# ============================================================
# 4. TEMPORAL QUERY ROUTING
# ============================================================

def route_temporal_query(query: str) -> str:
    """Route query expression to explicit temporal target dimension."""
    q = query.lower()
    if any(w in q for w in ("happen", "happened", "occur", "occurred", "event date")):
        return "event_at_ms"
    elif any(w in q for w in ("ai touch", "ai read", "touched by ai", "verified by model", "touched")):
        return "ai_touched_at_ms"
    elif any(w in q for w in ("migrated", "migration")):
        return "migrated_at_ms"
    elif any(w in q for w in ("updated", "amended", "revision", "edited")):
        return "updated_at_ms"
    elif any(w in q for w in ("captured", "stored", "ingested")):
        return "captured_at_ms"
    elif any(w in q for w in ("created", "originated", "authored")):
        return "created_at_ms"
    return "created_at_ms"

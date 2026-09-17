"""Millisecond temporal provenance, bitemporal events, and inline-date index."""
from __future__ import annotations

import calendar
import hashlib
import json
import re
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MONTHS = {name.casefold(): number for number, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.casefold(): number for number, name in enumerate(calendar.month_abbr) if name})
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                 "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_CLOCK_FIELDS = (
    "created_at", "source_created_at", "source_updated_at", "event_at", "first_seen_at",
    "captured_at", "updated_at", "ai_touched_at", "ingested_at", "migrated_at",
    "indexed_at", "reconciled_at", "canonicalized_at", "superseded_at", "retracted_at",
    "valid_from", "valid_to", "system_at",
)
_EVENT_TYPES = frozenset({
    "created", "source_update", "event", "first_seen", "capture", "version", "amendment",
    "ai_touch", "ingestion", "migration", "index", "reconciliation", "canonicalization",
    "supersession", "retraction",
})
_DIMENSION_TYPES = {
    "created_at": ("created",), "source_created_at": ("created",),
    "source_updated_at": ("source_update",), "event_at": ("event",),
    "first_seen_at": ("first_seen",), "captured_at": ("capture",),
    "updated_at": ("version", "amendment", "source_update"),
    "ai_touched_at": ("ai_touch",), "ingested_at": ("ingestion",),
    "migrated_at": ("migration",), "indexed_at": ("index",),
    "reconciled_at": ("reconciliation",), "canonicalized_at": ("canonicalization",),
    "superseded_at": ("supersession",), "retracted_at": ("retraction",),
    "system_at": (), "system_at_ms": (), "valid_at": (), "valid_at_ms": (),
    "event_at_ms": ("event",), "valid_to": (), "valid_to_ms": (),
    "physical_ms": (),
}


def _aware_datetime(value: str | datetime, timezone_name: Optional[str] = None) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return datetime.combine(date.fromisoformat(value), datetime_time.min, timezone.utc)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        if not timezone_name:
            raise ValueError("timezone is required for timestamps without an offset")
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed


def to_epoch_ms(value: str | datetime, timezone_name: Optional[str] = None) -> int:
    """Convert a timestamp to integer epoch milliseconds without float rounding."""
    parsed = _aware_datetime(value, timezone_name).astimezone(timezone.utc)
    delta = parsed - _EPOCH
    return delta.days * 86_400_000 + delta.seconds * 1_000 + delta.microseconds // 1_000


def from_epoch_ms(value: int) -> str:
    return (_EPOCH + timedelta(milliseconds=value)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _precision(raw: str) -> str:
    fractional = re.search(r"[T ]\d{2}:\d{2}:\d{2}\.(\d+)", raw)
    if fractional:
        digits = len(fractional.group(1))
        return "millisecond" if digits <= 3 else "microsecond"
    if re.search(r"[T ]\d{2}:\d{2}:\d{2}", raw):
        return "second"
    if re.search(r"[T ]\d{2}:\d{2}", raw):
        return "minute"
    return "date"


@dataclass(frozen=True, order=True)
class HybridLogicalClock:
    physical_ms: int
    logical_counter: int
    node_id: str
    event_id: str


def advance_hlc(now_ms: int, node_id: str, event_id: str,
                previous: Optional[HybridLogicalClock] = None,
                observed: Optional[HybridLogicalClock] = None) -> HybridLogicalClock:
    """Advance a deterministic HLC; its order does not assert wall-clock certainty."""
    physical = max(now_ms, previous.physical_ms if previous else now_ms,
                   observed.physical_ms if observed else now_ms)
    if previous and observed and physical == previous.physical_ms == observed.physical_ms:
        counter = max(previous.logical_counter, observed.logical_counter) + 1
    elif previous and physical == previous.physical_ms:
        counter = previous.logical_counter + 1
    elif observed and physical == observed.physical_ms:
        counter = observed.logical_counter + 1
    else:
        counter = 0
    return HybridLogicalClock(physical, counter, node_id, event_id)


def causal_relation(left_physical_ms: int, left_uncertainty_ms: Optional[int],
                    right_physical_ms: int, right_uncertainty_ms: Optional[int]) -> str:
    """Only infer wall-clock causality when uncertainty intervals do not overlap."""
    if left_uncertainty_ms is None or right_uncertainty_ms is None:
        return "uncertain_or_concurrent"
    if left_uncertainty_ms < 0 or right_uncertainty_ms < 0:
        raise ValueError("clock uncertainty must be non-negative")
    if left_physical_ms + left_uncertainty_ms < right_physical_ms - right_uncertainty_ms:
        return "definitely_before"
    if right_physical_ms + right_uncertainty_ms < left_physical_ms - left_uncertainty_ms:
        return "definitely_after"
    return "uncertain_or_concurrent"


@dataclass
class TemporalEnvelope:
    """Lifecycle clocks plus the raw source timestamp and its original precision."""
    artifact_id: str
    timezone: Optional[str] = None
    created_at_ms: Optional[int] = None
    source_created_at_ms: Optional[int] = None
    source_updated_at_ms: Optional[int] = None
    event_at_ms: Optional[int] = None
    first_seen_at_ms: Optional[int] = None
    captured_at_ms: Optional[int] = None
    updated_at_ms: Optional[int] = None
    ai_touched_at_ms: Optional[int] = None
    ingested_at_ms: Optional[int] = None
    migrated_at_ms: Optional[int] = None
    indexed_at_ms: Optional[int] = None
    reconciled_at_ms: Optional[int] = None
    canonicalized_at_ms: Optional[int] = None
    superseded_at_ms: Optional[int] = None
    retracted_at_ms: Optional[int] = None
    valid_from_ms: Optional[int] = None
    valid_to_ms: Optional[int] = None
    system_at_ms: Optional[int] = None
    raw_timestamps: dict[str, str] = field(default_factory=dict)
    original_precision: dict[str, str] = field(default_factory=dict)
    clock_offset_ms: Optional[int] = None
    clock_uncertainty_ms: Optional[int] = None
    drift_flag: bool = False

    def __post_init__(self) -> None:
        if not self.artifact_id:
            raise ValueError("artifact_id is required")
        if self.clock_uncertainty_ms is not None and self.clock_uncertainty_ms < 0:
            raise ValueError("clock_uncertainty_ms must be non-negative")
        if (self.valid_from_ms is not None and self.valid_to_ms is not None
                and self.valid_to_ms <= self.valid_from_ms):
            raise ValueError("valid_to_ms must be greater than valid_from_ms")

    @classmethod
    def from_timestamps(cls, artifact_id: str, values: Mapping[str, Optional[str | datetime]],
                        *, timezone_name: Optional[str] = None,
                        clock_offset_ms: Optional[int] = None,
                        clock_uncertainty_ms: Optional[int] = None,
                        drift_threshold_ms: int = 5_000) -> "TemporalEnvelope":
        kwargs: dict[str, Any] = {"artifact_id": artifact_id, "timezone": timezone_name}
        raw, precisions = {}, {}
        for field_name, value in values.items():
            if field_name not in _CLOCK_FIELDS:
                raise ValueError(f"unknown temporal clock: {field_name}")
            if value is None:
                kwargs[f"{field_name}_ms"] = None
                continue
            kwargs[f"{field_name}_ms"] = to_epoch_ms(value, timezone_name)
            raw[field_name] = value.isoformat() if isinstance(value, datetime) else value
            precisions[field_name] = _precision(raw[field_name])
        kwargs.update(raw_timestamps=raw, original_precision=precisions,
                      clock_offset_ms=clock_offset_ms,
                      clock_uncertainty_ms=clock_uncertainty_ms,
                      drift_flag=(clock_offset_ms is not None and abs(clock_offset_ms) > drift_threshold_ms))
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["normalized_timestamps"] = {
            field_name: (from_epoch_ms(getattr(self, f"{field_name}_ms"))
                         if getattr(self, f"{field_name}_ms") is not None else None)
            for field_name in _CLOCK_FIELDS
        }
        return result


def _word_count(raw: str) -> Optional[int]:
    if raw.isdigit():
        return int(raw)
    return _NUMBER_WORDS.get(raw.casefold())


def _shift_months(value: date, months: int) -> date:
    absolute = value.year * 12 + value.month - 1 + months
    year, month_zero = divmod(absolute, 12)
    month = month_zero + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _mention_role(text: str, start: int) -> str:
    prefix = text[max(0, start - 48):start].casefold()
    if re.search(r"\b(created|creation|born|authored)\b[^.]*$", prefix):
        return "created_at"
    if re.search(r"\b(happened|occurred|event)\b[^.]*$", prefix):
        return "event_at"
    if re.search(r"\b(ai|model|agent)\b[^.]*\b(read|touched|accessed)\b[^.]*$", prefix):
        return "ai_touched_at"
    if re.search(r"\b(migrated|migration)\b[^.]*$", prefix):
        return "migrated_at"
    if re.search(r"\b(updated|amended|changed)\b[^.]*$", prefix):
        return "updated_at"
    return "unspecified"


def extract_temporal_mentions(text: str, anchor: Optional[int | datetime],
                              timezone_name: str, resolver_version: str = "temporal-v2") -> list[dict[str, Any]]:
    """Extract date/time spans, retaining raw text and the relative-date anchor."""
    zone = ZoneInfo(timezone_name)
    if isinstance(anchor, int):
        anchor_dt = datetime.fromtimestamp(anchor / 1000, zone)
        anchor_ms: Optional[int] = anchor
    elif isinstance(anchor, datetime):
        anchor_dt = _aware_datetime(anchor, timezone_name).astimezone(zone)
        anchor_ms = to_epoch_ms(anchor_dt)
    else:
        anchor_dt = None
        anchor_ms = None

    patterns = [
        ("iso", re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?\b", re.I)),
        ("month_year", re.compile(r"\b([A-Za-z]{3,9})\s+(\d{4})\b")),
        ("named", re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:,?\s+(\d{4}))?\b")),
        ("relative", re.compile(r"\b(today|yesterday|tomorrow|(?:in\s+)?(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:days?|weeks?|months?|years?)(?:\s+ago|\s+from\s+now)?)\b", re.I)),
    ]
    found = []
    for kind, pattern in patterns:
        for match in pattern.finditer(text):
            raw = match.group(0)
            start, end = match.span()
            normalized_start: Optional[int] = None
            normalized_end: Optional[int] = None
            precision = "date"
            confidence = 1.0
            is_relative = kind == "relative"
            if kind == "iso":
                try:
                    if "T" in raw or " " in raw:
                        parsed = _aware_datetime(raw, timezone_name)
                        normalized_start = to_epoch_ms(parsed)
                        precision = _precision(raw)
                        normalized_end = normalized_start + {"date": 86_400_000, "minute": 60_000,
                                                              "second": 1_000, "millisecond": 1,
                                                              "microsecond": 1}[precision]
                    else:
                        parsed_date = date.fromisoformat(raw)
                        start_dt = datetime.combine(parsed_date, datetime_time.min, zone)
                        normalized_start = to_epoch_ms(start_dt)
                        normalized_end = to_epoch_ms(datetime.combine(parsed_date + timedelta(days=1), datetime_time.min, zone))
                except ValueError:
                    continue
            elif kind == "month_year":
                month = _MONTHS.get(match.group(1).casefold())
                if month is None:
                    continue
                year = int(match.group(2))
                normalized_start = to_epoch_ms(datetime(year, month, 1, tzinfo=zone))
                next_month = date(year + (month == 12), (month % 12) + 1, 1)
                normalized_end = to_epoch_ms(datetime.combine(next_month, datetime_time.min, zone))
                precision = "month"
                confidence = 1.0
            elif kind == "named":
                month = _MONTHS.get(match.group(1).casefold())
                if month is None:
                    continue
                year = int(match.group(3)) if match.group(3) else (anchor_dt.year if anchor_dt else None)
                if year is None:
                    continue
                try:
                    parsed_date = date(year, month, int(match.group(2)))
                except ValueError:
                    continue
                start_dt = datetime.combine(parsed_date, datetime_time.min, zone)
                normalized_start = to_epoch_ms(start_dt)
                normalized_end = to_epoch_ms(datetime.combine(parsed_date + timedelta(days=1), datetime_time.min, zone))
                confidence = 1.0 if match.group(3) else 0.75
            else:
                if anchor_dt is None:
                    continue
                phrase = raw.casefold()
                base_date = anchor_dt.date()
                if phrase == "today":
                    target = base_date
                elif phrase == "yesterday":
                    target = base_date - timedelta(days=1)
                elif phrase == "tomorrow":
                    target = base_date + timedelta(days=1)
                else:
                    rel = re.search(r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(days?|weeks?|months?|years?)", phrase)
                    if not rel:
                        continue
                    amount = _word_count(rel.group(1))
                    unit = rel.group(2).rstrip("s")
                    if amount is None:
                        continue
                    direction = -1 if "ago" in phrase else 1
                    amount *= direction
                    if unit == "day":
                        target = base_date + timedelta(days=amount)
                    elif unit == "week":
                        target = base_date + timedelta(days=7 * amount)
                    elif unit == "month":
                        target = _shift_months(base_date, amount)
                    else:
                        target = _shift_months(base_date, 12 * amount)
                normalized_start = to_epoch_ms(datetime.combine(target, datetime_time.min, zone))
                normalized_end = to_epoch_ms(datetime.combine(target + timedelta(days=1), datetime_time.min, zone))
                confidence = 0.95
            found.append({
                "raw_text": raw, "char_start": start, "char_end": end,
                "normalized_start_ms": normalized_start, "normalized_end_ms": normalized_end,
                "timezone": timezone_name, "precision": precision,
                "confidence": confidence, "semantic_role": _mention_role(text, start),
                "anchor_ms": anchor_ms, "resolver_version": resolver_version,
            })

    # A longer ISO datetime owns its embedded date prefix; return non-overlapping spans.
    selected = []
    for item in sorted(found, key=lambda value: (value["char_start"], -(value["char_end"] - value["char_start"]))):
        if any(item["char_start"] < prior["char_end"] and item["char_end"] > prior["char_start"] for prior in selected):
            continue
        selected.append(item)
    return sorted(selected, key=lambda value: value["char_start"])


def route_temporal_query(query: str) -> dict[str, Any]:
    """Route temporal language to one or more named clocks with explicit provenance."""
    value = query.casefold()
    routes = []
    if re.search(r"\b(created|creation|born|authored)\b", value):
        routes.append({"dimension": "created_at", "column": "physical_ms", "event_types": ["created"]})
    if re.search(r"\b(happened|occurred|event)\b", value):
        routes.append({"dimension": "event_at", "column": "valid_at_ms", "event_types": ["event"]})
    if re.search(r"\b(what did we know|known|as of|then)\b", value):
        routes.append({"dimension": "system_at", "column": "system_at_ms", "event_types": []})
    if re.search(r"\b(ai|model|agent)\b.*\b(read|touched|accessed)\b|\b(ai touch|ai touched)\b", value):
        routes.append({"dimension": "ai_touched_at", "column": "physical_ms", "event_types": ["ai_touch"]})
    if re.search(r"\b(migrated|migration)\b", value):
        routes.append({"dimension": "migrated_at", "column": "physical_ms", "event_types": ["migration"]})
    if re.search(r"\b(updated|amended|version)\b", value):
        routes.append({"dimension": "updated_at", "column": "physical_ms", "event_types": ["version", "amendment", "source_update"]})
    if re.search(r"\b(mentions?|mentioned|says|said)\b", value):
        routes.append({"dimension": "temporal_mentions", "column": "normalized_start_ms", "event_types": []})
    if not routes:
        routes.append({"dimension": "event_at", "column": "valid_at_ms", "event_types": ["event"]})
    return {"query": query, "routes": routes, "ambiguous": len(routes) > 1}


class TemporalFabric:
    """Append-only millisecond lifecycle/touch log and indexed date-mention store."""

    def __init__(self, path: str | Path, *, node_id: str,
                 drift_threshold_ms: int = 5_000):
        if not node_id:
            raise ValueError("node_id is required for deterministic HLC ordering")
        self.path = Path(path)
        self.node_id = node_id
        self.drift_threshold_ms = drift_threshold_ms
        self._last_clock: Optional[HybridLogicalClock] = None
        self._clock_lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS temporal_events (
                    event_id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    physical_ms INTEGER NOT NULL,
                    valid_at_ms INTEGER,
                    valid_to_ms INTEGER,
                    system_at_ms INTEGER NOT NULL,
                    hlc_physical_ms INTEGER NOT NULL,
                    logical_sequence INTEGER NOT NULL,
                    node_id TEXT NOT NULL,
                    clock_offset_ms INTEGER,
                    clock_uncertainty_ms INTEGER,
                    drift_flag INTEGER NOT NULL,
                    source_timestamp_raw TEXT,
                    original_precision TEXT,
                    timezone TEXT,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_temporal_physical_range
                    ON temporal_events(event_type, physical_ms, logical_sequence, node_id, event_id);
                CREATE INDEX IF NOT EXISTS idx_temporal_valid_system
                    ON temporal_events(artifact_id, event_type, valid_at_ms, system_at_ms,
                                       logical_sequence, node_id, event_id);
                CREATE INDEX IF NOT EXISTS idx_temporal_valid_to
                    ON temporal_events(artifact_id, valid_to_ms, event_type, system_at_ms);
                CREATE INDEX IF NOT EXISTS idx_temporal_system_range
                    ON temporal_events(system_at_ms, event_type, artifact_id);
                CREATE INDEX IF NOT EXISTS idx_temporal_hlc_order
                    ON temporal_events(hlc_physical_ms, logical_sequence, node_id, event_id);
                CREATE TABLE IF NOT EXISTS temporal_mentions (
                    mention_id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    char_start INTEGER NOT NULL,
                    char_end INTEGER NOT NULL,
                    normalized_start_ms INTEGER NOT NULL,
                    normalized_end_ms INTEGER NOT NULL,
                    timezone TEXT NOT NULL,
                    precision TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    semantic_role TEXT NOT NULL,
                    anchor_ms INTEGER,
                    resolver_version TEXT NOT NULL,
                    captured_at_ms INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_temporal_mention_range
                    ON temporal_mentions(normalized_start_ms, normalized_end_ms, semantic_role, mention_id);
                CREATE INDEX IF NOT EXISTS idx_temporal_mention_artifact
                    ON temporal_mentions(artifact_id, normalized_start_ms, mention_id);
                CREATE TRIGGER IF NOT EXISTS temporal_events_no_update BEFORE UPDATE ON temporal_events
                    BEGIN SELECT RAISE(ABORT, 'temporal_events is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS temporal_events_no_delete BEFORE DELETE ON temporal_events
                    BEGIN SELECT RAISE(ABORT, 'temporal_events is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS temporal_mentions_no_update BEFORE UPDATE ON temporal_mentions
                    BEGIN SELECT RAISE(ABORT, 'temporal_mentions is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS temporal_mentions_no_delete BEFORE DELETE ON temporal_mentions
                    BEGIN SELECT RAISE(ABORT, 'temporal_mentions is append-only'); END;
            """)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def append_event(self, artifact_id: str, event_type: str, *,
                     physical_ms: Optional[int] = None,
                     valid_at_ms: Optional[int] = None,
                     valid_to_ms: Optional[int] = None,
                     system_at_ms: Optional[int] = None,
                     event_id: Optional[str] = None,
                     source_timestamp_raw: Optional[str] = None,
                     original_precision: Optional[str] = None,
                     timezone_name: Optional[str] = None,
                     clock_offset_ms: Optional[int] = None,
                     clock_uncertainty_ms: Optional[int] = None,
                     observed_clock: Optional[HybridLogicalClock] = None,
                     payload: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        if not artifact_id:
            raise ValueError("artifact_id is required")
        if event_type not in _EVENT_TYPES:
            raise ValueError(f"unsupported lifecycle event type: {event_type}")
        if clock_uncertainty_ms is not None and clock_uncertainty_ms < 0:
            raise ValueError("clock_uncertainty_ms must be non-negative")
        now_ms = time.time_ns() // 1_000_000
        physical_ms = now_ms if physical_ms is None else int(physical_ms)
        system_at_ms = now_ms if system_at_ms is None else int(system_at_ms)
        event_id = event_id or hashlib.sha256(
            f"{artifact_id}\0{event_type}\0{physical_ms}\0{system_at_ms}\0{time.time_ns()}".encode()
        ).hexdigest()
        with self._clock_lock:
            clock = advance_hlc(system_at_ms, self.node_id, event_id, self._last_clock, observed_clock)
            self._last_clock = clock
        offset = clock_offset_ms
        drift = offset is not None and abs(offset) > self.drift_threshold_ms
        body = json.dumps(dict(payload or {}), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        record = {
            "event_id": event_id, "artifact_id": artifact_id, "event_type": event_type,
            "physical_ms": physical_ms, "valid_at_ms": valid_at_ms,
            "valid_to_ms": valid_to_ms, "system_at_ms": system_at_ms,
            "hlc_physical_ms": clock.physical_ms,
            "logical_sequence": clock.logical_counter, "node_id": self.node_id,
            "clock_offset_ms": offset, "clock_uncertainty_ms": clock_uncertainty_ms,
            "drift_flag": drift, "source_timestamp_raw": source_timestamp_raw,
            "original_precision": original_precision, "timezone": timezone_name,
            "payload_json": body,
        }
        with self._connect() as conn:
            conn.execute("""INSERT INTO temporal_events (
            event_id, artifact_id, event_type, physical_ms, valid_at_ms, valid_to_ms,
                system_at_ms, hlc_physical_ms, logical_sequence, node_id, clock_offset_ms, clock_uncertainty_ms,
                drift_flag, source_timestamp_raw, original_precision, timezone, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                record["event_id"], record["artifact_id"], record["event_type"],
                record["physical_ms"], record["valid_at_ms"], record["valid_to_ms"],
                record["system_at_ms"], record["hlc_physical_ms"], record["logical_sequence"],
                record["node_id"], record["clock_offset_ms"], record["clock_uncertainty_ms"],
                record["drift_flag"], record["source_timestamp_raw"],
                record["original_precision"], record["timezone"], record["payload_json"],
            ))
        return {**record, "clock": asdict(clock),
                "causal_confidence": "uncertain" if clock_uncertainty_ms is None or clock_uncertainty_ms or drift else "bounded"}

    def record_lifecycle(self, artifact_id: str, event_type: str, *,
                         raw_timestamp: Optional[str] = None,
                         timezone_name: Optional[str] = None,
                         valid_at_ms: Optional[int] = None,
                         system_at_ms: Optional[int] = None,
                         payload: Optional[Mapping[str, Any]] = None,
                         **kwargs: Any) -> dict[str, Any]:
        precision = _precision(raw_timestamp) if raw_timestamp else None
        physical_ms = to_epoch_ms(raw_timestamp, timezone_name) if raw_timestamp else None
        return self.append_event(
            artifact_id, event_type, physical_ms=physical_ms,
            valid_at_ms=valid_at_ms if valid_at_ms is not None else physical_ms,
            system_at_ms=system_at_ms, source_timestamp_raw=raw_timestamp,
            original_precision=precision, timezone_name=timezone_name,
            payload=payload, **kwargs,
        )

    def record_envelope(self, envelope: TemporalEnvelope) -> list[dict[str, Any]]:
        """Persist each known clock independently; null clocks remain absent."""
        event_for_clock = {
            "created_at": "created", "source_created_at": "created",
            "source_updated_at": "source_update", "event_at": "event",
            "first_seen_at": "first_seen", "captured_at": "capture",
            "updated_at": "version", "ai_touched_at": "ai_touch",
            "ingested_at": "ingestion", "migrated_at": "migration",
            "indexed_at": "index", "reconciled_at": "reconciliation",
            "canonicalized_at": "canonicalization", "superseded_at": "supersession",
            "retracted_at": "retraction", "valid_from": "version",
        }
        events = []
        for clock_name, event_type in event_for_clock.items():
            clock_ms = getattr(envelope, f"{clock_name}_ms")
            if clock_ms is None:
                continue
            events.append(self.append_event(
                envelope.artifact_id, event_type, physical_ms=clock_ms,
                valid_at_ms=(envelope.valid_from_ms if clock_name in ("updated_at", "valid_from")
                             else clock_ms),
                valid_to_ms=envelope.valid_to_ms if clock_name in ("updated_at", "valid_from") else None,
                system_at_ms=envelope.system_at_ms,
                source_timestamp_raw=envelope.raw_timestamps.get(clock_name),
                original_precision=envelope.original_precision.get(clock_name),
                timezone_name=envelope.timezone, clock_offset_ms=envelope.clock_offset_ms,
                clock_uncertainty_ms=envelope.clock_uncertainty_ms,
                payload={"clock_name": clock_name, "drift_flag": envelope.drift_flag},
            ))
        return events

    def record_ai_touch(self, artifact_id: str, *, event_id: Optional[str] = None,
                        touched_at_ms: Optional[int] = None,
                        system_at_ms: Optional[int] = None,
                        payload: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        """Record a read/touch without changing created, event, or update clocks."""
        return self.append_event(artifact_id, "ai_touch", physical_ms=touched_at_ms,
                                 system_at_ms=system_at_ms, event_id=event_id, payload=payload)

    def record_version(self, artifact_id: str, content: Mapping[str, Any], *,
                       valid_from_ms: int, known_from_ms: Optional[int] = None,
                       valid_to_ms: Optional[int] = None,
                       event_id: Optional[str] = None) -> dict[str, Any]:
        """Append a version with separate valid/event and transaction/system time."""
        if valid_to_ms is not None and valid_to_ms <= valid_from_ms:
            raise ValueError("valid_to_ms must be greater than valid_from_ms")
        return self.append_event(
            artifact_id, "version", physical_ms=known_from_ms,
            valid_at_ms=valid_from_ms, valid_to_ms=valid_to_ms,
            system_at_ms=known_from_ms, event_id=event_id,
            payload={"content": dict(content)},
        )

    def resolve_as_of(self, artifact_id: str, *, valid_as_of_ms: int,
                      known_as_of_ms: int) -> dict[str, Any]:
        """Return the version valid at V that was recorded by transaction time T."""
        with self._connect() as conn:
            row = conn.execute("""SELECT * FROM temporal_events
                WHERE artifact_id=? AND event_type='version'
                  AND valid_at_ms<=? AND (valid_to_ms IS NULL OR valid_to_ms>?)
                  AND system_at_ms<=?
                ORDER BY system_at_ms DESC, logical_sequence DESC, node_id DESC, event_id DESC
                LIMIT 1""", (artifact_id, valid_as_of_ms, valid_as_of_ms, known_as_of_ms)).fetchone()
        if row is None:
            return {"status": "cannot_determine", "artifact_id": artifact_id,
                    "valid_as_of_ms": valid_as_of_ms, "known_as_of_ms": known_as_of_ms,
                    "version": None, "lanes_queried": ["temporal_fabric"]}
        return {"status": "complete", "artifact_id": artifact_id,
                "valid_as_of_ms": valid_as_of_ms, "known_as_of_ms": known_as_of_ms,
                "version": {**dict(row), "payload": json.loads(row["payload_json"])},
                "lanes_queried": ["temporal_fabric"]}

    def events_for_range(self, dimension: str, start_ms: int, end_ms: int, *,
                         artifact_id: Optional[str] = None) -> list[dict[str, Any]]:
        if end_ms <= start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        if dimension not in _DIMENSION_TYPES:
            raise ValueError(f"unknown temporal dimension: {dimension}")
        if dimension in ("system_at", "system_at_ms"):
            column = "system_at_ms"
        elif dimension in ("valid_to", "valid_to_ms"):
            column = "valid_to_ms"
        elif dimension in ("valid_at", "valid_at_ms", "event_at", "event_at_ms"):
            column = "valid_at_ms"
        elif dimension in ("ai_touched_at", "created_at", "source_created_at",
                           "source_updated_at", "updated_at", "migrated_at", "ingested_at",
                           "first_seen_at", "captured_at", "indexed_at", "reconciled_at",
                           "canonicalized_at", "superseded_at", "retracted_at", "physical_ms"):
            column = "physical_ms"
        else:
            raise ValueError(f"unknown temporal dimension: {dimension}")
        event_types = _DIMENSION_TYPES.get(dimension, ())
        clauses, params = [f"{column}>=?", f"{column}<?"], [start_ms, end_ms]
        if event_types:
            clauses.append("event_type IN (" + ",".join("?" for _ in event_types) + ")")
            params.extend(event_types)
        if artifact_id is not None:
            clauses.append("artifact_id=?")
            params.append(artifact_id)
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM temporal_events WHERE " + " AND ".join(clauses) +
                                f" ORDER BY {column}, logical_sequence, node_id, event_id", params).fetchall()
        return [dict(row) for row in rows]

    def index_mentions(self, artifact_id: str, text: str, *, anchor: Optional[int | datetime],
                       timezone_name: str, captured_at_ms: Optional[int] = None,
                       resolver_version: str = "temporal-v2") -> list[dict[str, Any]]:
        captured_at_ms = time.time_ns() // 1_000_000 if captured_at_ms is None else captured_at_ms
        mentions = extract_temporal_mentions(text, anchor, timezone_name, resolver_version)
        for mention in mentions:
            canonical = json.dumps([artifact_id, mention["raw_text"], mention["char_start"],
                                    mention["char_end"], mention["anchor_ms"], resolver_version],
                                   ensure_ascii=False, separators=(",", ":"))
            mention_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            with self._connect() as conn:
                conn.execute("""INSERT OR IGNORE INTO temporal_mentions (
                    mention_id, artifact_id, raw_text, char_start, char_end,
                    normalized_start_ms, normalized_end_ms, timezone, precision,
                    confidence, semantic_role, anchor_ms, resolver_version, captured_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                    mention_id, artifact_id, mention["raw_text"], mention["char_start"], mention["char_end"],
                    mention["normalized_start_ms"], mention["normalized_end_ms"], mention["timezone"],
                    mention["precision"], mention["confidence"], mention["semantic_role"],
                    mention["anchor_ms"], mention["resolver_version"], captured_at_ms,
                ))
            mention["mention_id"] = mention_id
        return mentions

    def mentions_between(self, start_ms: int, end_ms: int, *,
                         semantic_role: Optional[str] = None,
                         artifact_id: Optional[str] = None) -> list[dict[str, Any]]:
        if end_ms <= start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        clauses = ["normalized_start_ms<?", "normalized_end_ms>?" ]
        params: list[Any] = [end_ms, start_ms]
        if semantic_role:
            clauses.append("semantic_role=?")
            params.append(semantic_role)
        if artifact_id:
            clauses.append("artifact_id=?")
            params.append(artifact_id)
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM temporal_mentions WHERE " + " AND ".join(clauses) +
                                " ORDER BY normalized_start_ms, mention_id", params).fetchall()
        return [dict(row) for row in rows]

"""Append-only index and scope-safe resolver for canonical fact snapshots.

This is deliberately separate from the free-form shard table: a semantic hit
is useful evidence, but it is not enough to prove that a scoped metric rollup
is current or complete.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEMA_VERSION = 1
_COMPLETENESS = {"complete", "partial", "unknown"}


def _iso(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO date or datetime")
    try:
        date.fromisoformat(value)
        if len(value) == 10:
            return value
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be ISO-8601") from exc
    else:
        if parsed.tzinfo is None:
            raise ValueError(f"{field} datetime must include a timezone")
    return value


def _time_key(value: str) -> float:
    """Compare date-only and offset timestamps by instant, not string shape."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.combine(date.fromisoformat(value), datetime.min.time(), timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric, not boolean")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    return number


def validate_snapshot(snapshot: Mapping[str, Any]) -> dict:
    """Validate and normalize a FACT_SNAPSHOT payload; never infer missing=0."""
    if not isinstance(snapshot, Mapping):
        raise ValueError("snapshot must be a JSON object")
    data = json.loads(json.dumps(snapshot, allow_nan=False))
    for field in ("canonical_key", "intent", "metric_namespace"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError(f"{field} is required")
    if data.get("artifact_kind") != "FACT_SNAPSHOT":
        raise ValueError("artifact_kind must be FACT_SNAPSHOT")
    if data.get("canonical") is not True:
        raise ValueError("only explicitly canonical snapshots may enter this index")

    temporal = data.get("temporal")
    if not isinstance(temporal, dict):
        raise ValueError("temporal is required")
    for field in ("as_of", "event_at", "captured_at"):
        temporal[field] = _iso(temporal.get(field), f"temporal.{field}")
    try:
        ZoneInfo(temporal.get("timezone", ""))
    except (ZoneInfoNotFoundError, TypeError) as exc:
        raise ValueError("temporal.timezone must be a valid IANA timezone") from exc
    if not temporal.get("period") or not temporal.get("year"):
        raise ValueError("temporal.period and temporal.year are required")

    scope = data.get("scope")
    if not isinstance(scope, dict):
        raise ValueError("scope is required")
    machines = scope.get("expected_machines")
    if not isinstance(machines, list) or not machines or any(not isinstance(m, str) or not m for m in machines):
        raise ValueError("scope.expected_machines must be a non-empty list of machine names")
    if len(set(machines)) != len(machines):
        raise ValueError("scope.expected_machines must be unique")
    machines = sorted(machines)
    scope["expected_machines"] = machines
    entities = data.get("entities")
    expected_entities = scope.get("expected_entities", entities)
    if (not isinstance(entities, list) or not entities
            or any(not isinstance(entity, str) or not entity for entity in entities)):
        raise ValueError("entities must be a non-empty list of canonical entity names")
    if (not isinstance(expected_entities, list) or not expected_entities
            or any(not isinstance(entity, str) or not entity for entity in expected_entities)):
        raise ValueError("scope.expected_entities must be a non-empty list")
    if len(set(expected_entities)) != len(expected_entities):
        raise ValueError("scope.expected_entities must be unique")
    if not set(expected_entities).issubset(entities):
        raise ValueError("entities must include every expected entity")
    scope["expected_entities"] = sorted(expected_entities)

    completeness = data.get("completeness")
    if not isinstance(completeness, dict) or completeness.get("state") not in _COMPLETENESS:
        raise ValueError("completeness.state must be complete, partial, or unknown")
    missing = completeness.get("missing_machines", [])
    if not isinstance(missing, list) or any(m not in machines for m in missing):
        raise ValueError("completeness.missing_machines must be a subset of expected machines")
    if completeness["state"] != "complete" or missing:
        raise ValueError("incomplete snapshots cannot be marked canonical")

    values = data.get("per_machine")
    if not isinstance(values, dict) or set(values) != set(machines):
        raise ValueError("per_machine values must cover exactly the expected machines")
    total = Decimal(0)
    for machine, record in values.items():
        if not isinstance(record, dict) or not isinstance(record.get("exact"), bool):
            raise ValueError(f"per_machine.{machine} requires value and exact boolean")
        total += _decimal(record.get("value"), f"per_machine.{machine}.value")
    if _decimal(data.get("total"), "total") != total:
        raise ValueError("total must equal the sum of per_machine values")

    provenance = data.get("provenance")
    if not isinstance(provenance, dict) or not provenance.get("source_ids"):
        raise ValueError("provenance.source_ids is required")
    hashes = provenance.get("source_hashes")
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError("provenance.source_hashes is required")
    if not isinstance(data.get("version"), int) or data["version"] < 1:
        raise ValueError("version must be a positive integer")
    data["aliases"] = data.get("aliases") or {}
    if not isinstance(data["aliases"], dict):
        raise ValueError("aliases must be an object mapping canonical entities to aliases")
    data["supersedes"] = data.get("supersedes")
    return data


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _terms(value: str) -> set[str]:
    terms = set(re.findall(r"[a-z0-9]+", value.casefold()))
    return {term[:-1] if term.endswith("s") and len(term) > 3 else term for term in terms}


class CanonicalFactIndex:
    """Small append-only SQLite index; caller owns the path and its backups."""

    def __init__(self, path: str | Path, *, create: bool = True):
        self.path = Path(path)
        self.read_only = not create
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS fact_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    canonical_key TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    event_at TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    scope_json TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL
                )""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_fact_key_asof ON fact_snapshots(canonical_key, as_of DESC, version DESC)")
                conn.execute("PRAGMA user_version = 1")
        else:
            if not self.path.is_file():
                raise FileNotFoundError(f"fact index does not exist: {self.path}")
            with self._connect() as conn:
                exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fact_snapshots'").fetchone()
                if not exists:
                    raise ValueError(f"not a canonical fact index: {self.path}")

    def _connect(self) -> sqlite3.Connection:
        if self.read_only:
            conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=10)
        else:
            conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def put(self, snapshot: Mapping[str, Any]) -> str:
        if self.read_only:
            raise PermissionError("fact index was opened read-only")
        data = validate_snapshot(snapshot)
        body = _canonical_json(data)
        snapshot_id = hashlib.sha256(body.encode("utf-8")).hexdigest()
        temporal = data["temporal"]
        with self._connect() as conn:
            conn.execute("""INSERT OR IGNORE INTO fact_snapshots
                (snapshot_id, canonical_key, as_of, event_at, captured_at, version, scope_json, snapshot_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (
                    snapshot_id, data["canonical_key"], temporal["as_of"], temporal["event_at"],
                    temporal["captured_at"], data["version"], _canonical_json(data["scope"]), body,
                ))
        return snapshot_id

    def resolve(self, canonical_key: str, *, expected_machines: Sequence[str],
                expected_entities: Optional[Sequence[str]] = None,
                scope: Optional[Mapping[str, Any]] = None,
                temporal_scope: Optional[Mapping[str, Any]] = None,
                as_of: Optional[str] = None) -> dict:
        """Resolve only complete exact-scope snapshots and return a full receipt."""
        expected = sorted(set(expected_machines))
        if not expected:
            raise ValueError("expected_machines must not be empty")
        if as_of is not None:
            as_of = _iso(as_of, "as_of")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT snapshot_id, snapshot_json FROM fact_snapshots WHERE canonical_key=? ORDER BY as_of DESC, version DESC, captured_at DESC",
                (canonical_key,),
            ).fetchall()

        candidates, rejected = [], []
        for row in rows:
            data = json.loads(row["snapshot_json"])
            why = None
            if sorted(data["scope"].get("expected_machines", [])) != expected:
                why = "scope_mismatch:expected_machines"
            elif (expected_entities is not None
                  and sorted(data["scope"].get("expected_entities", [])) != sorted(set(expected_entities))):
                why = "scope_mismatch:expected_entities"
            elif scope and any(data.get(key) != value for key, value in scope.items()):
                why = "scope_mismatch:query_scope"
            elif temporal_scope and any(data["temporal"].get(key) != value
                                        for key, value in temporal_scope.items()):
                why = "scope_mismatch:temporal_scope"
            elif as_of and _time_key(data["temporal"]["as_of"]) > _time_key(as_of):
                why = "future_as_of"
            elif data["completeness"].get("state") != "complete":
                why = "incomplete_snapshot"
            if why:
                rejected.append({"snapshot_id": row["snapshot_id"], "reason": why})
            else:
                candidates.append({"snapshot_id": row["snapshot_id"], "snapshot": data})

        if not candidates:
            return {"status": "cannot_determine", "canonical_key": canonical_key,
                    "snapshot": None, "candidates": [], "rejected": rejected,
                    "coverage": {"expected_machines": expected,
                                 "expected_entities": sorted(set(expected_entities or [])),
                                 "present_machines": [], "complete": False},
                    "lanes_queried": ["canonical_fact_index"], "failed_lanes": []}

        # Newest event-time/as-of wins; capture time cannot make old facts current.
        candidates.sort(key=lambda item: (
            _time_key(item["snapshot"]["temporal"]["as_of"]),
            item["snapshot"]["version"],
            _time_key(item["snapshot"]["temporal"]["event_at"]),
        ), reverse=True)
        winner = candidates[0]
        for stale in candidates[1:]:
            rejected.append({"snapshot_id": stale["snapshot_id"],
                             "reason": "superseded_by_newer_same_scope"})
        winner["snapshot"]["snapshot_id"] = winner["snapshot_id"]
        return {"status": "complete", "canonical_key": canonical_key,
                "snapshot": winner["snapshot"], "candidates": [c["snapshot_id"] for c in candidates],
                "rejected": rejected,
                "coverage": {"expected_machines": expected,
                             "expected_entities": sorted(set(expected_entities or [])),
                             "present_machines": expected, "complete": True},
                "lanes_queried": ["canonical_fact_index"], "failed_lanes": []}

    def resolve_query(self, query: str, *, expected_machines: Sequence[str],
                      expected_entities: Optional[Sequence[str]] = None,
                      scope: Optional[Mapping[str, Any]] = None,
                      as_of: Optional[str] = None) -> dict:
        """Resolve a bounded natural-language alias to one canonical key.

        Query variants must be captured in snapshot aliases. ``today`` queries
        are exact-date constrained; an older snapshot is never substituted.
        """
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        query_terms = _terms(query)
        if not query_terms:
            raise ValueError("query must contain searchable words")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT snapshot_id, canonical_key, snapshot_json FROM fact_snapshots"
            ).fetchall()

        ranked = []
        for row in rows:
            data = json.loads(row["snapshot_json"])
            aliases = [alias for values in data.get("aliases", {}).values()
                       if isinstance(values, list) for alias in values if isinstance(alias, str)]
            aliases.extend(data.get("query_aliases", []))
            alias_scores = []
            for alias in aliases:
                alias_terms = _terms(alias)
                if alias_terms:
                    alias_scores.append(len(query_terms & alias_terms) / len(query_terms))
            searchable = " ".join([
                data.get("intent", ""), data.get("canonical_key", ""),
                data.get("metric_namespace", ""), " ".join(data.get("entities", [])),
                " ".join(data["scope"].get("expected_machines", [])),
                str(data["temporal"].get("period", "")), str(data["temporal"].get("year", "")),
            ])
            text_score = len(query_terms & _terms(searchable)) / len(query_terms)
            score = max(alias_scores + [text_score])
            ranked.append({"snapshot_id": row["snapshot_id"], "canonical_key": row["canonical_key"],
                           "snapshot": data, "score": score})

        ranked.sort(key=lambda item: item["score"], reverse=True)
        ranked = [item for item in ranked if item["score"] >= 0.5]
        if not ranked:
            return {"status": "cannot_determine", "query": query, "snapshot": None,
                    "candidates": [], "rejected": [], "coverage": {"complete": False},
                    "lanes_queried": ["canonical_fact_index:structured_query"], "failed_lanes": []}

        top_score = ranked[0]["score"]
        top_keys = {item["canonical_key"] for item in ranked if item["score"] == top_score}
        if len(top_keys) != 1:
            return {"status": "ambiguous", "query": query, "snapshot": None,
                    "candidates": [{"canonical_key": item["canonical_key"],
                                    "snapshot_id": item["snapshot_id"], "score": item["score"]}
                                   for item in ranked],
                    "rejected": [], "coverage": {"complete": False},
                    "lanes_queried": ["canonical_fact_index:structured_query"], "failed_lanes": []}

        canonical_key = next(iter(top_keys))
        if "today" in query_terms:
            local_today = (date.fromisoformat(as_of[:10]) if as_of else
                           datetime.now(ZoneInfo("America/New_York")).date())
            date_filter = local_today.isoformat()
        else:
            date_filter = as_of
        result = self.resolve(
            canonical_key, expected_machines=expected_machines,
            expected_entities=expected_entities,
            scope=scope,
            temporal_scope={"as_of": date_filter} if "today" in query_terms else None,
            as_of=date_filter if "today" in query_terms else as_of,
        )
        result["query"] = query
        result["query_match"] = {"canonical_key": canonical_key, "score": top_score}
        result["lanes_queried"] = ["canonical_fact_index:structured_query", "canonical_fact_index"]
        return result

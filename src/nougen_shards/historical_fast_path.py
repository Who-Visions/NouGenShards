"""Historical Fast Path Recall Module (Sub-1ms Age-Invariant Fast Path).

Implements bitemporal exact/canonical indexing and direct pointers to guarantee
sub-1ms warm local index lookups regardless of historical era (Nov 2025 == now).
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class FastPathIntent:
    canonical_key: Optional[str] = None
    as_of_is_latest: bool = True
    as_of_ms: Optional[int] = None
    artifact_id: Optional[str] = None
    entity_id: Optional[str] = None
    tag_namespace: Optional[str] = None
    tag_value: Optional[str] = None
    metric_namespace: Optional[str] = None
    metric_scope: Optional[str] = None
    metric_period: Optional[str] = None
    metric_year: Optional[int] = None


@dataclass(frozen=True)
class FastPathResult:
    hit: bool
    source_index: str
    artifact_id: Optional[str] = None
    revision: Optional[int] = None
    as_of_ms: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None
    reason: str = "HIT"
    latency_us: int = 0


class HistoricalFastPathStore:
    """High-performance SQLite backed index maintaining bitemporal canonical tables and posting lists."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript("""
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;

        CREATE TABLE IF NOT EXISTS canonical_current (
            key TEXT PRIMARY KEY,
            artifact_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            as_of_ms INTEGER NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS canonical_history (
            key TEXT NOT NULL,
            as_of_ms INTEGER NOT NULL,
            revision INTEGER NOT NULL,
            artifact_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (key, as_of_ms, revision)
        );
        CREATE INDEX IF NOT EXISTS idx_canonical_history_lookup
            ON canonical_history(key, as_of_ms DESC, revision DESC);

        CREATE TABLE IF NOT EXISTS artifact (
            artifact_id TEXT PRIMARY KEY,
            event_ms INTEGER NOT NULL,
            kind TEXT NOT NULL,
            node TEXT NOT NULL,
            content TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_artifact_event
            ON artifact(event_ms DESC, kind, node);

        CREATE TABLE IF NOT EXISTS entity_posting (
            entity_id TEXT NOT NULL,
            event_ms INTEGER NOT NULL,
            artifact_id TEXT NOT NULL,
            PRIMARY KEY (entity_id, event_ms, artifact_id)
        );

        CREATE TABLE IF NOT EXISTS tag_posting (
            namespace TEXT NOT NULL,
            value TEXT NOT NULL,
            event_ms INTEGER NOT NULL,
            artifact_id TEXT NOT NULL,
            PRIMARY KEY (namespace, value, event_ms, artifact_id)
        );

        CREATE TABLE IF NOT EXISTS metric_fact (
            namespace TEXT NOT NULL,
            scope TEXT NOT NULL,
            period TEXT NOT NULL,
            year INTEGER NOT NULL,
            as_of_ms INTEGER NOT NULL,
            artifact_id TEXT NOT NULL,
            value_bps INTEGER NOT NULL,
            PRIMARY KEY (namespace, scope, period, year, as_of_ms, artifact_id)
        );
        CREATE INDEX IF NOT EXISTS idx_metric_lookup
            ON metric_fact(namespace, scope, period, year, as_of_ms DESC);
        """)
        self._conn.commit()

    def register_artifact(
        self,
        artifact_id: str,
        event_ms: int,
        kind: str,
        node: str,
        content: str
    ) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO artifact (artifact_id, event_ms, kind, node, content) VALUES (?, ?, ?, ?, ?)",
            (artifact_id, event_ms, kind, node, content)
        )
        self._conn.commit()

    def put_canonical(
        self,
        key: str,
        artifact_id: str,
        revision: int,
        as_of_ms: int,
        payload: Dict[str, Any]
    ) -> None:
        cur = self._conn.cursor()
        payload_str = json.dumps(payload, sort_keys=True)
        # Update current
        cur.execute(
            "INSERT OR REPLACE INTO canonical_current (key, artifact_id, revision, as_of_ms, payload_json) VALUES (?, ?, ?, ?, ?)",
            (key, artifact_id, revision, as_of_ms, payload_str)
        )
        # Append to history
        cur.execute(
            "INSERT OR REPLACE INTO canonical_history (key, as_of_ms, revision, artifact_id, payload_json) VALUES (?, ?, ?, ?, ?)",
            (key, as_of_ms, revision, artifact_id, payload_str)
        )
        self._conn.commit()

    def add_entity_posting(self, entity_id: str, event_ms: int, artifact_id: str) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO entity_posting (entity_id, event_ms, artifact_id) VALUES (?, ?, ?)",
            (entity_id, event_ms, artifact_id)
        )
        self._conn.commit()

    def add_tag_posting(self, namespace: str, value: str, event_ms: int, artifact_id: str) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO tag_posting (namespace, value, event_ms, artifact_id) VALUES (?, ?, ?, ?)",
            (namespace, value, event_ms, artifact_id)
        )
        self._conn.commit()

    def add_metric_fact(
        self,
        namespace: str,
        scope: str,
        period: str,
        year: int,
        as_of_ms: int,
        artifact_id: str,
        value_bps: int
    ) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO metric_fact (namespace, scope, period, year, as_of_ms, artifact_id, value_bps) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (namespace, scope, period, year, as_of_ms, artifact_id, value_bps)
        )
        self._conn.commit()

    def fast_lookup(self, intent: FastPathIntent) -> FastPathResult:
        """Sub-1ms warm local index lookup dispatcher."""
        t0 = time.perf_counter_ns()
        cur = self._conn.cursor()

        # 1. Direct Canonical Current
        if intent.canonical_key and intent.as_of_is_latest:
            row = cur.execute(
                "SELECT artifact_id, revision, as_of_ms, payload_json FROM canonical_current WHERE key = ?",
                (intent.canonical_key,)
            ).fetchone()
            if row:
                t1 = time.perf_counter_ns()
                return FastPathResult(
                    hit=True,
                    source_index="canonical_current",
                    artifact_id=row["artifact_id"],
                    revision=row["revision"],
                    as_of_ms=row["as_of_ms"],
                    payload=json.loads(row["payload_json"]),
                    reason="CANONICAL_CURRENT_HIT",
                    latency_us=(t1 - t0) // 1000
                )

        # 2. Canonical History Point-in-Time
        if intent.canonical_key and intent.as_of_ms is not None:
            row = cur.execute(
                """
                SELECT artifact_id, revision, as_of_ms, payload_json
                FROM canonical_history
                WHERE key = ? AND as_of_ms <= ?
                ORDER BY as_of_ms DESC, revision DESC
                LIMIT 1
                """,
                (intent.canonical_key, intent.as_of_ms)
            ).fetchone()
            if row:
                t1 = time.perf_counter_ns()
                return FastPathResult(
                    hit=True,
                    source_index="canonical_history",
                    artifact_id=row["artifact_id"],
                    revision=row["revision"],
                    as_of_ms=row["as_of_ms"],
                    payload=json.loads(row["payload_json"]),
                    reason="CANONICAL_HISTORY_AS_OF_HIT",
                    latency_us=(t1 - t0) // 1000
                )

        # 3. Direct Artifact PK
        if intent.artifact_id:
            row = cur.execute(
                "SELECT artifact_id, event_ms, kind, node, content FROM artifact WHERE artifact_id = ?",
                (intent.artifact_id,)
            ).fetchone()
            if row:
                t1 = time.perf_counter_ns()
                return FastPathResult(
                    hit=True,
                    source_index="artifact_pk",
                    artifact_id=row["artifact_id"],
                    revision=1,
                    as_of_ms=row["event_ms"],
                    payload={"kind": row["kind"], "node": row["node"], "content": row["content"]},
                    reason="ARTIFACT_PK_HIT",
                    latency_us=(t1 - t0) // 1000
                )

        # 4. Entity Posting List
        if intent.entity_id:
            rows = cur.execute(
                "SELECT artifact_id, event_ms FROM entity_posting WHERE entity_id = ? ORDER BY event_ms DESC LIMIT 1",
                (intent.entity_id,)
            ).fetchall()
            if rows:
                t1 = time.perf_counter_ns()
                return FastPathResult(
                    hit=True,
                    source_index="entity_posting",
                    artifact_id=rows[0]["artifact_id"],
                    as_of_ms=rows[0]["event_ms"],
                    reason="ENTITY_POSTING_HIT",
                    latency_us=(t1 - t0) // 1000
                )

        # 5. Tag Posting List
        if intent.tag_namespace and intent.tag_value:
            rows = cur.execute(
                "SELECT artifact_id, event_ms FROM tag_posting WHERE namespace = ? AND value = ? ORDER BY event_ms DESC LIMIT 1",
                (intent.tag_namespace, intent.tag_value)
            ).fetchall()
            if rows:
                t1 = time.perf_counter_ns()
                return FastPathResult(
                    hit=True,
                    source_index="tag_posting",
                    artifact_id=rows[0]["artifact_id"],
                    as_of_ms=rows[0]["event_ms"],
                    reason="TAG_POSTING_HIT",
                    latency_us=(t1 - t0) // 1000
                )

        # 6. Metric Fact Lookup
        if intent.metric_namespace and intent.metric_scope and intent.metric_period and intent.metric_year:
            as_of_limit = intent.as_of_ms if intent.as_of_ms is not None else 9999999999999
            row = cur.execute(
                """
                SELECT artifact_id, as_of_ms, value_bps
                FROM metric_fact
                WHERE namespace = ? AND scope = ? AND period = ? AND year = ? AND as_of_ms <= ?
                ORDER BY as_of_ms DESC
                LIMIT 1
                """,
                (intent.metric_namespace, intent.metric_scope, intent.metric_period, intent.metric_year, as_of_limit)
            ).fetchone()
            if row:
                t1 = time.perf_counter_ns()
                return FastPathResult(
                    hit=True,
                    source_index="metric_fact",
                    artifact_id=row["artifact_id"],
                    as_of_ms=row["as_of_ms"],
                    payload={"value_bps": row["value_bps"]},
                    reason="METRIC_FACT_HIT",
                    latency_us=(t1 - t0) // 1000
                )

        t1 = time.perf_counter_ns()
        return FastPathResult(
            hit=False,
            source_index="none",
            reason="MISS_TO_HYBRID_PLANNER",
            latency_us=(t1 - t0) // 1000
        )

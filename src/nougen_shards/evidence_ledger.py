"""Auditable business-evidence graph stored separately from the shard vault.

The caller must provide the SQLite path explicitly. This module indexes original
records; it never edits them and never treats business classification as a tax
conclusion.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Optional


class Provenance(str, Enum):
    SOURCE_VERIFIED = "SOURCE_VERIFIED"
    CORROBORATED = "CORROBORATED"
    INFERRED = "INFERRED"
    UNVERIFIED = "UNVERIFIED"
    CONFLICTED = "CONFLICTED"
    CORRECTED = "CORRECTED"


class EvidenceError(ValueError):
    """Raised when a write would violate an evidence invariant."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class EvidenceLedger:
    """Typed, append-oriented evidence index over an explicit SQLite file."""

    def __init__(self, path: str | Path):
        if not path:
            raise EvidenceError("an explicit evidence ledger path is required")
        self.path = Path(path).expanduser().resolve()

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    byte_size INTEGER NOT NULL CHECK(byte_size >= 0),
                    sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
                    source_created_at TEXT,
                    source_modified_at TEXT,
                    extracted_at TEXT NOT NULL,
                    extractor_version TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    root_source_id TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(source_path, sha256)
                );
                CREATE INDEX IF NOT EXISTS idx_sources_hash ON sources(sha256);
                CREATE INDEX IF NOT EXISTS idx_sources_root ON sources(root_source_id);

                CREATE TABLE IF NOT EXISTS business_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    start_time TEXT,
                    end_time TEXT,
                    project TEXT,
                    client_or_payer TEXT,
                    location TEXT,
                    business_purpose TEXT,
                    work_performed TEXT,
                    deliverables_json TEXT NOT NULL DEFAULT '[]',
                    provenance_class TEXT NOT NULL,
                    model_confidence REAL CHECK(model_confidence IS NULL OR
                        (model_confidence >= 0 AND model_confidence <= 1)),
                    created_from_pass TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS event_sources (
                    event_id TEXT NOT NULL REFERENCES business_events(event_id),
                    source_id TEXT NOT NULL REFERENCES sources(source_id),
                    relation TEXT NOT NULL,
                    PRIMARY KEY(event_id, source_id, relation)
                );

                CREATE TABLE IF NOT EXISTS claims (
                    claim_id TEXT PRIMARY KEY,
                    event_id TEXT REFERENCES business_events(event_id),
                    claim_type TEXT NOT NULL,
                    claim_value TEXT,
                    provenance_class TEXT NOT NULL,
                    model_confidence REAL CHECK(model_confidence IS NULL OR
                        (model_confidence >= 0 AND model_confidence <= 1)),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS claim_sources (
                    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
                    source_id TEXT NOT NULL REFERENCES sources(source_id),
                    supports INTEGER NOT NULL CHECK(supports IN (0, 1)),
                    PRIMARY KEY(claim_id, source_id)
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL CHECK(kind IN ('EXPENSE', 'INCOME')),
                    occurred_at TEXT,
                    counterparty TEXT,
                    amount_minor INTEGER,
                    currency TEXT,
                    payment_reference TEXT,
                    event_id TEXT REFERENCES business_events(event_id),
                    business_classification TEXT NOT NULL DEFAULT 'UNKNOWN',
                    tax_treatment TEXT,
                    provenance_class TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS transaction_sources (
                    transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id),
                    source_id TEXT NOT NULL REFERENCES sources(source_id),
                    relation TEXT NOT NULL,
                    PRIMARY KEY(transaction_id, source_id, relation)
                );

                CREATE TABLE IF NOT EXISTS corrections (
                    correction_id TEXT PRIMARY KEY,
                    subject_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    prior_interpretation TEXT NOT NULL,
                    corrected_interpretation TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    source_id TEXT REFERENCES sources(source_id),
                    corrected_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conflicts (
                    conflict_id TEXT PRIMARY KEY,
                    subject_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );
                CREATE TABLE IF NOT EXISTS review_flags (
                    flag_id TEXT PRIMARY KEY,
                    subject_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _validate_provenance(
        conn: sqlite3.Connection, provenance: Provenance, source_ids: Iterable[str]
    ) -> list[str]:
        ids = list(dict.fromkeys(source_ids))
        rows = conn.execute(
            f"SELECT source_id, root_source_id FROM sources WHERE source_id IN ({','.join('?' for _ in ids)})",
            ids,
        ).fetchall() if ids else []
        if len(rows) != len(ids):
            missing = sorted(set(ids) - {row["source_id"] for row in rows})
            raise EvidenceError(f"unknown source ids: {', '.join(missing)}")
        if provenance is Provenance.SOURCE_VERIFIED:
            if not any(row["source_id"] == row["root_source_id"] for row in rows):
                raise EvidenceError("SOURCE_VERIFIED requires a supporting primary source")
        if provenance is Provenance.CORROBORATED:
            roots = {row["root_source_id"] for row in rows}
            if len(roots) < 2:
                raise EvidenceError("CORROBORATED requires two independent root sources")
        return ids

    def add_source_file(
        self, path: str | Path, *, source_kind: str,
        extractor_version: str, root_source_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        source_path = Path(path).expanduser().resolve(strict=True)
        digest = hashlib.sha256()
        with source_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        stat = source_path.stat()
        source_id = _id("src")
        root_id = root_source_id or source_id
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (source_id, str(source_path), source_path.name, stat.st_size,
                 digest.hexdigest(), None, datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                 _now(), extractor_version, source_kind, root_id,
                 json.dumps(metadata or {}, sort_keys=True)),
            )
        return source_id

    def add_event(self, *, event_type: str, created_from_pass: str,
                  provenance: Provenance = Provenance.UNVERIFIED, **fields: Any) -> str:
        if provenance in {Provenance.SOURCE_VERIFIED, Provenance.CORROBORATED}:
            raise EvidenceError("create the event as unverified, link sources, then promote it")
        event_id = _id("evt")
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO business_events
                (event_id,event_type,start_time,end_time,project,client_or_payer,location,
                 business_purpose,work_performed,deliverables_json,provenance_class,
                 model_confidence,created_from_pass,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (event_id, event_type, fields.get("start_time"), fields.get("end_time"),
                 fields.get("project"), fields.get("client_or_payer"), fields.get("location"),
                 fields.get("business_purpose"), fields.get("work_performed"),
                 json.dumps(fields.get("deliverables", [])), provenance.value,
                 fields.get("model_confidence"), created_from_pass, _now()),
            )
        return event_id

    def link_event_source(self, event_id: str, source_id: str, relation: str = "SUPPORTS") -> None:
        with self.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO event_sources VALUES (?,?,?)", (event_id, source_id, relation))

    def promote_event(self, event_id: str, provenance: Provenance, *, reason: str) -> str:
        if provenance not in {Provenance.SOURCE_VERIFIED, Provenance.CORROBORATED,
                              Provenance.CONFLICTED, Provenance.CORRECTED}:
            raise EvidenceError("event promotion requires a material provenance state")
        with self.connect() as conn:
            event = conn.execute(
                "SELECT provenance_class FROM business_events WHERE event_id=?", (event_id,)
            ).fetchone()
            if event is None:
                raise EvidenceError(f"unknown event: {event_id}")
            source_ids = [row[0] for row in conn.execute(
                "SELECT source_id FROM event_sources WHERE event_id=?", (event_id,)
            )]
            self._validate_provenance(conn, provenance, source_ids)
            correction_id = _id("cor")
            conn.execute(
                "INSERT INTO corrections VALUES (?,?,?,?,?,?,?,?)",
                (correction_id, "BUSINESS_EVENT", event_id, event["provenance_class"],
                 provenance.value, reason, None, _now()),
            )
            conn.execute("UPDATE business_events SET provenance_class=? WHERE event_id=?",
                         (provenance.value, event_id))
        return correction_id

    def add_claim(self, *, claim_type: str, claim_value: Optional[str], provenance: Provenance,
                  source_ids: Iterable[str] = (), event_id: Optional[str] = None,
                  model_confidence: Optional[float] = None) -> str:
        with self.connect() as conn:
            ids = self._validate_provenance(conn, provenance, source_ids)
            claim_id = _id("clm")
            conn.execute("INSERT INTO claims VALUES (?,?,?,?,?,?,?)",
                         (claim_id, event_id, claim_type, claim_value, provenance.value,
                          model_confidence, _now()))
            conn.executemany("INSERT INTO claim_sources VALUES (?,?,1)",
                             ((claim_id, source_id) for source_id in ids))
        return claim_id

    def add_transaction(self, *, kind: str, provenance: Provenance,
                        source_ids: Iterable[str] = (), **fields: Any) -> str:
        normalized_kind = kind.upper()
        if normalized_kind not in {"EXPENSE", "INCOME"}:
            raise EvidenceError("transaction kind must be EXPENSE or INCOME")
        classification = fields.get("business_classification") or "UNKNOWN"
        if classification == "OWN_ACCOUNT_TRANSFER" and fields.get("tax_treatment"):
            raise EvidenceError("own-account transfers cannot receive automatic tax treatment")
        transaction_id = _id("txn")
        with self.connect() as conn:
            ids = self._validate_provenance(conn, provenance, source_ids)
            conn.execute(
                """INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (transaction_id, normalized_kind, fields.get("occurred_at"), fields.get("counterparty"),
                 fields.get("amount_minor"), fields.get("currency"), fields.get("payment_reference"),
                 fields.get("event_id"), classification, fields.get("tax_treatment"),
                 provenance.value, _now()),
            )
            conn.executemany("INSERT INTO transaction_sources VALUES (?,?,?)",
                             ((transaction_id, sid, "SUPPORTS") for sid in ids))
        return transaction_id

    def correct(self, *, subject_type: str, subject_id: str, prior: str,
                corrected: str, reason: str, source_id: Optional[str] = None) -> str:
        correction_id = _id("cor")
        with self.connect() as conn:
            conn.execute("INSERT INTO corrections VALUES (?,?,?,?,?,?,?,?)",
                         (correction_id, subject_type, subject_id, prior, corrected,
                          reason, source_id, _now()))
        return correction_id

    def record_conflict(self, *, subject_type: str, subject_id: str, description: str) -> str:
        conflict_id = _id("cnf")
        with self.connect() as conn:
            conn.execute("INSERT INTO conflicts VALUES (?,?,?,?,?,?,?)",
                         (conflict_id, subject_type, subject_id, description, "OPEN", _now(), None))
        return conflict_id

    def flag_review(self, *, subject_type: str, subject_id: str, reason: str) -> str:
        flag_id = _id("rev")
        with self.connect() as conn:
            conn.execute("INSERT INTO review_flags VALUES (?,?,?,?,?,?)",
                         (flag_id, subject_type, subject_id, reason, "OPEN", _now()))
        return flag_id

    def evidence_for_event(self, event_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            event = conn.execute("SELECT * FROM business_events WHERE event_id=?", (event_id,)).fetchone()
            if event is None:
                raise EvidenceError(f"unknown event: {event_id}")
            sources = conn.execute(
                """SELECT s.*, es.relation FROM event_sources es
                JOIN sources s ON s.source_id=es.source_id WHERE es.event_id=?""", (event_id,)
            ).fetchall()
            claims = conn.execute("SELECT * FROM claims WHERE event_id=?", (event_id,)).fetchall()
            transactions = conn.execute("SELECT * FROM transactions WHERE event_id=?", (event_id,)).fetchall()
        return {"event": dict(event), "sources": [dict(row) for row in sources],
                "claims": [dict(row) for row in claims],
                "transactions": [dict(row) for row in transactions]}

    def evidence_for_transaction(self, transaction_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            transaction = conn.execute(
                "SELECT * FROM transactions WHERE transaction_id=?", (transaction_id,)
            ).fetchone()
            if transaction is None:
                raise EvidenceError(f"unknown transaction: {transaction_id}")
            sources = conn.execute(
                """SELECT s.*, ts.relation FROM transaction_sources ts
                JOIN sources s ON s.source_id=ts.source_id WHERE ts.transaction_id=?""",
                (transaction_id,),
            ).fetchall()
            event = None
            if transaction["event_id"]:
                event = conn.execute(
                    "SELECT * FROM business_events WHERE event_id=?", (transaction["event_id"],)
                ).fetchone()
            corrections = conn.execute(
                "SELECT * FROM corrections WHERE subject_type='TRANSACTION' AND subject_id=?",
                (transaction_id,),
            ).fetchall()
            conflicts = conn.execute(
                "SELECT * FROM conflicts WHERE subject_type='TRANSACTION' AND subject_id=?",
                (transaction_id,),
            ).fetchall()
            flags = conn.execute(
                "SELECT * FROM review_flags WHERE subject_type='TRANSACTION' AND subject_id=?",
                (transaction_id,),
            ).fetchall()
        return {"transaction": dict(transaction), "event": dict(event) if event else None,
                "sources": [dict(row) for row in sources],
                "corrections": [dict(row) for row in corrections],
                "conflicts": [dict(row) for row in conflicts],
                "review_flags": [dict(row) for row in flags]}

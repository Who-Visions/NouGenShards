"""HF-first write-ahead buffer for shard capture (Cloud -> Local sync).

A capture is accepted once it is durable in two places: a local SQLite
`pending_shards` table and an append-only JSONL mirror (stand-in for the
private HF dataset commit). Delivery to each node is tracked per node, so a
node that was down catches up by pulling and acking unacked shards.

Pure and dependency-free; the HTTP surface and the HF mirror are wired
around this, not inside it.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import unicodedata
from typing import Callable, Dict, Iterable, List, Optional


def normalize(content: str) -> str:
    """Canonical form used for the content hash: NFC, LF line endings, edge whitespace trimmed."""
    text = unicodedata.normalize("NFC", content or "")
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def content_sha256(content: str) -> str:
    return hashlib.sha256(normalize(content).encode("utf-8")).hexdigest()


class WriteAheadBuffer:
    def __init__(self, db_path: str, mirror_path: Optional[str] = None) -> None:
        self.db_path = db_path
        self.mirror_path = mirror_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pending_shards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_sha256 TEXT UNIQUE NOT NULL,
                payload TEXT NOT NULL,
                event_time TEXT,
                capture_time TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS node_acks (
                content_sha256 TEXT NOT NULL,
                node TEXT NOT NULL,
                acked_at TEXT NOT NULL,
                PRIMARY KEY (content_sha256, node)
            );
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def capture(self, record: dict) -> dict:
        """Persist a shard. Idempotent: the same content hash returns stored=true, duplicate=true."""
        content = record.get("content") or ""
        if not content.strip():
            raise ValueError("content is required")
        sha = content_sha256(content)
        capture_time = record.get("capture_time") or _utc_now_iso()
        event_time = record.get("event_time")
        payload = dict(record, content_sha256=sha, capture_time=capture_time)
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO pending_shards (content_sha256, payload, event_time, capture_time) "
            "VALUES (?, ?, ?, ?)",
            (sha, json.dumps(payload, sort_keys=True), event_time, capture_time),
        )
        self._conn.commit()
        duplicate = cur.rowcount == 0
        if not duplicate:
            self._mirror(payload)
        return {"stored": True, "duplicate": duplicate, "content_sha256": sha,
                "via": "hf-cloud-buffer"}

    def _mirror(self, payload: dict) -> None:
        if not self.mirror_path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.mirror_path)), exist_ok=True)
        with open(self.mirror_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, sort_keys=True) + "\n")

    def pending_for(self, node: str, limit: int = 200) -> List[dict]:
        """Shards this node has not acked yet, oldest first."""
        rows = self._conn.execute(
            "SELECT p.payload FROM pending_shards p "
            "WHERE NOT EXISTS (SELECT 1 FROM node_acks a "
            "  WHERE a.content_sha256 = p.content_sha256 AND a.node = ?) "
            "ORDER BY p.id LIMIT ?",
            (node.lower(), int(limit)),
        ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def ack(self, node: str, shas: Iterable[str]) -> int:
        """Record that `node` durably took these shards. Returns how many were newly acked."""
        now = _utc_now_iso()
        n = 0
        for sha in shas:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO node_acks (content_sha256, node, acked_at) VALUES (?, ?, ?)",
                (sha, node.lower(), now),
            )
            n += cur.rowcount
        self._conn.commit()
        return n

    def fanout(self, record: dict, targets: Dict[str, Callable[[dict], bool]]) -> Dict[str, bool]:
        """POST-like delivery to each node. A node's ack flag is True only if its callable returned True."""
        stored = self.capture(record)
        sha = stored["content_sha256"]
        flags: Dict[str, bool] = {}
        for node, send in targets.items():
            try:
                ok = bool(send(dict(record, content_sha256=sha)))
            except Exception:
                ok = False
            flags[node] = ok
            if ok:
                self.ack(node, [sha])
        return flags


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

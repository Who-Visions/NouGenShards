"""Durable per-lane inboxes with ack and retry (SQLite, standard library only).

One row per envelope id, so a retry, a second route or a re-send is the same
message. State moves accepted -> pushed -> delivered -> acked (or answered),
or to failed/expired. A push that reached nobody is retried with backoff. A
push that reached the receiver's transport without a confirmation (a Claude
Code socket write) is never re-pushed, because the receiver would see it twice;
it waits for the ack. A pull lane (no push adapter, e.g. a phone app) keeps the
message in its inbox until it acks.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .address import Address

OPEN = ("accepted", "pushed", "delivered")
MAX_ATTEMPTS = 8


def backoff_s(attempts: int) -> float:
    return float(min(5 * (2 ** max(attempts - 1, 0)), 600))


class WireStore:
    def __init__(self, path: str = ":memory:") -> None:
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._lock = threading.Lock()
        with self._lock:
            if path != ":memory:":
                self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                  seq INTEGER PRIMARY KEY AUTOINCREMENT,
                  id TEXT UNIQUE NOT NULL, to_lane TEXT NOT NULL, env TEXT NOT NULL,
                  state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                  next_attempt REAL NOT NULL DEFAULT 0, expires REAL NOT NULL,
                  acked_by TEXT, updated REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS messages_lane ON messages(to_lane, seq);
                CREATE TABLE IF NOT EXISTS receipts (
                  rid INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL, receipt TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS receipts_id ON receipts(id, rid);
                """
            )

    # -- writes ------------------------------------------------------------
    def put(self, env: Dict[str, Any], now: Optional[float] = None) -> Tuple[bool, str]:
        """Store an envelope once. Returns (inserted, current_state)."""
        now = time.time() if now is None else now
        lane = Address.parse(env["to"]).lane
        with self._lock:
            try:
                self._db.execute(
                    "INSERT INTO messages(id,to_lane,env,state,next_attempt,expires,updated) VALUES(?,?,?,?,?,?,?)",
                    (env["id"], lane, json.dumps(env), "accepted", now, float(env["expires"]), now))
                return True, "accepted"
            except sqlite3.IntegrityError:
                row = self._db.execute("SELECT state FROM messages WHERE id=?", (env["id"],)).fetchone()
                return False, row[0]

    def add_receipt(self, receipt: Dict[str, Any]) -> None:
        with self._lock:
            self._db.execute("INSERT INTO receipts(id, receipt) VALUES(?,?)", (receipt["id"], json.dumps(receipt)))

    def set_state(self, env_id: str, state: str, now: Optional[float] = None, acked_by: Optional[str] = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            cur = self._db.execute(
                "UPDATE messages SET state=?, updated=?, acked_by=COALESCE(?, acked_by) WHERE id=?",
                (state, now, acked_by, env_id))
            return cur.rowcount == 1

    def record_push(self, env_id: str, pushed: bool, verified: bool, now: Optional[float] = None) -> str:
        """After a push attempt: delivered when verified, else retry later."""
        now = time.time() if now is None else now
        with self._lock:
            row = self._db.execute("SELECT attempts, state FROM messages WHERE id=?", (env_id,)).fetchone()
            if row is None:
                return "unknown"
            attempts, state = row[0] + 1, row[1]
            if state not in OPEN:
                return state  # acked/answered meanwhile: never move it back
            if verified:
                new = "delivered"
            elif pushed:
                new = "pushed"  # it reached the receiver's transport: wait for the ack, never re-push
            elif attempts >= MAX_ATTEMPTS:
                new = "failed"
            else:
                new = "accepted"  # reached nobody: retry with backoff
            self._db.execute("UPDATE messages SET state=?, attempts=?, next_attempt=?, updated=? WHERE id=?",
                             (new, attempts, now + backoff_s(attempts), now, env_id))
            return new

    def claim(self, env_id: str, now: Optional[float] = None, lease_s: float = 600.0) -> bool:
        """Take one open message for a push attempt, atomically.

        Only one caller (send or any pump) can claim a due message: the claim
        moves its next attempt past the lease, so a concurrent pump can't pick it
        up while an adapter call is in flight. record_push sets the real next
        attempt afterwards; a crash mid-push retries once the lease runs out.
        """
        now = time.time() if now is None else now
        with self._lock:
            cur = self._db.execute(
                "UPDATE messages SET next_attempt=? WHERE id=? AND state='accepted' AND next_attempt<=?",
                (now + lease_s, env_id, now))
            return cur.rowcount == 1

    def park(self, env_id: str) -> None:
        """Keep a message in its inbox and out of the retry queue (pinned to a
        receiver this hub's transports can't reach: it must not wake anyone else)."""
        with self._lock:
            self._db.execute("UPDATE messages SET next_attempt=expires WHERE id=?", (env_id,))

    def expire(self, now: Optional[float] = None) -> List[str]:
        now = time.time() if now is None else now
        with self._lock:
            ids = [r[0] for r in self._db.execute(
                "SELECT id FROM messages WHERE expires<=? AND state IN (?,?,?)", (now, *OPEN))]
            self._db.executemany("UPDATE messages SET state='expired', updated=? WHERE id=?", [(now, i) for i in ids])
            return ids

    # -- reads -------------------------------------------------------------
    def get(self, env_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._db.execute("SELECT seq, env, state, attempts, acked_by FROM messages WHERE id=?",
                                   (env_id,)).fetchone()
        if row is None:
            return None
        return {"seq": row[0], "env": json.loads(row[1]), "state": row[2], "attempts": row[3], "acked_by": row[4]}

    def receipts(self, env_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            return [json.loads(r[0]) for r in self._db.execute(
                "SELECT receipt FROM receipts WHERE id=? ORDER BY rid", (env_id,))]

    def inbox(self, lane: str, session: Optional[str] = None, node: Optional[str] = None,
              after: int = 0, limit: int = 25, include_acked: bool = False,
              model: str = "", app: bool = False) -> List[Dict[str, Any]]:
        """Open messages for one receiver, oldest first, by seq cursor."""
        states = OPEN + (("acked", "answered") if include_acked else ())
        marks = ",".join("?" * len(states))
        with self._lock:
            rows = self._db.execute(
                f"SELECT seq, env, state FROM messages WHERE to_lane=? AND seq>? AND state IN ({marks}) ORDER BY seq",
                (lane, int(after), *states)).fetchall()
        out = []
        for seq, raw, state in rows:
            env = json.loads(raw)
            if Address.parse(env["to"]).matches(lane, session, node, model, app):
                out.append({"seq": seq, "state": state, "env": env})
                if len(out) >= max(1, min(int(limit), 100)):
                    break
        return out

    def due(self, lanes, now: Optional[float] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Envelopes for push lanes whose next attempt is due (pull lanes never are)."""
        now = time.time() if now is None else now
        lanes = sorted(set(lanes))
        if not lanes:
            return []
        marks = ",".join("?" * len(lanes))
        with self._lock:
            rows = self._db.execute(
                "SELECT env FROM messages WHERE state='accepted' AND next_attempt<=? AND expires>? "
                f"AND to_lane IN ({marks}) ORDER BY next_attempt LIMIT ?", (now, now, *lanes, int(limit))).fetchall()
        return [json.loads(r[0]) for r in rows]

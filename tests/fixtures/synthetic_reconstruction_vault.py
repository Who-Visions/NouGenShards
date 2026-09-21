"""Synthetic multi-vault fixture for reconstructive recall tests/benchmarks.

Every project, node, person and value here is invented. No real vault rows,
no personal data. Three in-memory SQLite FTS5 vaults stand in for fleet nodes.
"""
from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional, Sequence, Tuple

from nougen_shards.reconstruction import SourceUnavailable

# (key, vault, kind, state, date, entities, title, body)
ROWS = [
    ("T01", "alpha", "shard", "live", "2026-03-02", ["lantern", "gateway"], "Lantern gateway moved to port 8844", "The lantern gateway now listens on port 8844."),
    ("D01", "beta", "shard", "retracted", "2026-02-20", ["lantern", "gateway"], "Lantern gateway moved to port 8811", "Retracted: lantern gateway port 8811 was a typo."),
    ("T02", "beta", "shard", "live", "2026-04-10", ["orchid", "backup"], "Orchid node backup runs nightly at 02:30", "Orchid backup job schedule set nightly."),
    ("D02", "alpha", "shard", "live", "2026-04-11", ["heron", "backup"], "Heron node backup runs nightly at 01:00", "Heron backup job schedule set nightly."),
    ("T03", "gamma", "shard", "live", "2026-05-05", ["mira vance", "ledger"], "Mira Vance approved the ledger schema v3", "Ledger schema v3 approved by Mira Vance."),
    ("D03", "gamma", "shard", "superseded", "2026-01-11", ["mira vance", "ledger"], "Mira Vance rejected the ledger schema v2", "Ledger schema v2 rejected by Mira Vance."),
    ("T04", "alpha", "shard", "live", "2026-06-01", ["kestrel", "transcription"], "Kestrel transcription lane switched to CPU", "Kestrel transcription runs on cpu now."),
    ("T05", "beta", "relay", "live", "2026-06-12", ["quill", "tunnel"], "Relay: pin tunnel hostname for Quill", "Handoff asking to pin the quill tunnel hostname."),
    ("A05", "gamma", "shard", "live", "2026-06-13", ["quill", "tunnel"], "Decision: Quill tunnel hostname pinned to q.example.test", "Pinned after the relay request."),
    ("T06", "gamma", "shard", "live", "2026-07-03", ["quill", "search"], "Quill search timeout raised to 45 seconds", "Quill search timeout raised."),
    ("T07", "alpha", "shard", "live", "2026-02-14", ["heron", "embedding"], "Heron embedding model changed to minilm", "Heron embedding model changed."),
    ("D07", "beta", "shard", "live", "2026-08-01", ["heron", "embedding"], "Heron embedding model changed to bge", "Heron embedding model changed."),
    ("T08", "beta", "shard", "live", "2026-03-20", ["sparrow", "dashboard"], "Sparrow dashboard colour tokens unified", "Sparrow dashboard colour tokens unified."),
    ("D08", "gamma", "shard", "live", "2026-03-21", ["kestrel", "dashboard"], "Kestrel dashboard colour tokens unified", "Kestrel dashboard colour tokens unified."),
    ("T09", "gamma", "shard", "live", "2026-05-18", ["orchid", "disk"], "Orchid disk alert threshold set to 90 percent", "Orchid disk alert threshold."),
    ("T10", "alpha", "shard", "live", "2026-07-15", ["lantern", "rate limit"], "Lantern rate limit fixed after reconnect loop", "Lantern rate limit fixed; reconnect loop closed."),
    ("T11", "beta", "shard", "live", "2026-04-02", ["mira vance", "invoice"], "Mira Vance owns the invoice export", "Invoice export owner is Mira Vance."),
    ("D11", "alpha", "shard", "live", "2026-04-03", ["tomas reed", "payroll"], "Tomas Reed owns the payroll export", "Payroll export owner is Tomas Reed."),
    ("T12", "gamma", "shard", "live", "2026-06-20", ["kestrel", "audio"], "Kestrel audio chunk size reduced to 30 seconds", "Kestrel audio chunk size reduced."),
    ("T13", "alpha", "shard", "live", "2026-02-01", ["heron", "sqlite"], "Decision: Heron keeps SQLite over Postgres", "Heron decision sqlite retained."),
    ("T14", "beta", "shard", "live", "2026-05-09", ["sparrow", "build"], "Failure: Sparrow build broke on missing font", "Sparrow build broke; font missing."),
    ("T15", "gamma", "shard", "live", "2026-07-22", ["quill", "cache"], "Quill cache warmup added at boot", "Quill cache warmup at boot."),
    ("T16", "alpha", "shard", "live", "2026-08-05", ["orchid", "fan"], "Orchid fan curve lowered for quieter runs", "Orchid fan curve lowered, quieter."),
    ("T17", "gamma", "relay", "live", "2026-08-09", ["lantern", "docs"], "Relay: Lantern docs moved to the wiki", "Handoff: lantern docs moved to wiki."),
    ("T18", "beta", "shard", "live", "2026-08-12", ["kestrel", "speaker labels"], "Kestrel speaker labels disabled by default", "Kestrel speaker labels disabled."),
    ("T19", "gamma", "shard", "live", "2026-08-20", ["heron", "compaction"], "Heron nightly compaction moved to Sunday", "Heron compaction weekly on sunday."),
    ("T20", "alpha", "shard", "live", "2026-09-01", ["sparrow", "login"], "Sparrow login uses OAuth sign-in", "Sparrow login oauth."),
]

EDGES = [("T05", "A05", "decided_by"), ("T14", "T20", "unrelated_followup")]

ALIASES: Dict[str, List[str]] = {
    "gateway": ["front door"], "orchid": ["orch"], "backup": ["snapshot"],
    "ledger": ["books"], "approved": ["sign off", "signed off"], "schema": ["table layout"],
    "transcription": ["speech to text"], "cpu": ["processor"], "tunnel": ["pipe"],
    "search": ["lookup"], "timeout": ["deadline"], "raised": ["bump"],
    "embedding": ["vector"], "changed": ["swap"], "dashboard": ["panel"],
    "colour": ["palette"], "disk": ["storage"], "alert": ["warning"], "threshold": ["level"],
    "rate limit": ["throttling"], "loop": ["storm"], "invoice": ["bill"], "owns": ["responsible"],
    "audio": ["sound"], "chunk": ["slice"], "size": ["length"], "reduced": ["smaller"],
    "decision": ["choice"], "sqlite": ["database"], "build": ["compile"], "broke": ["crash"],
    "font": ["typeface"], "warmup": ["preload"], "boot": ["startup"], "fan": ["cooling"],
    "quieter": ["noise"], "lowered": ["tweak"], "docs": ["documentation"],
    "speaker labels": ["diarization"], "disabled": ["off"], "compaction": ["vacuum"],
    "login": ["auth"], "relay": ["handoff"],
}

ENTITIES = sorted({e for r in ROWS for e in r[5]})

# 20 deliberately badly-worded queries -> expected key
BAD_QUERIES: List[Tuple[str, str]] = [
    ("what port does the lantern front door use now", "T01"),
    ("when does orch do its snapshot job", "T02"),
    ("did mira sign off on the books table layout", "T03"),
    ("kestrel speech to text on processor", "T04"),
    ("the handoff about quill pipe hostname", "T05"),
    ("quill lookup deadline bump", "T06"),
    ("heron vector model swap in february 2026", "T07"),
    ("sparrow panel palette cleanup", "T08"),
    ("orch storage warning level", "T09"),
    ("lantern throttling bug from reconnect storm", "T10"),
    ("who is responsible for mira vance bill export", "T11"),
    ("kestrel sound slice length smaller", "T12"),
    ("heron database choice", "T13"),
    ("sparrow compile crash typeface", "T14"),
    ("quill preload on startup", "T15"),
    ("orch cooling noise tweak", "T16"),
    ("handoff where lantern documentation went", "T17"),
    ("kestrel diarization off", "T18"),
    ("heron vacuum schedule", "T19"),
    ("sparrow auth flow", "T20"),
]

# Known-positive controls: good wording that single-shot must hit.
GOOD_QUERIES: List[Tuple[str, str]] = [
    ("lantern gateway port", "T01"),
    ("quill search timeout", "T06"),
]


class SyntheticVault:
    def __init__(self, name: str, rows: Sequence[tuple], edges: Sequence[tuple]):
        self.name = name
        self.available = True
        self.calls = 0
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE ev(key TEXT PRIMARY KEY, kind TEXT, state TEXT, date TEXT, entities TEXT, title TEXT, body TEXT)")
        self.conn.execute("CREATE VIRTUAL TABLE ev_fts USING fts5(key UNINDEXED, title, body, entities)")
        for key, vault, kind, state, date, ents, title, body in rows:
            if vault != name:
                continue
            self.conn.execute("INSERT INTO ev VALUES (?,?,?,?,?,?,?)", (key, kind, state, date, "|".join(ents), title, body))
            self.conn.execute("INSERT INTO ev_fts VALUES (?,?,?,?)", (key, title, body, " ".join(ents)))
        self.edges = list(edges)

    def _check(self):
        self.calls += 1
        if not self.available:
            raise SourceUnavailable(f"{self.name} offline (simulated)")

    @staticmethod
    def _row(r) -> dict:
        return {"key": r[0], "kind": r[1], "state": r[2], "date": r[3],
                "entities": r[4].split("|") if r[4] else [], "title": r[5], "body": r[6]}

    def search(self, query: str, limit: int, *, mode: str = "all",
               kinds: Optional[Sequence[str]] = None,
               date_range: Optional[Tuple[str, str]] = None) -> List[dict]:
        self._check()
        toks = [t for t in "".join(ch if ch.isalnum() else " " for ch in query.lower()).split() if len(t) >= 3]
        if not toks:
            return []
        expr = (" OR " if mode == "any" else " ").join('"' + t + '"' for t in toks)
        sql = ("SELECT e.key,e.kind,e.state,e.date,e.entities,e.title,e.body FROM ev_fts f "
               "JOIN ev e ON e.key=f.key WHERE ev_fts MATCH ?")
        args: list = [expr]
        if kinds:
            sql += " AND e.kind IN (%s)" % ",".join("?" * len(kinds))
            args += list(kinds)
        if date_range:
            sql += " AND e.date BETWEEN ? AND ?"
            args += list(date_range)
        sql += " ORDER BY bm25(ev_fts) LIMIT ?"
        args.append(limit)
        return [self._row(r) for r in self.conn.execute(sql, args)]

    def neighbours(self, key: str) -> List[Tuple[str, str]]:
        self._check()
        out = []
        for a, b, rel in self.edges:
            if a == key:
                out.append((b, rel))
            elif b == key:
                out.append((a, rel))
        return out

    def get(self, key: str) -> Optional[dict]:
        self._check()
        r = self.conn.execute("SELECT key,kind,state,date,entities,title,body FROM ev WHERE key=?", (key,)).fetchone()
        return self._row(r) if r else None


def build_vaults() -> List[SyntheticVault]:
    # Edges are a fleet-wide relation table here; every vault can report them.
    return [SyntheticVault(n, ROWS, EDGES) for n in ("alpha", "beta", "gamma")]

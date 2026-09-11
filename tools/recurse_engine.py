"""Recurse Engine: Recursive Dialogue, Dream Payoff & Asset Ledger for Shadow Dweller.

Implements Dave's 4-Stage Recursive Architecture:
  1. Setup: Early statement, dream, warning, insult, proverb, or sensory fragment.
     Must be emotionally self-contained without requiring future lore.
  2. First Echo: Reappearance under shifted context (instinct, sensory anomaly, anomaly).
     Must honor Vol 1 Level 1-3 ceiling (no mastered chronocutting or tear traversal).
  3. Inversion: Flipped meaning across timelines (Prime vs SDX) or moral polarity.
  4. Final Payoff: Causal revelation that rewards the Vol 5 rewatch standard.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_DB_PATH = Path(os.environ.get("NOUGEN_RECURSE_DB", Path.home() / ".nougen" / "recurse_ledger.db"))


@dataclass
class RecurseEntry:
    id: str
    entity: str           # e.g., 'xoah', 'sdx', 'rixa', 'whitelock', 'sireva', 'kage_tanak', 'veil'
    category: str         # 'dialogue', 'dream', 'motif', 'combat_line', 'sensory_anomaly', 'prophecy'
    title: str            # Short identifier
    setup: str            # Stage 1: Initial line or sensory beat
    setup_context: str    # e.g., 'Vol 1 Act 1 Scene 3'
    first_echo: Optional[str] = None      # Stage 2: Second life
    first_echo_context: Optional[str] = None
    inversion: Optional[str] = None       # Stage 3: Timeline or polar reversal
    inversion_context: Optional[str] = None
    final_payoff: Optional[str] = None    # Stage 4: Ultimate causal revelation
    final_payoff_context: Optional[str] = None
    rewatch_score: int = 5                # 1 to 10 scale of structural impact
    notes: Optional[str] = None
    created_utc: str = ""

    def is_complete(self) -> bool:
        return bool(self.setup and self.first_echo and self.inversion and self.final_payoff)

    def audit(self) -> List[str]:
        warnings = []
        if not self.setup:
            warnings.append("Missing Stage 1 (setup)")
        if not self.first_echo:
            warnings.append("Missing Stage 2 (first_echo)")
        if not self.inversion:
            warnings.append("Missing Stage 3 (inversion)")
        if not self.final_payoff:
            warnings.append("Missing Stage 4 (final_payoff)")
        # Check Level 1-3 guardrail on Vol 1
        v1_text = (self.setup or "") + " " + (self.first_echo or "")
        forbidden_v1_terms = ["tear traversal", "mastered chronocut", "god mode", "temporal control"]
        for term in forbidden_v1_terms:
            if term in v1_text.lower():
                warnings.append(f"Guardrail violation: Early stage mentions '{term}' (violates Vol 1 Level 1-3 ceiling)")
        return warnings


def init_db(db_path: Path = DEFAULT_DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recurse_ledger (
                id TEXT PRIMARY KEY,
                entity TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                setup TEXT NOT NULL,
                setup_context TEXT NOT NULL,
                first_echo TEXT,
                first_echo_context TEXT,
                inversion TEXT,
                inversion_context TEXT,
                final_payoff TEXT,
                final_payoff_context TEXT,
                rewatch_score INTEGER DEFAULT 5,
                notes TEXT,
                created_utc TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_recurse_entity ON recurse_ledger(entity)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_recurse_category ON recurse_ledger(category)")
        conn.commit()
    finally:
        conn.close()


def add_entry(entry: RecurseEntry, db_path: Path = DEFAULT_DB_PATH) -> str:
    init_db(db_path)
    if not entry.id:
        entry.id = str(uuid.uuid4())[:8]
    if not entry.created_utc:
        entry.created_utc = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            INSERT OR REPLACE INTO recurse_ledger (
                id, entity, category, title, setup, setup_context,
                first_echo, first_echo_context, inversion, inversion_context,
                final_payoff, final_payoff_context, rewatch_score, notes, created_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.id, entry.entity, entry.category, entry.title, entry.setup, entry.setup_context,
            entry.first_echo, entry.first_echo_context, entry.inversion, entry.inversion_context,
            entry.final_payoff, entry.final_payoff_context, entry.rewatch_score, entry.notes, entry.created_utc
        ))
        conn.commit()
        return entry.id
    finally:
        conn.close()


def list_entries(entity: Optional[str] = None, category: Optional[str] = None, db_path: Path = DEFAULT_DB_PATH) -> List[RecurseEntry]:
    init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        sql = "SELECT * FROM recurse_ledger WHERE 1=1"
        params = []
        if entity:
            sql += " AND entity = ?"
            params.append(entity.lower())
        if category:
            sql += " AND category = ?"
            params.append(category.lower())
        sql += " ORDER BY rewatch_score DESC, created_utc DESC"

        rows = conn.execute(sql, params).fetchall()
        entries = []
        for r in rows:
            entries.append(RecurseEntry(
                id=r["id"],
                entity=r["entity"],
                category=r["category"],
                title=r["title"],
                setup=r["setup"],
                setup_context=r["setup_context"],
                first_echo=r["first_echo"],
                first_echo_context=r["first_echo_context"],
                inversion=r["inversion"],
                inversion_context=r["inversion_context"],
                final_payoff=r["final_payoff"],
                final_payoff_context=r["final_payoff_context"],
                rewatch_score=r["rewatch_score"],
                notes=r["notes"],
                created_utc=r["created_utc"]
            ))
        return entries
    finally:
        conn.close()


def audit_ledger(db_path: Path = DEFAULT_DB_PATH) -> dict:
    entries = list_entries(db_path=db_path)
    total = len(entries)
    complete = 0
    warnings_list = []

    for e in entries:
        if e.is_complete():
            complete += 1
        errs = e.audit()
        if errs:
            warnings_list.append({"id": e.id, "title": e.title, "entity": e.entity, "warnings": errs})

    return {
        "total_entries": total,
        "complete_entries": complete,
        "completion_rate": round((complete / total * 100) if total else 0, 1),
        "issues": warnings_list
    }


def main():
    parser = argparse.ArgumentParser(description="Recurse Engine: 4-Stage Dialogue & Motif Payoff Ledger")
    subparsers = parser.add_subparsers(dest="subcommand")

    # init
    subparsers.add_parser("init", help="Initialize the recurse ledger database")

    # add
    add_parser = subparsers.add_parser("add", help="Add a 4-stage recursive entry")
    add_parser.add_argument("--entity", required=True, help="Entity/Character (xoah, sdx, rixa, whitelock, veil, etc.)")
    add_parser.add_argument("--category", required=True, help="Category (dialogue, dream, motif, combat_line, sensory_anomaly)")
    add_parser.add_argument("--title", required=True, help="Short title/slug")
    add_parser.add_argument("--setup", required=True, help="Stage 1: Setup line or sensory detail")
    add_parser.add_argument("--setup-context", required=True, help="Stage 1 Context (e.g., 'Vol 1 Act 1 Scene 2')")
    add_parser.add_argument("--first-echo", help="Stage 2: First echo / reappearance")
    add_parser.add_argument("--first-echo-context", help="Stage 2 Context (e.g., 'Vol 2 Act 1')")
    add_parser.add_argument("--inversion", help="Stage 3: Inversion across timeline or polarity")
    add_parser.add_argument("--inversion-context", help="Stage 3 Context (e.g., 'Vol 3 Act 3 SDX')")
    add_parser.add_argument("--final-payoff", help="Stage 4: Final causal payoff")
    add_parser.add_argument("--final-payoff-context", help="Stage 4 Context (e.g., 'Vol 5 Climax')")
    add_parser.add_argument("--score", type=int, default=8, help="Rewatch value score (1-10)")
    add_parser.add_argument("--notes", help="Editorial or canon notes")

    # list
    list_parser = subparsers.add_parser("list", help="List recursive entries")
    list_parser.add_argument("--entity", help="Filter by entity")
    list_parser.add_argument("--category", help="Filter by category")
    list_parser.add_argument("--json", action="store_true", help="Output JSON")

    # audit
    audit_parser = subparsers.add_parser("audit", help="Audit ledger for completeness and Vol 1 Level 1-3 guardrails")
    audit_parser.add_argument("--json", action="store_true", help="Output JSON")

    args = parser.parse_args()

    if args.subcommand == "init":
        init_db()
        print(f"Initialized recurse ledger at {DEFAULT_DB_PATH}")

    elif args.subcommand == "add":
        entry = RecurseEntry(
            id="",
            entity=args.entity,
            category=args.category,
            title=args.title,
            setup=args.setup,
            setup_context=args.setup_context,
            first_echo=args.first_echo,
            first_echo_context=args.first_echo_context,
            inversion=args.inversion,
            inversion_context=args.inversion_context,
            final_payoff=args.final_payoff,
            final_payoff_context=args.final_payoff_context,
            rewatch_score=args.score,
            notes=args.notes
        )
        eid = add_entry(entry)
        print(f"✅ Added recurse entry [{eid}] '{entry.title}' for {entry.entity}")

    elif args.subcommand == "list":
        entries = list_entries(entity=args.entity, category=args.category)
        if args.json:
            print(json.dumps([asdict(e) for e in entries], indent=2))
        else:
            print(f"Found {len(entries)} recurse entries:")
            for e in entries:
                status = "✅ Complete" if e.is_complete() else "⚠️ Partial"
                print(f"- [{e.id}] [{e.entity.upper()}/{e.category}] '{e.title}' (Score: {e.rewatch_score}/10) — {status}")
                print(f"    1. Setup: {e.setup} ({e.setup_context})")
                if e.first_echo:
                    print(f"    2. Echo: {e.first_echo} ({e.first_echo_context})")
                if e.inversion:
                    print(f"    3. Inversion: {e.inversion} ({e.inversion_context})")
                if e.final_payoff:
                    print(f"    4. Payoff: {e.final_payoff} ({e.final_payoff_context})")

    elif args.subcommand == "audit":
        res = audit_ledger()
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print("======================================================================")
            print(f"RECURSE LEDGER AUDIT: {res['complete_entries']}/{res['total_entries']} Complete ({res['completion_rate']}%)")
            print("======================================================================")
            if res["issues"]:
                print(f"Found {len(res['issues'])} issues:")
                for item in res["issues"]:
                    print(f"- [{item['id']}] {item['entity']}/{item['title']}:")
                    for w in item["warnings"]:
                        print(f"    ⚠️ {w}")
            else:
                print("✅ All entries satisfy the 4-stage rewatch and guardrail standards.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

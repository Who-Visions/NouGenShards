"""Ingest a pending markdown shard into the Watchtower memory vault.

Run this from a normal user shell, not from the restricted Codex sandbox, when
the sandbox cannot write to ``C:\\Users\\super\\Watchtower\\vault``.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
from datetime import datetime
from pathlib import Path


DEFAULT_DB = Path(r"C:\Users\super\Watchtower\vault\nougenai_memory_vault.db")
DEFAULT_SHARD = (
    Path(__file__).resolve().parents[1]
    / "pending_shards"
    / "2026-06-11_nougenshards_mcp_history_repair.md"
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _section(markdown: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\s*$"
    match = re.search(pattern, markdown, flags=re.MULTILINE)
    if not match:
        return ""

    start = match.end()
    next_match = re.search(r"^## .+?$", markdown[start:], flags=re.MULTILINE)
    end = start + next_match.start() if next_match else len(markdown)
    return markdown[start:end].strip()


def parse_pending_shard(path: Path) -> dict:
    markdown = path.read_text(encoding="utf-8")
    title_match = re.search(r"^#\s+(.+)$", markdown, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.stem

    finding = _clean(_section(markdown, "Finding"))
    logic_parts = [
        _section(markdown, "Implementation"),
        _section(markdown, "Verification"),
        _section(markdown, "Related Test-Isolation Issue"),
    ]
    logic = _clean("\n\n".join(part for part in logic_parts if part))
    tags = _section(markdown, "Tags").replace("`", "").strip()

    return {
        "category": "CODEX_SESSION_FIX",
        "source": f"Pending Shard: {title}",
        "finding": finding,
        "logic": logic,
        "tags": tags,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    }


def ingest(db_path: Path, shard_path: Path, confirm: bool) -> int:
    row = parse_pending_shard(shard_path)

    if confirm:
        conn = sqlite3.connect(str(db_path), timeout=30)
    else:
        db_uri = "file:" + str(db_path).replace("\\", "/") + "?mode=ro&immutable=1"
        conn = sqlite3.connect(db_uri, uri=True)
    try:
        existing = conn.execute(
            "SELECT id FROM shards WHERE source = ? AND finding = ? LIMIT 1",
            (row["source"], row["finding"]),
        ).fetchone()
        if existing:
            return int(existing[0])

        next_id = int(conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM shards").fetchone()[0])
        if not confirm:
            print(f"DRY RUN: would insert shard id {next_id} into {db_path}")
            print(f"source: {row['source']}")
            return next_id

        with conn:
            conn.execute(
                """
                INSERT INTO shards (
                    id, category, source, finding, logic, timestamp,
                    utility_score, access_count, outcome_history, tags
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    next_id,
                    row["category"],
                    row["source"],
                    row["finding"],
                    row["logic"],
                    row["timestamp"],
                    1.0,
                    0,
                    "[]",
                    row["tags"],
                ),
            )
            conn.execute(
                """
                INSERT INTO shards_fts(rowid, category, tags, source, finding, logic)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    next_id,
                    row["category"],
                    row["tags"],
                    row["source"],
                    row["finding"],
                    row["logic"],
                ),
            )
            conn.execute(
                """
                INSERT INTO predictive_shards_fts(rowid, finding, category, tags)
                VALUES (?, ?, ?, ?)
                """,
                (next_id, row["finding"], row["category"], row["tags"]),
            )
        return next_id
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--shard", type=Path, default=DEFAULT_SHARD)
    parser.add_argument("--confirm", action="store_true", help="Actually write to the vault DB.")
    args = parser.parse_args()

    shard_id = ingest(args.db, args.shard, args.confirm)
    action = "Inserted" if args.confirm else "Prepared"
    print(f"{action} shard id {shard_id}.")


if __name__ == "__main__":
    main()

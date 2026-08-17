"""Local SQLite vault connector for federated retrieval."""
import os
import re
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_valid_identifier(ident: str) -> bool:
    """Validate table or column name to prevent SQL injection in dynamic queries."""
    if not ident or not isinstance(ident, str):
        return False
    return bool(_IDENTIFIER_RE.match(ident))


def query_local_vaults(query: str, vault_configs: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
    """Queries registered local SQLite vaults and maps results to standard shard format."""
    results = []
    if not query:
        return results

    tokens = [t for t in query.split() if t.isalnum()]
    if not tokens:
        tokens = [query]

    for conf in vault_configs:
        v_path = conf.get("path")
        table = conf.get("table_name", "shards")
        title_col = conf.get("title_col", "title")
        content_col = conf.get("content_col", "content")

        if not v_path or not os.path.exists(v_path):
            continue

        if not all(_is_valid_identifier(x) for x in [table, title_col, content_col]):
            continue

        stem = Path(str(v_path)).stem
        try:
            conn = sqlite3.connect(f"file:{v_path}?mode=ro", uri=True, timeout=5.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # LIKE-based keyword matching across title and content columns
            clauses = []
            params = []
            for t in tokens:
                clauses.append(f'("{title_col}" LIKE ? OR "{content_col}" LIKE ?)')
                pattern = f"%{t}%"
                params.extend([pattern, pattern])

            where_sql = " OR ".join(clauses) if clauses else "1=1"
            cursor.execute(f"""
                SELECT rowid as id, "{title_col}" as title, "{content_col}" as content
                FROM "{table}"
                WHERE {where_sql}
                LIMIT ?
            """, (*params, limit))

            rows = cursor.fetchall()
            for r in rows:
                results.append({
                    "id": f"vault_{stem}_{r['id']}",
                    "title": r["title"] or "Untitled",
                    "content": r["content"] or "",
                    "utility_score": 1.0,
                    "_db_index": f"vault_{stem}",
                })
            conn.close()
        except Exception:
            continue

    return results

"""SQLAlchemy Connector for external databases."""
import hashlib
import json
import logging
import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError, ArgumentError

logger = logging.getLogger(__name__)

# Only real network database backends are allowed. This blocks create_engine
# from being pointed at sqlite:///arbitrary files or other local/SSRF schemes
# via an attacker-influenced external-DB config.
_ALLOWED_DB_BACKENDS = {
    "postgresql", "mysql", "mariadb", "mssql", "oracle", "cockroachdb",
}


def is_valid_identifier(ident: str) -> bool:
    """Strict regex for safe SQL identifiers."""
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", ident))


def is_allowed_db_uri(uri: str) -> bool:
    """Allow only known network DB drivers; reject file-based/local schemes."""
    try:
        backend = make_url(uri).get_backend_name()
    except (ArgumentError, ValueError, AttributeError):
        return False
    return backend in _ALLOWED_DB_BACKENDS


def _stable_hash(value) -> str:
    """Deterministic content hash.

    Python's built-in hash() is salted per process (PYTHONHASHSEED), so it
    produced a different id/file_hash for the same external row on every
    restart — breaking dedup and stable identity. SHA-256 is reproducible.
    """
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def query_external_dbs(query: str, db_configs: list, limit: int = 3) -> list:
    """Queries external databases and maps results to Shard format."""
    results = []
    keywords = [w for w in query.split() if w.isalnum()]
    if not keywords:
        keywords = [query]

    for conf in db_configs:
        try:
            table = conf['table_name']
            title_col = conf['title_col']
            content_col = conf['content_col']

            # Patch 16.E: Validate identifiers (Module 10: Constraints)
            if not all(is_valid_identifier(x) for x in [table, title_col, content_col]):
                continue

            # Reject non-network DB URIs (sqlite/file/etc.) before connecting.
            if not is_allowed_db_uri(conf['uri']):
                logger.warning("external DB skipped (conf %s): disallowed URI scheme",
                               conf.get('id', '?'))
                continue

            # Module 10: Integrate Constraints (Timeout & Connection Pooling)
            engine = create_engine(conf['uri'], pool_pre_ping=True,
                                   connect_args={"connect_timeout": 5})
            try:
                with engine.connect() as conn:
                    where_clauses = []
                    params = {}
                    for i, kw in enumerate(keywords):
                        where_clauses.append(
                            f"({title_col} LIKE :kw{i} OR {content_col} LIKE :kw{i})")
                        params[f"kw{i}"] = f"%{kw}%"

                    where_sql = " OR ".join(where_clauses)
                    # LIMIT is not valid on every allowed backend: mssql uses
                    # SELECT TOP, oracle (12c+) uses FETCH FIRST. Build the row
                    # cap dialect-aware. Identifiers are still validated above and
                    # the cap is a bound param, so no injection surface is added.
                    backend = make_url(conf['uri']).get_backend_name()
                    select_top = ""
                    limit_clause = ""
                    if backend == "mssql":
                        select_top = "TOP (:limit) "
                    elif backend == "oracle":
                        limit_clause = " FETCH FIRST :limit ROWS ONLY"
                    else:
                        limit_clause = " LIMIT :limit"
                    sql_text = text(
                        f"SELECT {select_top}{title_col} AS title, "
                        f"{content_col} AS content "
                        f"FROM {table} WHERE {where_sql}{limit_clause}")
                    params['limit'] = limit

                    res = conn.execute(sql_text, params)
                    for row in res:
                        item = dict(row._mapping)
                        results.append({
                            "id": f"ext_{conf['id']}_{_stable_hash(item['title'])[:16]}",
                            "event_type": "EXTERNAL_DB",
                            "title": item['title'],
                            "content": item['content'],
                            "tags": json.dumps(["external"]),
                            "utility_score": 1.0,
                            "access_count": 0,
                            "file_hash": _stable_hash(item['content']),
                            "bm25_score": 0.0,
                            "final_score": 0.5,
                            "_db_index": f"ext_{conf['id']}"
                        })
            finally:
                # Dispose the engine/pool so file descriptors aren't leaked per sweep.
                engine.dispose()
        except (SQLAlchemyError, KeyError, TypeError, ValueError) as exc:
            # Resilient (one bad external DB must not kill the sweep) but no
            # longer silent. Log by conf id, never the URI — it carries creds.
            logger.warning("external DB skipped (conf %s): %s: %s",
                           conf.get('id', '?'), type(exc).__name__, exc)
            continue
    return results

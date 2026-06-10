"""SQLAlchemy Connector for external databases."""
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

def query_external_dbs(query: str, db_configs: list, limit: int = 3) -> list:
    """Queries external databases and maps results to Shard format."""
    results = []
    keywords = [w for w in query.split() if w.isalnum()]
    if not keywords: keywords = [query]
    
    for conf in db_configs:
        try:
            # Module 10: Integrate Constraints (Timeout & Connection Pooling)
            engine = create_engine(conf['uri'], pool_pre_ping=True, connect_args={"connect_timeout": 5})
            with engine.connect() as conn:
                table = conf['table_name']
                title_col = conf['title_col']
                content_col = conf['content_col']
                
                where_clauses = []
                params = {}
                for i, kw in enumerate(keywords):
                    where_clauses.append(f"({title_col} LIKE :kw{i} OR {content_col} LIKE :kw{i})")
                    params[f"kw{i}"] = f"%{kw}%"
                
                where_sql = " OR ".join(where_clauses)
                sql_text = text(f"SELECT {title_col} AS title, {content_col} AS content FROM {table} WHERE {where_sql} LIMIT :limit")
                params['limit'] = limit
                
                res = conn.execute(sql_text, params)
                for row in res:
                    item = dict(row._mapping)
                    results.append({
                        "id": f"ext_{conf['id']}_{abs(hash(item['title']))}",
                        "event_type": "EXTERNAL_DB",
                        "title": item['title'],
                        "content": item['content'],
                        "tags": "[\"external\"]",
                        "utility_score": 1.0,
                        "access_count": 0,
                        "file_hash": str(hash(item['content'])),
                        "bm25_score": 0.0,
                        "final_score": 0.5,
                        "_db_index": f"ext_{conf['id']}"
                    })
        except Exception: continue
    return results

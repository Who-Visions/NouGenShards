import os
import json
import sqlite3
import glob
from pathlib import Path
from datetime import datetime, timedelta, timezone
from . import core

_HOME = Path.home()
SHARDS_DIR = os.environ.get("NOUGEN_VAULT_DIR", str(_HOME / ".nougen" / "shards"))


def _shards_dir() -> str:
    """Resolve per call so a request ContextVar cannot be bypassed."""
    if core.vault_context_is_set():
        return str(core.active_vault_dir())
    return SHARDS_DIR
TRACKER_DIR = os.environ.get(
    "NOUGEN_TRACKER_DIR", str(_HOME / "Outpost" / "NouGenTracker_remote")
)
DAILIES_DIR = os.path.join(TRACKER_DIR, "dailies")

def get_machine_breakdown(scope='local', period='week'):
    """
    scope: 'local' (whoart alone) or 'fleet' (whoart + blade1tb + phoebus)
    period: '24h', 'week', 'month', 'quarter', 'year', 'all'
    """
    days_map = {
        '24h': 1,
        'week': 7,
        'month': 30,
        'quarter': 90,
        'year': 365,
        'all': 99999
    }
    max_days = days_map.get(period, 7)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_days)

    from .dashboard_live import read_json
    registry = read_json(Path.home() / '.nougen/nodes.json', {})
    import socket
    hostname = socket.gethostname().lower()
    local_aliases = {hostname}
    for node in registry.values():
        if node.get('ip') in ('127.0.0.1', 'localhost'):
            local_aliases.update(str(node.get(key, '')).lower() for key in ('transport_node', 'machine', 'name'))
            local_aliases.update(str(alias).lower() for alias in node.get('aliases', []))
    candidates = [p.name for p in Path(DAILIES_DIR).iterdir() if p.is_dir()] if Path(DAILIES_DIR).is_dir() else []
    machines_to_load = candidates if scope == 'fleet' else [name for name in candidates if name.lower() in local_aliases]

    tot_in = 0
    tot_out = 0
    tot_cache = 0
    tot_invocations = 0
    models_accum = {}
    records_read = 0
    read_errors = 0

    if os.path.exists(DAILIES_DIR):
        for machine in machines_to_load:
            m_dir = os.path.join(DAILIES_DIR, machine)
            if not os.path.exists(m_dir):
                continue
            for f in glob.glob(os.path.join(m_dir, '*.json')):
                try:
                    fname = os.path.basename(f).replace('.json', '')
                    # parse date
                    if max_days < 99999:
                        f_date = datetime.strptime(fname, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                        if f_date < cutoff:
                            continue

                    with open(f, 'r', encoding='utf-8') as fp:
                        d = json.load(fp)
                        totals = d.get('totals', {})
                        records_read += 1
                        in_tok = totals.get('input_tokens', 0)
                        out_tok = totals.get('output_tokens', 0)
                        c_tok = totals.get('cache_read', 0) + totals.get('cache_creation', 0)
                        inv = d.get('invocations', 0)

                        tot_in += in_tok
                        tot_out += out_tok
                        tot_cache += c_tok
                        tot_invocations += inv

                        # models
                        for m_name, m_stats in d.get('models', {}).items():
                            if m_name == '<synthetic>':
                                continue
                            model_key = (machine, m_name)
                            if model_key not in models_accum:
                                models_accum[model_key] = {"in": 0, "out": 0, "cache": 0, "inv": 0, "machine": machine}
                            models_accum[model_key]["in"] += m_stats.get('input_tokens', 0)
                            models_accum[model_key]["out"] += m_stats.get('output_tokens', 0)
                            models_accum[model_key]["cache"] += m_stats.get('cache_read', 0) + m_stats.get('cache_creation', 0)

                except Exception:
                    read_errors += 1

    total_tokens = tot_in + tot_out + tot_cache
    by_model = []
    for (_, name), row in models_accum.items():
        by_model.append({'provider': row.get('machine'), 'model': name,
                         'invocations': None, 'total_tokens': row['in'] + row['out'] + row['cache'],
                         'estimated_cost': None})
    return {'period': period, 'scope': scope, 'invocations': tot_invocations,
            'total_tokens': total_tokens, 'prompt_tokens': tot_in,
            'cached_tokens': tot_cache,
            'cache_hit_rate': round(tot_cache / (tot_in + tot_cache) * 100, 1) if tot_in + tot_cache else None,
            'estimated_cost': None, 'free_share': None, 'by_model': by_model,
            'ledger_present': records_read > 0, 'records_read': records_read, 'read_errors': read_errors,
            'source': DAILIES_DIR, 'observed_at': now.isoformat()}


def search_shards(query="", limit=40):
    query = (query or "").strip().lower()
    results = []

    for db_idx in range(1, core.MAX_DB_COUNT + 1):
        db_path = os.path.join(_shards_dir(), f"nougen_shards_{db_idx}.db")
        if not os.path.exists(db_path):
            continue
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = conn.cursor()

            if not query:
                cur.execute(
                    "SELECT id, title, content, utility_score, timestamp, tags FROM shards ORDER BY id DESC LIMIT 5"
                )
                rows = cur.fetchall()
                for r in rows:
                    results.append({
                        "id": r[0],
                        "title": r[1] or f"Memory #{r[0]}",
                        "content": r[2] or "",
                        "utility_score": float(r[3] or 1.0),
                        "timestamp": r[4] or "",
                        "tags": r[5] or "",
                        "_db_index": db_idx,
                        "final_score": None
                    })
            else:
                words = [w for w in query.split() if w]
                sql = "SELECT id, title, content, utility_score, timestamp, tags FROM shards WHERE "
                conditions = []
                params = []
                for w in words:
                    conditions.append("(LOWER(title) LIKE ? OR LOWER(content) LIKE ? OR LOWER(tags) LIKE ?)")
                    like_w = f"%{w}%"
                    params.extend([like_w, like_w, like_w])

                sql += " AND ".join(conditions) + " ORDER BY id DESC LIMIT 20"
                cur.execute(sql, params)
                rows = cur.fetchall()

                for r in rows:
                    title_l = (r[1] or "").lower()
                    content_l = (r[2] or "").lower()
                    tags_l = (r[5] or "").lower()

                    score = 0.5
                    if query in title_l:
                        score += 0.4
                    elif any(w in title_l for w in words):
                        score += 0.25
                    if query in content_l:
                        score += 0.15
                    if any(w in tags_l for w in words):
                        score += 0.1

                    score = min(1.0, score * float(r[3] or 1.0))

                    results.append({
                        "id": r[0],
                        "title": r[1] or f"Memory #{r[0]}",
                        "content": r[2] or "",
                        "utility_score": float(r[3] or 1.0),
                        "timestamp": r[4] or "",
                        "tags": r[5] or "",
                        "_db_index": db_idx,
                        "final_score": round(score, 2)
                    })
            conn.close()
        except Exception:
            pass

    if query:
        results.sort(key=lambda x: (x.get("final_score", 0), x.get("id", 0)), reverse=True)
    else:
        results.sort(key=lambda x: x.get("id", 0), reverse=True)

    return results[:limit]

def get_engine_status():
    databases = []
    total_shards = 0

    for db_idx in range(1, core.MAX_DB_COUNT + 1):
        db_path = os.path.join(_shards_dir(), f"nougen_shards_{db_idx}.db")
        size_mb = 0.0
        shards_count = 0
        if os.path.exists(db_path):
            try:
                size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM shards")
                shards_count = cur.fetchone()[0]
                conn.close()
            except Exception:
                shards_count = None

        total_shards += shards_count or 0
        databases.append({
            "index": db_idx,
            "shards": shards_count,
            "size_mb": size_mb,
            "is_active": db_idx == core.get_active_db_index()
        })

    return {
        "databases": databases,
        "total_shards": total_shards,
        "max_db_count": core.MAX_DB_COUNT,
        "partition_cap_mb": core.MAX_DB_SIZE / 1024**2,
        "active_db": core.get_active_db_index()
    }

def get_fleet_telemetry_status():
    """Return unified 3-layer fleet telemetry and declared intent."""
    state_file = Path.home() / ".nougen" / "state" / "fleet_telemetry.json"
    intent_file = Path.home() / ".nougen" / "state" / "fleet_intent.json"

    telemetry = {}
    intent = {}

    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                telemetry = json.load(f)
        except Exception:
            pass

    if intent_file.exists():
        try:
            with open(intent_file, "r", encoding="utf-8") as f:
                intent = json.load(f)
        except Exception:
            pass

    return {
        "telemetry": telemetry,
        "declared_intent": intent,
        "engine": get_engine_status()
    }

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "usage"
    if cmd == "search":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        print(json.dumps(search_shards(q)))
    elif cmd == "status":
        print(json.dumps(get_engine_status()))
    elif cmd == "live":
        print(json.dumps(get_fleet_telemetry_status()))
    elif cmd == "usage":
        p = sys.argv[2] if len(sys.argv) > 2 else "week"
        s = sys.argv[3] if len(sys.argv) > 3 else "local"
        print(json.dumps(get_machine_breakdown(s, p)))

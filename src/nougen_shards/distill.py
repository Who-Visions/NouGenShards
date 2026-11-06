"""Distillation sidecar: L1 atoms, entity graph, L2 scenes, L3 persona.

The cross-donor #1 move from Sun 9/13/2026. Five independent teams converge on it:
TencentDB-Agent-Memory L0-L3 (MIT) and openhuman's memory tree (fleet 6/6 on
both), memmesh consolidation, cortex-app sleep pass, EverOS reflection.

The shard DBs stay the source of truth (GM rule, 9/13: "db is source for us").
Everything here is DERIVED and lives in ONE sidecar SQLite file beside the
vault. It can be rebuilt from the shards at any time, and the 9 shard DBs are
never schema-changed by it.

    L0 shard -> L1 atoms (typed statements) + entities + relations (graph)
    L2 scene  : an entity seen in >= SCENE_MIN distilled shards, summarised
    L3 persona: one profile per owner scope, summarised from its top scenes

The package never calls a model itself. Callers inject `llm(prompt, schema)`,
and tools/distill_run.py injects coach.local, the loopback e2b lane, so shard
text never leaves the machine.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional


ATOM_TYPES = ("fact", "preference", "constraint", "event", "decision")
ENTITY_KINDS = ("person", "project", "tool", "machine", "org", "place", "concept")
MAX_BODY_CHARS = 5000        # keeps prompt + 1.4k-token answer inside e2b's default context
SCENE_MIN = 3                # Tencent: scenes are hubs, not singletons
MAX_SCENES_PER_PERSONA = 15  # Tencent persona.maxScenes default
GENERIC = {"it", "this", "that", "user", "system", "the user", "memory", "shard", "data", "model"}
SHARD_COLS = "id, timestamp, title, content, utility_score, embedding, tags, domain_key, density_score, event_type"

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "atoms": {"type": "array", "items": {"type": "object", "properties": {
            "type": {"type": "string", "enum": list(ATOM_TYPES)}, "text": {"type": "string"}},
            "required": ["type", "text"]}},
        "entities": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "kind": {"type": "string", "enum": list(ENTITY_KINDS)}},
            "required": ["name", "kind"]}},
        "relations": {"type": "array", "items": {"type": "object", "properties": {
            "src": {"type": "string"}, "rel": {"type": "string"}, "dst": {"type": "string"}},
            "required": ["src", "rel", "dst"]}},
    },
    "required": ["atoms", "entities", "relations"],
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS distilled (shard_key TEXT PRIMARY KEY, db INTEGER, shard_id INTEGER,
    content_hash TEXT, model TEXT, n_atoms INTEGER, status TEXT, created_utc TEXT);
CREATE TABLE IF NOT EXISTS atoms (id INTEGER PRIMARY KEY, shard_key TEXT, type TEXT, text TEXT);
CREATE INDEX IF NOT EXISTS atoms_shard ON atoms(shard_key);
CREATE VIRTUAL TABLE IF NOT EXISTS atoms_fts USING fts5(text, content='atoms', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS atoms_ai AFTER INSERT ON atoms BEGIN
    INSERT INTO atoms_fts(rowid, text) VALUES (new.id, new.text); END;
CREATE TRIGGER IF NOT EXISTS atoms_ad AFTER DELETE ON atoms BEGIN
    INSERT INTO atoms_fts(atoms_fts, rowid, text) VALUES ('delete', old.id, old.text); END;
CREATE TABLE IF NOT EXISTS entities (id INTEGER PRIMARY KEY, norm TEXT UNIQUE, name TEXT, kind TEXT);
CREATE TABLE IF NOT EXISTS mentions (entity_id INTEGER, shard_key TEXT, PRIMARY KEY (entity_id, shard_key));
CREATE INDEX IF NOT EXISTS mentions_shard ON mentions(shard_key);
CREATE TABLE IF NOT EXISTS edges (src INTEGER, rel TEXT, dst INTEGER, shard_key TEXT,
    PRIMARY KEY (src, rel, dst, shard_key));
CREATE INDEX IF NOT EXISTS edges_dst ON edges(dst);
CREATE TABLE IF NOT EXISTS scenes (entity_id INTEGER PRIMARY KEY, summary TEXT, n_shards INTEGER, updated_utc TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS scenes_fts USING fts5(summary, content='scenes', content_rowid='entity_id');
CREATE TRIGGER IF NOT EXISTS scenes_ai AFTER INSERT ON scenes BEGIN
    INSERT INTO scenes_fts(rowid, summary) VALUES (new.entity_id, new.summary); END;
CREATE TRIGGER IF NOT EXISTS scenes_ad AFTER DELETE ON scenes BEGIN
    INSERT INTO scenes_fts(scenes_fts, rowid, summary) VALUES ('delete', old.entity_id, old.summary); END;
CREATE TABLE IF NOT EXISTS persona (scope TEXT PRIMARY KEY, summary TEXT, n_scenes INTEGER, updated_utc TEXT);
CREATE TABLE IF NOT EXISTS sent (session TEXT, shard_key TEXT, sent_utc TEXT, PRIMARY KEY (session, shard_key));
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sidecar_path() -> Path:
    from . import core  # pylint: disable=import-outside-toplevel
    return core.get_db_path(1).parent / "nougen_distill.db"


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or sidecar_path()), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA_SQL)
    return conn


def available() -> bool:
    """Lanes are live only when a sidecar with atoms exists (cheap stat, no create)."""
    try:
        p = sidecar_path()
        return p.exists() and p.stat().st_size > 0
    except OSError:
        return False


def shard_key(db: int, sid: int) -> str:
    return f"{sid}@{db}"


def _split(key: str) -> tuple[int, int]:
    sid, db = key.split("@")
    return int(db), int(sid)


def _entity_like(norm: str) -> bool:
    """Reject file names and long slugs the model sometimes lists as entities."""
    return len(norm) <= 60 and not re.search(r"\.(md|json|py|txt|db|pdf)$", norm) and norm.count("_") < 3


def norm_entity(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).lower().strip(" .,:;\"'`()[]")).strip()


# ------------------------------------------------------------------ scope

def scope_from_tags(tags, domain_key: Optional[str] = None) -> dict:
    """Deterministic scope from existing tags, no model needed: via:<agent>/<user>,
    machine:<host>, and project = domain_key. Works on every shard, distilled or not."""
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except ValueError:
            tags = [t.strip() for t in tags.split(",")]
    scope = {"agent": None, "user": None, "machine": None, "project": domain_key}
    for t in tags or []:
        t = str(t)
        if t.startswith("via:"):
            agent, _, user = t[4:].partition("/")
            scope["agent"], scope["user"] = agent or None, user or None
        elif t.startswith("machine:"):
            scope["machine"] = t[8:] or None
    return scope


def scope_matches(item: dict, want: dict) -> bool:
    have = scope_from_tags(item.get("tags"), item.get("domain_key"))
    return all(have.get(k) == v for k, v in want.items() if v)


# ------------------------------------------------------------------ L1 write path

def extract_prompt(title: str, body: str) -> str:
    return (
        "You distil one memory record into a compact, searchable index.\n"
        f"Title: {title}\nBody:\n{body[:MAX_BODY_CHARS]}\n\n"
        "atoms: 3-8 standalone statements (fact, preference, constraint, event or decision) that together "
        "cover the body. Each must make sense alone: name the people, projects, tools, machines and dates "
        "instead of pronouns, and keep the body's own key terms verbatim.\n"
        "entities: the named people, projects, tools, machines, orgs, places and key concepts.\n"
        "relations: [src, rel, dst] between those entities with short verbs "
        "(uses, runs_on, owns, part_of, blocks, fixes, replaces, depends_on).")


def _load_rows(keys: list[str], with_research: bool = True) -> dict:
    """(db, id) -> shard dict in the same shape the FTS lane yields (no file_hash,
    so RRF keys it as id_<db>_<id> and fuses it with the other lanes' copies)."""
    from . import core  # pylint: disable=import-outside-toplevel
    by_db: dict[int, list[int]] = {}
    for k in keys:
        db, sid = _split(k)
        by_db.setdefault(db, []).append(sid)
    bulk = set() if with_research else {t.upper() for t in (core.bulk_ingest_event_types() or ())}
    out = {}
    for db, ids in by_db.items():
        conn = None
        try:
            conn = core.get_connection(db)
            marks = ",".join("?" * len(ids))
            for row in conn.execute(f"SELECT {SHARD_COLS} FROM shards WHERE id IN ({marks})", ids):
                item = core.hydrate(dict(row))
                if bulk and str(item.get("event_type") or "").upper() in bulk:
                    continue
                item["_db_index"] = db
                out[shard_key(db, item["id"])] = item
        except (sqlite3.DatabaseError, OSError):
            continue
        finally:  # get_connection opens a fresh handle per call
            if conn is not None:
                conn.close()
    return out


def distill_shard(conn: sqlite3.Connection, key: str, llm: Callable, model: str = "e2b") -> str:
    """Distil one shard into atoms/entities/edges. Returns 'done', 'skip' (unchanged) or 'empty'.
    Idempotent: re-running replaces this shard's derived rows."""
    rows = _load_rows([key])
    item = rows.get(key)
    if not item or not item.get("content"):
        return "empty"
    body = str(item["content"])
    h = hashlib.sha1(f"{item.get('title')}\n{body}".encode("utf-8", "replace")).hexdigest()
    prev = conn.execute("SELECT content_hash, status FROM distilled WHERE shard_key=?", (key,)).fetchone()
    if prev and prev[0] == h and prev[1] == "done":
        return "skip"
    raw = llm(extract_prompt(str(item.get("title") or ""), body), EXTRACT_SCHEMA)
    data = json.loads(raw) if isinstance(raw, str) else raw
    atoms = [a for a in data.get("atoms", []) if a.get("type") in ATOM_TYPES and str(a.get("text", "")).strip()][:8]
    db, sid = _split(key)
    with conn:
        conn.execute("DELETE FROM atoms WHERE shard_key=?", (key,))
        conn.execute("DELETE FROM mentions WHERE shard_key=?", (key,))
        conn.execute("DELETE FROM edges WHERE shard_key=?", (key,))
        conn.executemany("INSERT INTO atoms(shard_key, type, text) VALUES (?,?,?)",
                         [(key, a["type"], str(a["text"]).strip()[:500]) for a in atoms])
        ids = {}

        def entity(name, kind):
            n = norm_entity(name)
            if len(n) < 3 or n in GENERIC or not _entity_like(n):
                return None
            if n not in ids:
                conn.execute("INSERT OR IGNORE INTO entities(norm, name, kind) VALUES (?,?,?)",
                             (n, str(name).strip()[:120], kind if kind in ENTITY_KINDS else "concept"))
                ids[n] = conn.execute("SELECT id FROM entities WHERE norm=?", (n,)).fetchone()[0]
                conn.execute("INSERT OR IGNORE INTO mentions VALUES (?,?)", (ids[n], key))
            return ids[n]

        for e in data.get("entities", [])[:20]:
            entity(e.get("name", ""), e.get("kind"))
        # A small model names relation endpoints loosely ("LLMs" vs "Large language
        # models"); endpoints become entities of their own rather than dropping the
        # edge. The smoke test on 4944@6 lost every edge before this.
        for r in data.get("relations", [])[:20]:
            rel = re.sub(r"[^a-z_]", "", str(r.get("rel", "")).lower().replace(" ", "_"))[:32]
            s, d = entity(r.get("src", ""), "concept"), entity(r.get("dst", ""), "concept")
            if s and d and s != d and rel:
                conn.execute("INSERT OR IGNORE INTO edges VALUES (?,?,?,?)", (s, rel, d, key))
        conn.execute("INSERT OR REPLACE INTO distilled VALUES (?,?,?,?,?,?,?,?)",
                     (key, db, sid, h, model, len(atoms), "done", _now()))
    return "done"


def extract_structured(title: str, body: str) -> Optional[dict]:
    """Deterministic, zero-LLM extractor for structured shards (Twitch Helix API endpoints
    and NouGenStream session summaries). Returns an EXTRACT_SCHEMA-shaped dict or None."""
    atoms: list[dict] = []
    entities: list[dict] = []
    relations: list[dict] = []

    ep_m = re.search(r"(?:^|\n)ENDPOINT:\s*(GET|POST|PATCH|PUT|DELETE)\s+(https://api\.twitch\.tv/helix/([\w/\-]+))", body)
    if ep_m or title.startswith("Twitch Helix API:"):
        method = ep_m.group(1) if ep_m else (re.search(r"\((GET|POST|PATCH|PUT|DELETE)\s+", title) or [None, "GET"])[1]
        url = ep_m.group(2) if ep_m else ""
        path = "/" + ep_m.group(3) if ep_m else (re.search(r"(/[\w/\-]+)\)", title) or [None, ""])[1]
        name = re.sub(r"^Twitch Helix API:\s*|\s*\([^)]*\)\s*$", "", title).strip() or path
        sc_m = re.search(r"(?:^|\n)SCOPES:\s*([^\n]+)", body)
        scopes = [s.strip() for s in (sc_m.group(1).split(",") if sc_m else []) if s.strip() and s.strip() != "none listed"]
        entities.extend([
            {"name": "Twitch Helix API", "kind": "tool"},
            {"name": "NouGenStream", "kind": "project"},
            {"name": name, "kind": "concept"},
        ])
        relations.append({"src": "NouGenStream", "rel": "uses", "dst": "Twitch Helix API"})
        relations.append({"src": name, "rel": "part_of", "dst": "Twitch Helix API"})
        atoms.append({"type": "fact", "text": f"Twitch Helix API endpoint {name} uses {method} {path or url} ({url})."})
        if scopes:
            atoms.append({"type": "constraint", "text": f"Twitch Helix API {name} ({method} {path}) requires OAuth scopes: {', '.join(scopes)}."})
            for sc in scopes[:6]:
                entities.append({"name": sc, "kind": "concept"})
                relations.append({"src": name, "rel": "depends_on", "dst": sc})
        else:
            atoms.append({"type": "fact", "text": f"Twitch Helix API {name} ({method} {path}) requires an OAuth token with no extra scope."})
        for line in body.splitlines():
            s = line.strip()
            if s.startswith("NOTE :"):
                atoms.append({"type": "constraint", "text": f"Twitch Helix API {name}: {s[6:].strip()}"})
            elif len(s) > 25 and not s.startswith(("SOURCE:", "ENDPOINT:", "SCOPES:", "Twitch Helix")) and s != name and len(atoms) < 6:
                if any(s.startswith(w) for w in ("Starts ", "Gets ", "Creates ", "Updates ", "Deletes ", "Sends ", "Modifies ", "Bans ", "Unbans ", "Resolves ", "Snoozes ", "Searches ")):
                    atoms.append({"type": "fact", "text": f"Twitch Helix API {name} ({method} {path}): {s}"})
        return {"atoms": atoms[:8], "entities": entities[:20], "relations": relations[:20]}

    if title.startswith("NouGenStream session ") or "| Frames encoded (live) |" in body:
        entities.append({"name": "NouGenStream", "kind": "project"})
        kv = {m.group(1).strip(): m.group(2).strip() for m in re.finditer(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$", body, re.M)
              if m.group(1).strip() and not m.group(1).strip().startswith("-")}
        dur = kv.get("Duration", "")
        fps = kv.get("Average capture fps", "")
        enc = kv.get("Encoder", "")
        viewers = kv.get("Peak viewers", "0")
        atoms.append({"type": "event", "text": f"{title} ran for {dur} at {fps} average capture fps with peak viewers {viewers} using encoder {enc}."})
        if enc and enc != "none":
            entities.append({"name": enc, "kind": "tool"})
            relations.append({"src": "NouGenStream", "rel": "uses", "dst": enc})
        for line in body.splitlines():
            s = line.strip()
            if s.startswith(("Viewer backlog drops:", "Policy decisions:", "Privacy mask:", "Model:")):
                atype = "constraint" if s.startswith(("Policy", "Privacy")) else "fact"
                atoms.append({"type": atype, "text": f"NouGenStream session telemetry: {s}"})
                if s.startswith("Model:"):
                    mod = s.split("Model:", 1)[1].split(".", 1)[0].strip()
                    if mod and mod != "none":
                        entities.append({"name": mod, "kind": "tool"})
                        relations.append({"src": "NouGenStream", "rel": "uses", "dst": mod})
        return {"atoms": atoms[:8], "entities": entities[:20], "relations": relations[:20]}

    if ("Visual Asset" in title or "Asset Kit" in title or "Visual Pack" in title
            or "assets/premium/" in body or "NouGenStream-visual-pack" in body):
        entities.append({"name": "NouGenStream", "kind": "project"})
        kit_name = "Purple Obsidian Asset Kit" if "Purple Obsidian" in body or "assets/premium/" in body else "NouGenStream Visual Pack"
        entities.append({"name": kit_name, "kind": "File"})
        relations.append({"src": kit_name, "rel": "part_of", "dst": "NouGenStream"})
        atoms.append({"type": "fact", "text": f"{title}: {kit_name} registered for NouGenStream broadcast overlays, icons, splash, Now Playing cards, and stinger transitions."})
        pal_m = re.findall(r"(#[0-9a-fA-F]{6})", body)
        if pal_m:
            uniq_hex = list(dict.fromkeys(h.lower() for h in pal_m))[:8]
            atoms.append({"type": "constraint", "text": f"{kit_name} color palette anchors: {', '.join(uniq_hex)}."})
        for m in re.finditer(r"`?((?:assets/premium/|[\w\-]+/|)[\w\-]+\.(?:png|svg|ico|webm))`?\s*(?:\(|—|-|:)\s*([^\n]{5,120})", body):
            fn, desc = m.group(1).strip(), m.group(2).strip(" ):")
            entities.append({"name": fn, "kind": "File"})
            relations.append({"src": fn, "rel": "part_of", "dst": kit_name})
            if len(atoms) < 8:
                atoms.append({"type": "fact", "text": f"{kit_name} asset {fn}: {desc}"})
        return {"atoms": atoms[:8], "entities": entities[:20], "relations": relations[:20]}

    return None


def distill_structured_shard(conn: sqlite3.Connection, key: str) -> str:
    """Zero-LLM fast path for structured shards (stream_session, Twitch Helix API).
    Returns 'done', 'skip', 'unsupported', or 'empty'."""
    rows = _load_rows([key])
    item = rows.get(key)
    if not item or not item.get("content"):
        return "empty"
    extracted = extract_structured(str(item.get("title") or ""), str(item["content"]))
    if not extracted or not extracted.get("atoms"):
        return "unsupported"
    return distill_shard(conn, key, lambda _p, _s: extracted, model="deterministic-v1")



# ------------------------------------------------------------------ L2 / L3

def build_scenes(conn: sqlite3.Connection, llm: Callable, min_shards: int = SCENE_MIN, limit: int = 200) -> int:
    """Summarise every entity hub seen in >= min_shards distilled shards. Skips hubs
    whose shard count has not changed since their last summary. Returns scenes written."""
    hubs = conn.execute("""
        SELECT e.id, e.name, e.kind, COUNT(*) n FROM mentions m JOIN entities e ON e.id = m.entity_id
        GROUP BY e.id HAVING n >= ? ORDER BY n DESC, e.id LIMIT ?""", (min_shards, limit)).fetchall()
    written = 0
    for eid, name, kind, n in hubs:
        prev = conn.execute("SELECT n_shards FROM scenes WHERE entity_id=?", (eid,)).fetchone()
        if prev and prev[0] == n:
            continue
        atoms = [r[0] for r in conn.execute("""
            SELECT a.text FROM atoms a JOIN mentions m ON m.shard_key = a.shard_key
            WHERE m.entity_id = ? ORDER BY a.id DESC LIMIT 24""", (eid,))]
        if not atoms:
            continue
        summary = llm(f"Summarise what this memory vault knows about {name} ({kind}) in 3-6 sentences. "
                      "Keep names, dates and numbers exactly. Statements:\n- " + "\n- ".join(atoms), None).strip()
        if not summary:
            continue
        with conn:
            conn.execute("DELETE FROM scenes WHERE entity_id=?", (eid,))
            conn.execute("INSERT INTO scenes VALUES (?,?,?,?)", (eid, summary[:2400], n, _now()))
        written += 1
    return written


def owner_scope(conn: sqlite3.Connection) -> Optional[str]:
    """The most frequent via:<agent>/<user> user across distilled shards: data-derived,
    no hardcoded owner (the cape rule)."""
    keys = [r[0] for r in conn.execute("SELECT shard_key FROM distilled WHERE status='done'")]
    counts: dict[str, int] = {}
    for item in _load_rows(keys).values():
        u = scope_from_tags(item.get("tags")).get("user")
        if u:
            counts[u] = counts.get(u, 0) + 1
    return max(counts, key=counts.get) if counts else None


def build_persona(conn: sqlite3.Connection, llm: Callable, scope: Optional[str] = None) -> Optional[str]:
    scope = scope or owner_scope(conn) or "vault"
    scenes = conn.execute("""SELECT e.name, s.summary FROM scenes s JOIN entities e ON e.id = s.entity_id
                             ORDER BY s.n_shards DESC LIMIT ?""", (MAX_SCENES_PER_PERSONA,)).fetchall()
    if not scenes:
        return None
    text = llm(f"Write a compact profile of '{scope}' as at most 12 bullet lines: who they are, what they "
               "build, how they work, standing preferences and constraints. Use only these topic summaries; "
               "keep names exact.\n\n" + "\n\n".join(f"## {n}\n{s}" for n, s in scenes), None).strip()
    with conn:
        conn.execute("INSERT OR REPLACE INTO persona VALUES (?,?,?,?)", (scope, text[:4000], len(scenes), _now()))
    return text


# ------------------------------------------------------------------ read path

def _fts_or(query: str) -> Optional[str]:
    toks = [t for t in re.findall(r"\w+", query.lower()) if len(t) >= 2][:16]
    return " OR ".join('"' + t.replace('"', "") + '"' for t in toks) or None


def atoms_lane(query: str, limit: int = 20, include_research: bool = False,
               domain_key: Optional[str] = None, conn: Optional[sqlite3.Connection] = None) -> list[dict]:
    """Shards ranked by how strongly their atoms match the query (sum of atom bm25)."""
    expr = _fts_or(query)
    if not expr or not available():
        return []
    conn = conn or connect()
    scores: dict[str, float] = {}
    for key, bm in conn.execute("""SELECT a.shard_key, bm25(atoms_fts) FROM atoms_fts
                                   JOIN atoms a ON a.id = atoms_fts.rowid WHERE atoms_fts MATCH ?
                                   ORDER BY bm25(atoms_fts) LIMIT 400""", (expr,)):
        scores[key] = scores.get(key, 0.0) - bm
    return _ranked_items(scores, limit, include_research, domain_key)


def graph_lane(query: str, limit: int = 20, include_research: bool = False,
               domain_key: Optional[str] = None, conn: Optional[sqlite3.Connection] = None) -> list[dict]:
    """Personalised-PageRank-lite: entities named in the query seed weight 1.0 onto
    the shards that mention them; one hop along relation edges passes 0.5 on to the
    neighbours' shards. Bounded to 1 hop so it stays fast and explainable."""
    if not available():
        return []
    conn = conn or connect()
    q = " " + re.sub(r"\s+", " ", query.lower()) + " "
    seeds = [eid for eid, norm in conn.execute("SELECT id, norm FROM entities") if f" {norm} " in q]
    if not seeds:
        return []
    weight: dict[int, float] = {e: 1.0 for e in seeds}
    marks = ",".join("?" * len(seeds))
    for s, d in conn.execute(f"SELECT src, dst FROM edges WHERE src IN ({marks}) OR dst IN ({marks})", seeds * 2):
        for nb in (s, d):
            if nb not in seeds:
                weight[nb] = max(weight.get(nb, 0.0), 0.5)
    scores: dict[str, float] = {}
    marks = ",".join("?" * len(weight))
    for eid, key in conn.execute(f"SELECT entity_id, shard_key FROM mentions WHERE entity_id IN ({marks})", list(weight)):
        scores[key] = scores.get(key, 0.0) + weight[eid]
    return _ranked_items(scores, limit, include_research, domain_key)


def _ranked_items(scores: dict, limit: int, include_research: bool, domain_key: Optional[str]) -> list[dict]:
    ranked = sorted(scores, key=lambda k: (-scores[k], k))[: limit * 3]
    rows = _load_rows(ranked, with_research=include_research)
    out = []
    for k in ranked:
        item = rows.get(k)
        if item is None or (domain_key not in (None, "*") and item.get("domain_key") != domain_key):
            continue
        item["final_score"] = scores[k]
        out.append(item)
        if len(out) >= limit:
            break
    return out


def held_keys(session: str, conn: Optional[sqlite3.Connection] = None) -> set:
    if not session:
        return set()
    conn = conn or connect()
    return {r[0] for r in conn.execute("SELECT shard_key FROM sent WHERE session=?", (session,))}


def mark_sent(session: str, keys, conn: Optional[sqlite3.Connection] = None) -> None:
    if not session or not keys:
        return
    conn = conn or connect()
    with conn:
        conn.executemany("INSERT OR IGNORE INTO sent VALUES (?,?,?)", [(session, k, _now()) for k in keys])


def layered_context(query: str, retrieve: Callable, token_budget: int = 1200,
                    conn: Optional[sqlite3.Connection] = None, **retrieve_kw) -> str:
    """Tencent's layered read: L3 persona and L2 scenes bootstrap the context, L1
    atoms give the specifics with handles, L0 shards fill whatever budget is left."""
    conn = conn or connect()
    used, parts = 0, []

    def add(block: str) -> bool:
        nonlocal used
        cost = (len(block) + 3) // 4
        if used + cost > token_budget:
            return False
        parts.append(block)
        used += cost
        return True

    persona = conn.execute("SELECT scope, summary FROM persona ORDER BY updated_utc DESC LIMIT 1").fetchone()
    if persona:
        add(f"=== L3 PERSONA ({persona[0]}) ===\n{persona[1]}")
    expr = _fts_or(query)
    if expr:
        for name, summary in conn.execute("""SELECT e.name, s.summary FROM scenes_fts JOIN scenes s
                ON s.entity_id = scenes_fts.rowid JOIN entities e ON e.id = s.entity_id
                WHERE scenes_fts MATCH ? ORDER BY bm25(scenes_fts) LIMIT 3""", (expr,)):
            if not add(f"=== L2 SCENE: {name} ===\n{summary}"):
                break
        atoms = conn.execute("""SELECT a.type, a.text, a.shard_key FROM atoms_fts JOIN atoms a
                ON a.id = atoms_fts.rowid WHERE atoms_fts MATCH ? ORDER BY bm25(atoms_fts) LIMIT 12""",
                             (expr,)).fetchall()
        if atoms:
            add("=== L1 ATOMS ===\n" + "\n".join(f"- [{t}] {x} (shard {k})" for t, x, k in atoms))
    from .core import compile_recall_packet  # pylint: disable=import-outside-toplevel
    rest = token_budget - used
    if rest > 80:
        shards = retrieve(query, **retrieve_kw)
        if shards:
            parts.append(compile_recall_packet(shards, token_budget=rest))
    return "\n\n".join(parts) if parts else "<!-- NO RELEVANT MEMORY RECALLED -->"


def stats(conn: Optional[sqlite3.Connection] = None) -> dict:
    conn = conn or connect()
    one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    return {"distilled": one("SELECT COUNT(*) FROM distilled WHERE status='done'"),
            "atoms": one("SELECT COUNT(*) FROM atoms"), "entities": one("SELECT COUNT(*) FROM entities"),
            "edges": one("SELECT COUNT(*) FROM edges"), "scenes": one("SELECT COUNT(*) FROM scenes"),
            "personas": one("SELECT COUNT(*) FROM persona"), "path": str(sidecar_path())}

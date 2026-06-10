"""NouGenShards core database and retrieval module."""
# pylint: disable=duplicate-code
from pathlib import Path
import os
import sqlite3
import hashlib
import json
import glob
import re
from datetime import datetime

# Database path resolution: check local root first, then default to global .nougen folder
LOCAL_DB = Path("shards.db")
GLOBAL_DIR = Path.home() / ".nougen" / "shards"
GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
GLOBAL_DB = GLOBAL_DIR / "nougen_shards.db"

DB_PATH = str(LOCAL_DB) if LOCAL_DB.exists() else str(GLOBAL_DB)

def get_connection():
    """Establishes an SQLite connection with WAL enabled."""
    # Ensure init_db uses the intended path
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database schema and FTS5 triggers."""
    conn = get_connection()
    cursor = conn.cursor()

    # Create main shards table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT,
            utility_score REAL DEFAULT 1.0,
            access_count INTEGER DEFAULT 0,
            file_hash TEXT UNIQUE NOT NULL
        );
    """)

    # Create FTS5 virtual table
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS shards_fts USING fts5(
            title,
            content,
            content='shards',
            content_rowid='id'
        );
    """)

    # Triggers to keep FTS5 virtual table synchronized with the main shards table
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS shards_ai AFTER INSERT ON shards BEGIN
            INSERT INTO shards_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
        END;
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS shards_ad AFTER DELETE ON shards BEGIN
            INSERT INTO shards_fts(shards_fts, rowid, title, content)
            VALUES('delete', old.id, old.title, old.content);
        END;
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS shards_au AFTER UPDATE ON shards BEGIN
            INSERT INTO shards_fts(shards_fts, rowid, title, content)
            VALUES('delete', old.id, old.title, old.content);
            INSERT INTO shards_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
        END;
    """)

    conn.commit()
    conn.close()

    # Auto-seed the database with predefined default workspace experience shards
    seed_default_shards()


def get_hash(content: str) -> str:
    """Returns MD5 hash for deduplication."""
    return hashlib.md5(content.encode("utf-8", errors="ignore")).hexdigest()

def capture(event_type: str, title: str, content: str, tags: list = None) -> bool:
    """
    Saves a persistent unit of machine experience (Shard).
    Returns True if successfully written, False if it already exists or fails.
    """
    fhash = get_hash(content)
    tags_str = json.dumps(tags or [])
    timestamp = datetime.utcnow().isoformat() + "Z"

    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO shards (timestamp, event_type, title, content, tags, file_hash)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (timestamp, event_type, title, content, tags_str, fhash))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Shard already exists (duplicate hash)
        return False
    finally:
        conn.close()

def retrieve(query: str, limit: int = 3) -> list:
    """
    Retrieves matching shards using FTS5 BM25 ranked query with utility weighting.
    Falls back to LIKE syntax if query contains invalid syntax or is empty.
    Also increments the access count for retrieved shards.
    """
    init_db()
    conn = get_connection()
    shards = []

    # Attempt FTS5 search
    try:
        # Sanitize query for FTS5 (replace special chars or keep simple keywords)
        clean_query = " OR ".join([f'"{word}"' for word in query.split() if word.isalnum()])
        if not clean_query:
            clean_query = query

        # Incorporate utility_score into ranking logic (Utility-Weighted BM25)
        cursor = conn.execute("""
            SELECT s.id, s.timestamp, s.event_type, s.title, s.content, s.tags,
                   s.utility_score, s.access_count
            FROM shards s
            JOIN shards_fts f ON s.id = f.rowid
            WHERE shards_fts MATCH ?
            ORDER BY (bm25(shards_fts) * (1.0 / (s.utility_score + 0.1))) ASC
            LIMIT ?
        """, (clean_query, limit))
        shards = [dict(row) for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        # Fallback to standard LIKE matching with utility weighting
        like_query = f"%{query}%"
        cursor = conn.execute("""
            SELECT id, timestamp, event_type, title, content, tags, utility_score, access_count
            FROM shards
            WHERE title LIKE ? OR content LIKE ?
            ORDER BY utility_score DESC, timestamp DESC
            LIMIT ?
        """, (like_query, like_query, limit))
        shards = [dict(row) for row in cursor.fetchall()]

    # Increment access counts for retrieved shards
    if shards:
        ids = [s["id"] for s in shards]
        conn.executemany(
            "UPDATE shards SET access_count = access_count + 1 WHERE id = ?",
            [(id_,) for id_ in ids]
        )
        conn.commit()

    conn.close()
    return shards

def mark_shard(shard_id: int, worked: bool) -> bool:
    """Updates the utility score based on whether the shard worked or failed."""
    conn = get_connection()
    try:
        # Increment/Decrement with exponential dampening for stability
        if worked:
            conn.execute(
                "UPDATE shards SET utility_score = utility_score + 1.0 WHERE id = ?",
                (shard_id,)
            )
        else:
            conn.execute(
                "UPDATE shards SET utility_score = utility_score - 0.5 WHERE id = ?",
                (shard_id,)
            )
        conn.commit()
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()

def compile_recall_packet(shards: list) -> str:
    """Formats retrieved shards into a structured context injection prompt."""
    if not shards:
        return (
            "<!-- NO RELEVANT MEMORY SHARDS RECALLED -->\n"
            "[SYSTEM NOTE: Operating with clean-slate amnesia. "
            "Proceed with first-principles reasoning.]"
        )

    packet_lines = [
        "=== NOUGENSHARDS RECALL PACKET [DAVOS-CLASS SYNTHESIS] ===",
        "The following persistent local memory shards are active for this workspace context.",
        "Use these units of experience to guide decision-making and prevent regression.",
        ""
    ]

    for shard in shards:
        tags = json.loads(shard["tags"]) if shard["tags"] else []
        tags_line = f"Tags: {', '.join(tags)}" if tags else "Tags: none"

        # Determine sentiment/recommendation based on utility score
        recommendation = "STABLE"
        if shard["utility_score"] > 2.0:
            recommendation = "HIGHLY RECOMMENDED"
        elif shard["utility_score"] < 0.5:
            recommendation = "PROCEED WITH CAUTION (LOW UTILITY)"

        packet_lines.extend([
            f"--- SHARD #{shard['id']} [{shard['event_type']}] | {recommendation} ---",
            f"Title: {shard['title']}",
            f"Captured: {shard['timestamp']}",
            f"{tags_line} | Hits: {shard['access_count']}",
            "Machine Note:",
            "```",
            shard["content"].strip(),
            "```",
            ""
        ])

    packet_lines.append(
        "HISTORICAL GUIDANCE: Prioritize the 'HIGHLY RECOMMENDED' solutions. "
        "If a shard is marked 'LOW UTILITY', verify its outcomes against the current environment "
        "before implementation. Write back successful results to the memory vault."
    )
    return "\n".join(packet_lines)

def seed_default_shards():
    """Seeds the database with foundational workspace experience shards if empty."""
    default_seeds = [
        {
            "event_type": "BUG_FIX",
            "title": "Next.js Windows Python Spawn Helper Resolution",
            "content": (
                "RESOLVED: Next.js API routes on Windows fail to spawn Python child processes "
                "if path slashes are unescaped. Fix this by normalizing the PATH using forward "
                "slashes in your Next.js subprocess config or calling `subprocess.Popen` with "
                "shell=True and replacing all backslashes in `process.env.PATH` with forward "
                "slashes."
            ),
            "tags": ["nextjs", "windows", "python", "subprocess", "spawn-helper"]
        },
        {
            "event_type": "KNOWLEDGE",
            "title": "SQLite WAL Mode Lock Verification",
            "content": (
                "GUIDELINE: When running intensive multi-agent operations, SQLite databases "
                "must have Write-Ahead Logging (WAL) enabled via `PRAGMA journal_mode=WAL;` "
                "and a robust timeout (minimum 10.0s) to prevent 'database is locked' "
                "operational errors."
            ),
            "tags": ["sqlite", "wal", "locking", "concurrency"]
        },
        {
            "event_type": "DECISION",
            "title": "Local LLM Thermal Throttling Mitigation Strategy",
            "content": (
                "DECISION: To prevent GPU thermal throttling and system timeouts on local "
                "hardware, automatically unload Ollama models from VRAM if nvidia-smi GPU "
                "temperatures exceed 75°C by calling /api/generate with keep_alive=0."
            ),
            "tags": ["ollama", "gpu", "thermals", "throttling", "optimization"]
        }
    ]

    for seed in default_seeds:
        capture(
            event_type=seed["event_type"],
            title=seed["title"],
            content=seed["content"],
            tags=seed["tags"]
        )

def _parse_front_matter(front_matter: str, title: str, event_type: str, tags: list):
    """Parses simple YAML front matter to extract metadata."""
    for line in front_matter.split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip().lower()
            v = v.strip().strip('"').strip("'")
            if k == "title":
                title = v
            elif k in ("event_type", "type"):
                event_type = v.upper()
            elif k == "tags":
                tags = [t.strip() for t in v.split(",") if t.strip()]
    return title, event_type, tags

def _process_file(file_path: str) -> bool:
    """Processes a single markdown file and imports it into the database."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Default values
        title = os.path.basename(file_path).replace(".md", "").replace("_", " ").title()
        event_type = "TECHNICAL_DEEP_DIVE"
        tags = ["discovered"]
        body = content

        # Simple YAML front-matter parser
        yaml_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
        if yaml_match:
            front_matter = yaml_match.group(1)
            body = yaml_match.group(2)
            title, event_type, tags = _parse_front_matter(front_matter, title, event_type, tags)

        return capture(event_type=event_type, title=title, content=body, tags=tags)
    except OSError:
        return False

def discover_and_import_shards(directory_path: str = None):
    """
    Scans a given directory (defaults to current workspace directory)
    for markdown files representing shards and imports them.
    Supports parsing YAML headers if present.
    """
    if not directory_path:
        directory_path = os.getcwd()

    # Scan for markdown shard files
    patterns = [
        os.path.join(directory_path, "intelligence_shard_*.md"),
        os.path.join(directory_path, "shard_*.md")
    ]

    found_files = []
    for pattern in patterns:
        found_files.extend(glob.glob(pattern))

    imported_count = 0
    for file_path in found_files:
        if _process_file(file_path):
            imported_count += 1

    return imported_count

# Initialize database and run auto-discovery on load
init_db()
discover_and_import_shards()

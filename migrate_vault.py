import sqlite3
import hashlib
import json
from datetime import datetime

# Old path and new path
old_db = r'C:\Users\super\Watchtower\vault\nougenai_memory_vault.db'
new_db = r'C:\Users\super\Watchtower\vault\nougen_shards_elevated.db'

# Initialize New DB
conn_new = sqlite3.connect(new_db)
cursor_new = conn_new.cursor()

cursor_new.execute("""
    CREATE TABLE IF NOT EXISTS shards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        event_type TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        tags TEXT,
        utility_score REAL DEFAULT 1.0,
        access_count INTEGER DEFAULT 0,
        file_hash TEXT UNIQUE NOT NULL,
        embedding BLOB
    );
""")

cursor_new.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS shards_fts USING fts5(
        title,
        content,
        content='shards',
        content_rowid='id'
    );
""")

# Sync trigger
cursor_new.execute("DROP TRIGGER IF EXISTS shards_ai")
cursor_new.execute("""
    CREATE TRIGGER shards_ai AFTER INSERT ON shards BEGIN
        INSERT INTO shards_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
    END;
""")

# Migrate Data
conn_old = sqlite3.connect(old_db)
old_rows = conn_old.execute("SELECT * FROM shards").fetchall()

print(f"Migrating {len(old_rows)} records...")

for row in old_rows:
    # Row structure: id, category, source, finding, logic, timestamp, utility_score, access_count, outcome_history, tags
    # New structure: timestamp, event_type, title, content, tags, utility_score, access_count, file_hash
    
    old_id, category, source, finding, logic, timestamp, utility, access, outcome, tags = row
    
    event_type = category
    title = f"{source}: {finding}"
    content = logic
    
    # Generate unique hash based on content
    fhash = hashlib.md5(f"{event_type}{title}{content}".encode()).hexdigest()
    
    cursor_new.execute("""
        INSERT INTO shards (timestamp, event_type, title, content, tags, utility_score, access_count, file_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (timestamp, event_type, title, content, tags, utility, access, fhash))

conn_new.commit()
print("Migration completed.")
conn_old.close()
conn_new.close()

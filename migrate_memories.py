import sqlite3

backup_db = r'C:\Users\super\Watchtower\vault\nougenai_memory_vault.db.bak'
new_memories_db = r'C:\Users\super\Watchtower\vault\nougen_memories.db'

conn_backup = sqlite3.connect(backup_db)
conn_new = sqlite3.connect(new_memories_db)

schema = conn_backup.execute("SELECT sql FROM sqlite_master WHERE name='memories'").fetchone()[0]
conn_new.execute(schema)
conn_new.execute("PRAGMA journal_mode=WAL;")

rows = conn_backup.execute("SELECT * FROM memories").fetchall()

print(f"Migrating {len(rows)} memories...")

placeholders = ','.join(['?'] * len(rows[0]))
conn_new.executemany(f"INSERT INTO memories VALUES ({placeholders})", rows)

conn_new.commit()
print("Memories migration completed.")
conn_backup.close()
conn_new.close()

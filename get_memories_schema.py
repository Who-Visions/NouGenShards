import sqlite3
backup_db = r'%USERPROFILE%\Watchtower\vault\nougenai_memory_vault.db.bak'
conn = sqlite3.connect(backup_db)
schema = conn.execute("SELECT sql FROM sqlite_master WHERE name='memories'").fetchone()[0]
print(schema)
conn.close()

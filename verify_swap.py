import sqlite3
db_path = r'%USERPROFILE%\Watchtower\vault\nougenai_memory_vault.db'
conn = sqlite3.connect(db_path)
print([row[0] for row in conn.execute('SELECT name FROM sqlite_master WHERE type="table"')])
conn.close()

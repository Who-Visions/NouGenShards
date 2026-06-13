import sqlite3
db_path = r'C:\Users\super\Watchtower\vault\nougenai_memory_vault.db.bak'
conn = sqlite3.connect(db_path)
print('--- SCHEMA: memories ---')
cursor = conn.execute("SELECT sql FROM sqlite_master WHERE name='memories'")
print(cursor.fetchone()[0])
conn.close()

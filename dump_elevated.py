import sqlite3
db_path = r'C:\Users\super\Watchtower\vault\nougen_shards_elevated.db'
conn = sqlite3.connect(db_path)

print('--- SCHEMA: shards ---')
cursor = conn.execute("SELECT sql FROM sqlite_master WHERE name='shards'")
result = cursor.fetchone()
if result:
    print(result[0])

print('\n--- SAMPLE ROWS: shards (LIMIT 2) ---')
cursor = conn.execute('SELECT id, timestamp, event_type, title, file_hash FROM shards LIMIT 2')
for row in cursor.fetchall():
    print(row)
conn.close()

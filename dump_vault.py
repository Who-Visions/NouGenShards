import sqlite3
db_path = r'C:\Users\super\Watchtower\vault\nougenai_memory_vault.db'
conn = sqlite3.connect(db_path)

print('--- SCHEMA: shards ---')
# Using a safer way to query schema
cursor = conn.execute("SELECT sql FROM sqlite_master WHERE name='shards'")
result = cursor.fetchone()
if result:
    print(result[0])
else:
    print("Table 'shards' not found.")

print('\n--- SAMPLE ROWS: shards ---')
cursor = conn.execute('SELECT * FROM shards LIMIT 5')
for row in cursor.fetchall():
    print(row)
conn.close()

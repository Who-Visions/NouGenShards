import sqlite3
import json

db_path = r'%USERPROFILE%\.nougen\shards\nougen_shards.db'
conn = sqlite3.connect(db_path)

print('--- SCHEMA: shards ---')
print(conn.execute("SELECT sql FROM sqlite_master WHERE name='shards'").fetchone()[0])

print('\n--- SCHEMA: shards_fts ---')
print(conn.execute("SELECT sql FROM sqlite_master WHERE name='shards_fts'").fetchone()[0])

print('\n--- SAMPLE ROWS: shards ---')
for row in conn.execute('SELECT * FROM shards LIMIT 5').fetchall():
    print(row)
conn.close()

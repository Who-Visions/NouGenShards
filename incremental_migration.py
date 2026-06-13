import sqlite3

backup_db = r'%USERPROFILE%\Watchtower\vault\nougenai_memory_vault.db.bak'
live_db = r'%USERPROFILE%\Watchtower\vault\nougenai_memory_vault.db'

conn_backup = sqlite3.connect(backup_db)
conn_live = sqlite3.connect(live_db)

# Get all tables from backup
backup_tables = [row[0] for row in conn_backup.execute('SELECT name FROM sqlite_master WHERE type="table"')]

for table in backup_tables:
    if table == 'sqlite_sequence': continue
    
    # Get schema
    schema = conn_backup.execute(f"SELECT sql FROM sqlite_master WHERE name='{table}'").fetchone()[0]
    
    print(f"Migrating table: {table}")
    
    # Create table in live if not exists
    conn_live.execute(schema)
    
    # Copy data
    rows = conn_backup.execute(f"SELECT * FROM {table}").fetchall()
    if rows:
        # Generate placeholders
        cols = len(rows[0])
        placeholders = ','.join(['?'] * cols)
        
        # Insert or ignore to handle existing data
        try:
            conn_live.executemany(f"INSERT OR IGNORE INTO {table} VALUES ({placeholders})", rows)
        except sqlite3.OperationalError as e:
            print(f"Skipping table {table} due to error: {e}")

conn_live.commit()
print("Incremental migration completed.")
conn_backup.close()
conn_live.close()

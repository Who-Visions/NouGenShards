import sqlite3

backup_db = r'C:\Users\super\Watchtower\vault\nougenai_memory_vault.db.bak'
live_db = r'C:\Users\super\Watchtower\vault\nougenai_memory_vault.db'

conn_backup = sqlite3.connect(backup_db)
conn_live = sqlite3.connect(live_db)

# Get all tables from backup
backup_tables = [row[0] for row in conn_backup.execute('SELECT name FROM sqlite_master WHERE type="table"')]

for table in backup_tables:
    if table in ['sqlite_sequence', 'shards', 'shards_fts', 'shards_fts_data', 'shards_fts_idx', 'shards_fts_docsize', 'shards_fts_config']:
        continue
    
    # Get schema for new tables
    schema = conn_backup.execute(f"SELECT sql FROM sqlite_master WHERE name='{table}'").fetchone()[0]
    
    print(f"Migrating table: {table}")
    
    # Create table in live if not exists
    try:
        conn_live.execute(schema)
    except sqlite3.OperationalError:
        print(f"Table {table} already exists, skipping creation.")
    
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
            print(f"Error migrating data for table {table}: {e}")

conn_live.commit()
print("Incremental migration completed.")
conn_backup.close()
conn_live.close()

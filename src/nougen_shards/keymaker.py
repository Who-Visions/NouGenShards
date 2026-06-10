"""
Keymaker Agent: Secure Secret Ingestion & Management
Mimics the 'Atibon' workflow for the NouGenAi franchise.
"""
import os
import sqlite3
import csv
import json
from datetime import datetime
from pathlib import Path

# Portable Vault Resolution
# Default to a local .nougen_vault in the repo, but allow environment override for sovereign users
VAULT_DIR = Path(os.getenv("NOUGEN_VAULT_DIR", ".nougen_vault"))
DB_PATH = VAULT_DIR / "shards_secrets.db"
CSV_PATH = VAULT_DIR / "shards_secrets.csv"
SECRETS_JSON_DIR = VAULT_DIR / "service_accounts"

def init_keymaker():
    """Initializes the Keymaker's infrastructure."""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    SECRETS_JSON_DIR.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS secrets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            secret_key TEXT UNIQUE NOT NULL,
            secret_value TEXT NOT NULL,
            last_rotated TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    print(f"[*] Keymaker initialized at {VAULT_DIR.absolute()}")

def ingest_secret(key: str, value: str):
    """
    Ingests a secret into the DB, exports to CSV, and redacts output.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            INSERT OR REPLACE INTO secrets (secret_key, secret_value, last_rotated)
            VALUES (?, ?, ?)
        """, (key, value, timestamp))
        conn.commit()
        print(f"  [+] Ingested: {key} (Value Redacted)")
        _export_to_csv()
    except Exception as e:
        print(f"  [!] Error ingesting {key}: {e}")
    finally:
        conn.close()

def ingest_service_account(json_data: str):
    """
    Ingests a Google Service Account JSON, saves to file, and stores project metadata.
    """
    try:
        data = json.loads(json_data)
        project_id = data.get("project_id", "unknown_project")
        client_email = data.get("client_email", "unknown_email")
        
        file_name = f"{project_id}_service_account.json"
        target_path = SECRETS_JSON_DIR / file_name
        
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        # Store metadata in DB
        ingest_secret(f"GCP_SA_{project_id.upper()}", client_email)
        print(f"  [+] Service Account for {project_id} stored at {target_path}")
        
    except Exception as e:
        print(f"  [!] Error ingesting service account: {e}")

def _export_to_csv():
    """Exports the secrets table to a CSV for human-auditable backup."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, secret_key, secret_value, last_rotated FROM secrets")
    rows = cursor.fetchall()
    
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "secret_key", "secret_value", "last_rotated"])
        writer.writerows(rows)
    conn.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python keymaker.py init | add <key> <value> | sa <json_content>")
        sys.exit(1)
        
    cmd = sys.argv[1]
    if cmd == "init":
        init_keymaker()
    elif cmd == "add" and len(sys.argv) == 4:
        ingest_secret(sys.argv[2], sys.argv[3])
    elif cmd == "sa" and len(sys.argv) == 3:
        ingest_service_account(sys.argv[2])
    else:
        print("Invalid command or arguments.")

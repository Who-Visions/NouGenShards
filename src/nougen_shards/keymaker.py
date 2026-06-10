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
VAULT_DIR = Path(os.getenv("NOUGEN_VAULT_DIR", ".nougen_vault"))
DB_PATH = VAULT_DIR / "shards_secrets.db"
CSV_PATH = VAULT_DIR / "shards_secrets.csv"
SECRETS_JSON_DIR = VAULT_DIR / "service_accounts"


def init_vault():
    """Initializes the vault database schema."""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    SECRETS_JSON_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS secrets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            secret_key TEXT UNIQUE NOT NULL,
            secret_value TEXT NOT NULL,
            last_rotated TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS external_dbs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uri TEXT NOT NULL,
            table_name TEXT NOT NULL,
            title_col TEXT NOT NULL,
            content_col TEXT NOT NULL,
            last_connected TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cloud_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            last_connected TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


def _export_to_csv():
    """Exports the secrets table to a CSV for human-auditable backup."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, secret_key, secret_value, last_rotated FROM secrets")
        rows = cursor.fetchall()
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f_out:
            writer = csv.writer(f_out)
            writer.writerow(["id", "secret_key", "secret_value", "last_rotated"])
            writer.writerows(rows)
    except sqlite3.Error:
        pass
    finally:
        conn.close()


def ingest_secret(key: str, value: str):
    """
    Ingests a secret into the DB, exports to CSV, and redacts output.
    """
    init_vault()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("""
            INSERT OR REPLACE INTO secrets (secret_key, secret_value, last_rotated)
            VALUES (?, ?, ?)
        """, (key, value, timestamp))
        conn.commit()
        print(f"  [+] Ingested: {key} (Value Redacted)")
        _export_to_csv()
    except sqlite3.Error as exc:
        print(f"  [!] Error ingesting {key}: {exc}")
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

        with open(target_path, "w", encoding="utf-8") as f_out:
            json.dump(data, f_out, indent=2)

        # Store metadata in DB
        ingest_secret(f"GCP_SA_{project_id.upper()}", client_email)
        print(f"  [+] Service Account for {project_id} stored at {target_path}")

    except (json.JSONDecodeError, OSError) as exc:
        print(f"  [!] Error ingesting service account: {exc}")


def register_external_db(uri: str, table_name: str, title_col: str, content_col: str):
    """Registers a new external database connection."""
    init_vault()
    conn = sqlite3.connect(str(DB_PATH))
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('''
        INSERT INTO external_dbs (uri, table_name, title_col, content_col, last_connected)
        VALUES (?, ?, ?, ?, ?)
    ''', (uri, table_name, title_col, content_col, timestamp))
    conn.commit()
    conn.close()


def list_external_dbs() -> list:
    """Returns all registered external database configurations."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM external_dbs").fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def register_cloud_node(url: str, name: str):
    """Registers a new remote NouGenShards cloud node."""
    init_vault()
    conn = sqlite3.connect(str(DB_PATH))
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('''
        INSERT OR REPLACE INTO cloud_nodes (url, name, last_connected)
        VALUES (?, ?, ?)
    ''', (url, name, timestamp))
    conn.commit()
    conn.close()


def list_cloud_nodes() -> list:
    """Returns all registered cloud node configurations."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM cloud_nodes").fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def get_secret(key: str) -> str:
    """Retrieves a secret value from the DB by its key."""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT secret_value FROM secrets WHERE secret_key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def list_providers() -> list:
    """Returns a list of keys currently stored in the vault."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT secret_key FROM secrets")
        return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python keymaker.py init | add <key> <value> | sa <json_content>")
        sys.exit(1)

    CMD = sys.argv[1]
    if CMD == "init":
        init_vault()
        print(f"[*] Keymaker initialized at {VAULT_DIR.absolute()}")
    elif CMD == "add" and len(sys.argv) == 4:
        ingest_secret(sys.argv[2], sys.argv[3])
    elif CMD == "sa" and len(sys.argv) == 3:
        ingest_service_account(sys.argv[2])
    else:
        print("Invalid command or arguments.")

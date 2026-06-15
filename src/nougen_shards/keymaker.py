"""
Keymaker Agent: Secure Secret Ingestion & Management
Mimics the 'Atibon' workflow for the NouGenAi franchise.
"""
import base64
import ctypes
import ctypes.wintypes
import hashlib
import os
import sqlite3
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

# Marker prefix for values encrypted at rest via Windows DPAPI (user-bound).
_DPAPI_PREFIX = "dpapi1:"
# Marker prefix for values stored in the OS keyring (macOS Keychain / Secret Service).
_KEYRING_PREFIX = "keyring1:"
_KEYRING_SERVICE = "nougenshards-vault"


def _is_encrypted(stored: str) -> bool:
    """True if the stored value is protected (DPAPI or keyring), not legacy plaintext."""
    return str(stored).startswith((_DPAPI_PREFIX, _KEYRING_PREFIX))


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi_call(func_name: str, data: bytes) -> bytes:
    """Invokes CryptProtectData/CryptUnprotectData on the given bytes."""
    blob_in = _DataBlob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)),
                                              ctypes.POINTER(ctypes.c_char)))
    blob_out = _DataBlob()
    func = getattr(ctypes.windll.crypt32, func_name)
    if not func(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise OSError(f"{func_name} failed (DPAPI)")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _protect(value: str, key: Optional[str] = None) -> str:
    """
    Encrypts a secret value at rest. Fails closed: never stores plaintext silently.

    Windows  -> DPAPI (user-bound).
    Other OS -> OS keyring (macOS Keychain / freedesktop Secret Service) if `keyring`
                is installed; the DB then stores only a reference, not the secret.
                If keyring is unavailable, refuse unless NOUGEN_ALLOW_PLAINTEXT_VAULT=1.
    """
    if os.name == "nt":
        encrypted = _dpapi_call("CryptProtectData", value.encode("utf-8"))
        return _DPAPI_PREFIX + base64.b64encode(encrypted).decode("ascii")

    try:
        import keyring  # pylint: disable=import-outside-toplevel
        ref = key or hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        keyring.set_password(_KEYRING_SERVICE, ref, value)
        return _KEYRING_PREFIX + ref
    except ImportError:
        if os.getenv("NOUGEN_ALLOW_PLAINTEXT_VAULT") == "1":
            return value
        raise RuntimeError(
            "No OS keyring backend available on this platform. "
            "Install it with 'pip install keyring', or set "
            "NOUGEN_ALLOW_PLAINTEXT_VAULT=1 to override (not recommended).") from None


def _unprotect(stored: str) -> str:
    """Decrypts a stored value; passes through legacy plaintext rows untouched."""
    if stored.startswith(_DPAPI_PREFIX):
        raw = base64.b64decode(stored[len(_DPAPI_PREFIX):])
        return _dpapi_call("CryptUnprotectData", raw).decode("utf-8")
    if stored.startswith(_KEYRING_PREFIX):
        import keyring  # pylint: disable=import-outside-toplevel
        ref = stored[len(_KEYRING_PREFIX):]
        value = keyring.get_password(_KEYRING_SERVICE, ref)
        if value is None:
            raise OSError(f"Keyring entry '{ref}' not found.")
        return value
    return stored  # legacy plaintext row (pre-encryption migration)


def _fingerprint(value: str) -> str:
    """Non-reversible audit fingerprint of a secret (first 12 hex of SHA-256)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]

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
    """Exports a metadata-only audit ledger. NEVER writes secret values to disk."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, secret_key, secret_value, last_rotated FROM secrets")
        rows = cursor.fetchall()
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f_out:
            writer = csv.writer(f_out)
            writer.writerow(["id", "secret_key", "fingerprint_sha256_12", "encrypted", "last_rotated"])
            for row_id, key, stored, rotated in rows:
                try:
                    fp = _fingerprint(_unprotect(stored))
                except OSError:
                    fp = "unreadable"
                writer.writerow([row_id, key, fp, _is_encrypted(stored), rotated])
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
        """, (key, _protect(value, key), timestamp))
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

        # Lock file ACL to the current user only (constitution 0.2 rule 3)
        if os.name == "nt":
            import subprocess  # pylint: disable=import-outside-toplevel
            user = os.environ.get("USERNAME", "")
            if user:
                subprocess.run(
                    ["icacls", str(target_path), "/inheritance:r", "/grant:r", f"{user}:F"],
                    capture_output=True, check=False, timeout=10)

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


def get_secret(key: str) -> Optional[str]:
    """Retrieves a secret value from the DB by its key."""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT secret_value FROM secrets WHERE secret_key = ?", (key,))
        row = cursor.fetchone()
        return _unprotect(str(row[0])) if row else None
    except (sqlite3.Error, OSError):
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


def migrate_to_encrypted() -> int:
    """Re-encrypts any legacy plaintext rows in place. Returns count migrated."""
    if not DB_PATH.exists():
        return 0
    conn = sqlite3.connect(str(DB_PATH))
    migrated = 0
    try:
        rows = conn.execute("SELECT secret_key, secret_value FROM secrets").fetchall()
        for key, stored in rows:
            if not _is_encrypted(stored):
                conn.execute("UPDATE secrets SET secret_value = ? WHERE secret_key = ?",
                             (_protect(str(stored), key), key))
                migrated += 1
        conn.commit()
    finally:
        conn.close()
    if migrated:
        _export_to_csv()
    return migrated


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python keymaker.py init | add <key> <value> | sa <json_content> | migrate")
        sys.exit(1)

    CMD = sys.argv[1]
    if CMD == "migrate":
        COUNT = migrate_to_encrypted()
        print(f"[*] Migrated {COUNT} legacy plaintext secrets to DPAPI encryption.")
    elif CMD == "init":
        init_vault()
        print(f"[*] Keymaker initialized at {VAULT_DIR.absolute()}")
    elif CMD == "add" and len(sys.argv) == 4:
        ingest_secret(sys.argv[2], sys.argv[3])
    elif CMD == "sa" and len(sys.argv) == 3:
        ingest_service_account(sys.argv[2])
    else:
        print("Invalid command or arguments.")

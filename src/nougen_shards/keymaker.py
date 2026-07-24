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


# --------------------------------------------------------------------------
# Filesystem hardening: owner-only vault dirs, secrets DB and SA key files.
#
# Service-account JSONs hold `private_key` in PLAINTEXT on disk; the ACL is
# their only protection, not defence-in-depth. Every failure here is therefore
# fatal and loud -- silently continuing leaves credentials at inherited perms.
# Rule 0.2: the owning account resolves env -> OS API -> probe, never hardcode.
# --------------------------------------------------------------------------

class VaultProtectionError(RuntimeError):
    """Owner-only protection could not be applied to a vault path."""


# Ordered env overrides; NOUGEN_ACL_USER lets an operator name the account
# explicitly (service contexts where USERNAME is not the intended owner).
_ACL_USER_ENV_VARS = ("NOUGEN_ACL_USER", "USERNAME", "USER", "LOGNAME")
# Directories are hardened once per process; files are always re-applied so a
# recreated (freshly inheriting) file is never left on a stale cache entry.
_HARDENED_DIRS: set = set()


def _log(message: str) -> None:
    print(f"[keymaker] {message}")


def _windows_user_from_api() -> str:
    """Current account via advapi32!GetUserNameW -- independent of the env block."""
    size = ctypes.wintypes.DWORD(0)
    ctypes.windll.advapi32.GetUserNameW(None, ctypes.byref(size))
    buf = ctypes.create_unicode_buffer(size.value or 257)
    size = ctypes.wintypes.DWORD(len(buf))
    if not ctypes.windll.advapi32.GetUserNameW(buf, ctypes.byref(size)):
        raise OSError("GetUserNameW failed")
    return buf.value.strip()


def _resolve_acl_user() -> str:
    """
    Resolve the account that must own the vault: env -> OS API -> shell probe.

    Raises VaultProtectionError if no identity can be established. An unknown
    owner means the ACL cannot be applied, and skipping it (the old behaviour
    when USERNAME was empty) leaves SA private keys readable by anyone the
    inherited profile ACL allows.
    """
    for var in _ACL_USER_ENV_VARS:
        val = os.environ.get(var, "").strip()
        if val:
            return val

    if os.name == "nt":
        try:
            val = _windows_user_from_api()
            if val:
                _log(f"ACL user resolved via GetUserNameW (env vars empty): {val}")
                return val
        except (OSError, AttributeError, ValueError) as exc:
            _log(f"GetUserNameW probe failed: {exc}")

    try:
        import getpass  # pylint: disable=import-outside-toplevel
        val = (getpass.getuser() or "").strip()
        if val:
            _log(f"ACL user resolved via getpass.getuser(): {val}")
            return val
    except Exception as exc:  # pylint: disable=broad-except
        # getpass raises ImportError/KeyError/OSError depending on platform.
        _log(f"getpass.getuser() probe failed: {exc}")

    try:
        import subprocess  # pylint: disable=import-outside-toplevel
        proc = subprocess.run(["whoami"], capture_output=True, text=True,
                              timeout=15, check=True)
        val = (proc.stdout or "").strip().splitlines()
        if val and val[0].strip():
            _log(f"ACL user resolved via 'whoami' probe: {val[0].strip()}")
            return val[0].strip()
    except Exception as exc:  # pylint: disable=broad-except
        _log(f"'whoami' probe failed: {exc}")

    raise VaultProtectionError(
        "Cannot resolve the current user, so owner-only permissions cannot be "
        "applied to the credential vault. Refusing to leave secrets at "
        "inherited permissions -- set NOUGEN_ACL_USER to the owning account.")


def _icacls_principals(target: str) -> list:
    """Principals holding an explicit ACE on `target`, per `icacls` output."""
    import subprocess  # pylint: disable=import-outside-toplevel
    proc = subprocess.run(["icacls", target], capture_output=True, text=True,
                          check=False, timeout=30)
    principals = []
    for line in (proc.stdout or "").splitlines():
        if ":(" not in line:
            continue
        head = line.split(":(")[0]
        if head.startswith(target):
            head = head[len(target):]
        head = head.strip()
        if head:
            principals.append(head)
    return principals


def _same_principal(a: str, b: str) -> bool:
    """Compare account names ignoring case and DOMAIN\\ / MACHINE\\ qualifiers."""
    return a.split("\\")[-1].strip().lower() == b.split("\\")[-1].strip().lower()


def _harden_path(path, is_dir: bool = False) -> None:
    """
    Restrict `path` to the current user only. POSIX: 0700/0600. Windows:
    icacls with inheritance stripped and a single grant to the resolved user.

    Raises VaultProtectionError on any failure -- never returns having skipped.
    """
    target = str(path)
    if is_dir and target in _HARDENED_DIRS:
        return

    if os.name != "nt":
        try:
            os.chmod(target, 0o700 if is_dir else 0o600)
        except OSError as exc:
            raise VaultProtectionError(f"chmod failed for {target}: {exc}") from exc
        if is_dir:
            _HARDENED_DIRS.add(target)
        return

    import subprocess  # pylint: disable=import-outside-toplevel
    user = _resolve_acl_user()
    # (OI)(CI) so new children inherit the owner-only grant; files take plain F.
    grant = f"{user}:(OI)(CI)(F)" if is_dir else f"{user}:(F)"
    try:
        proc = subprocess.run(
            ["icacls", target, "/inheritance:r", "/grant:r", grant],
            capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise VaultProtectionError(f"icacls could not run for {target}: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise VaultProtectionError(
            f"icacls failed to lock {target} to {user} "
            f"(rc={proc.returncode}): {detail}")

    # /inheritance:r strips INHERITED ACEs and /grant:r only replaces the named
    # user's grant -- any pre-existing EXPLICIT ACE for another principal (e.g.
    # a BUILTIN\Users grant on a restored or copied key file) survives both.
    # Strip the survivors so the DACL really is owner-only, then verify.
    for principal in _icacls_principals(target):
        if _same_principal(principal, user):
            continue
        _log(f"Removing foreign ACE {principal} from {target}")
        subprocess.run(["icacls", target, "/remove:g", principal],
                       capture_output=True, text=True, check=False, timeout=30)
        subprocess.run(["icacls", target, "/remove:d", principal],
                       capture_output=True, text=True, check=False, timeout=30)

    survivors = [p for p in _icacls_principals(target) if not _same_principal(p, user)]
    if survivors:
        raise VaultProtectionError(
            f"{target} is still accessible to {survivors} after hardening; "
            f"refusing to treat it as owner-only.")

    if is_dir:
        _HARDENED_DIRS.add(target)


# Portable Vault Resolution
VAULT_DIR = Path(os.getenv("NOUGEN_VAULT_DIR", ".nougen_vault"))
DB_PATH = VAULT_DIR / "shards_secrets.db"
CSV_PATH = VAULT_DIR / "shards_secrets.csv"
SECRETS_JSON_DIR = VAULT_DIR / "service_accounts"


def init_vault():
    """Initializes the vault database schema."""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    SECRETS_JSON_DIR.mkdir(parents=True, exist_ok=True)
    # Restrict the vault to the owner on BOTH platforms: POSIX modes, Windows
    # ACLs (inheritance stripped + current user only). Windows was previously
    # skipped entirely, so the vault inherited whatever the profile allowed.
    for d in (VAULT_DIR, SECRETS_JSON_DIR):
        _harden_path(d, is_dir=True)

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
    # The secrets DB holds every ingested credential (DPAPI/keyring-wrapped, but
    # still the whole keyring surface) and previously got no chmod and no ACL on
    # any platform -- it simply inherited the profile's permissions. Lock it to
    # the owner like the SA JSONs, after close() so no WAL/journal handle is open.
    _harden_path(DB_PATH)


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
    except sqlite3.Error as e:
        print(f"[keymaker] CSV audit ledger export failed: {e}")
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

        # Ensure the (owner-only) vault dirs exist before writing the key file.
        init_vault()

        file_name = f"{project_id}_service_account.json"
        target_path = SECRETS_JSON_DIR / file_name

        # This file holds the SA private key. On POSIX create it owner-only from
        # the start (O_CREAT|0o600) so there is no window where it is world/group
        # readable before perms are applied; on Windows the icacls lock below
        # restricts it (default-deny inheritance + grant current user).
        payload = json.dumps(data, indent=2)
        if os.name == "nt":
            with open(target_path, "w", encoding="utf-8") as f_out:
                f_out.write(payload)
        else:
            fd = os.open(str(target_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            # O_CREAT's mode only applies to a NEW inode; O_TRUNC on a pre-existing
            # (possibly 0644) file keeps the old perms. fchmod enforces 0600 on
            # re-ingest/rotation so existing vaults are repaired, not left readable.
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f_out:
                f_out.write(payload)

        # Lock the file to the current user only (constitution 0.2 rule 3).
        # This file contains `private_key` in PLAINTEXT, so the ACL/mode is its
        # ONLY protection. Previously this depended on a non-empty USERNAME and
        # used check=False, so an empty env var or a failing icacls silently
        # left the key at inherited permissions. Now it fails loudly, and the
        # unprotected copy we just wrote is removed before the error surfaces.
        try:
            _harden_path(target_path)
        except VaultProtectionError:
            try:
                os.remove(target_path)
                _log(f"Removed unprotected service-account file {target_path}")
            except OSError as cleanup_exc:
                _log(f"WARNING: could not remove unprotected {target_path}: {cleanup_exc}")
            raise

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
    # The URI usually embeds DB credentials (user:pass@host) — protect it at
    # rest like any other secret instead of storing the connection string raw.
    conn.execute('''
        INSERT INTO external_dbs (uri, table_name, title_col, content_col, last_connected)
        VALUES (?, ?, ?, ?, ?)
    ''', (_protect(uri), table_name, title_col, content_col, timestamp))
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
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["uri"] = _unprotect(d["uri"])  # legacy plaintext passes through
            except Exception:  # pylint: disable=broad-except
                # Any failure to decrypt ONE row (keyring entry missing -> OSError,
                # backend not installed -> ImportError, no backend available ->
                # keyring.errors.NoKeyringError, etc.) must skip that row, never
                # abort the federation sweep (federated_retrieve calls this before
                # its graceful-degradation try). Intentionally broad.
                continue
            result.append(d)
        return result
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
                protected = _protect(str(stored), key)
                # Don't claim a migration if the plaintext escape-hatch is active
                # (_protect returned the value unchanged) — it's still plaintext.
                if not _is_encrypted(protected):
                    continue
                conn.execute("UPDATE secrets SET secret_value = ? WHERE secret_key = ?",
                             (protected, key))
                migrated += 1

        # Also migrate legacy plaintext external-DB URIs (they embed user:pass).
        # The external_dbs table predates URI encryption, so existing rows hold
        # raw connection strings that this otherwise leaves untouched.
        try:
            ext_rows = conn.execute("SELECT id, uri FROM external_dbs").fetchall()
        except sqlite3.Error:
            ext_rows = []
        for row_id, uri in ext_rows:
            if not _is_encrypted(uri):
                protected_uri = _protect(str(uri))
                if not _is_encrypted(protected_uri):
                    continue  # plaintext escape-hatch active
                conn.execute("UPDATE external_dbs SET uri = ? WHERE id = ?",
                             (protected_uri, row_id))
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

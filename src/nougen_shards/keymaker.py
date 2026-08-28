"""
Keymaker Agent: Secure Secret Ingestion & Management
Mimics the 'Atibon' workflow for the NouGenAi franchise.
"""
import base64
import ctypes
import ctypes.wintypes
import hashlib
import logging
import os
import sqlite3
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Marker prefix for values encrypted at rest via Windows DPAPI (user-bound).
_DPAPI_PREFIX = "dpapi1:"
# A DPAPI blob opens with dwVersion=1 and the provider GUID
# d08c9ddf-0115-11d1-8c7a-00c04fc297eb. Layers are detected by these bytes
# rather than by the marker prefix, because only the OUTERMOST layer carries
# the prefix -- see _unprotect.
_DPAPI_MAGIC = bytes([0x01, 0x00, 0x00, 0x00, 0xD0, 0x8C, 0x9D, 0xDF])
# Generous ceiling on re-protection depth; rows in the field measure 3.
_DPAPI_MAX_LAYERS = int(os.getenv("NOUGEN_KEYMAKER_MAX_LAYERS", "8"))
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


def _as_dpapi_blob(stored: str) -> Optional[bytes]:
    """The raw blob if `stored` is base64 of a DPAPI blob, tagged or bare."""
    payload = stored[len(_DPAPI_PREFIX):] if stored.startswith(_DPAPI_PREFIX) else stored
    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception:  # pylint: disable=broad-except
        return None
    return raw if raw[:8] == _DPAPI_MAGIC else None


def _unprotect(stored: str) -> str:
    """Decrypts a stored value; passes through legacy plaintext rows untouched.

    Peels EVERY DPAPI layer, not just one. A value that is re-protected -- by a
    migration, a re-ingest, or a second pass of the ingest tool -- ends up
    wrapped several times deep, and only the outermost layer keeps the
    `dpapi1:` marker. Stopping when the marker disappears returns a base64
    blob that looks like a secret and fails as one: measured 2026-08-15, rows
    in `agent_secrets.db` needed three passes, and a one-pass read handed an
    820-character ciphertext to a provider that answered 401. Layers are
    therefore detected by blob magic, which does not depend on tagging.
    """
    if stored.startswith(_DPAPI_PREFIX) and _as_dpapi_blob(stored) is None:
        # Tagged as protected but not a readable blob: fail loudly rather than
        # hand the caller a marker string it would spend as a secret.
        raise OSError("Value is tagged 'dpapi1:' but is not a valid DPAPI blob.")
    if _as_dpapi_blob(stored) is not None:
        current = stored
        for _ in range(_DPAPI_MAX_LAYERS):
            # Strip only for detection -- never mutate the value we return, in
            # case a secret legitimately carries trailing whitespace.
            raw = _as_dpapi_blob(current.strip())
            if raw is None:
                return current
            current = _dpapi_call("CryptUnprotectData", raw).decode("utf-8")
        return current
    if stored.startswith(_KEYRING_PREFIX):
        import keyring  # pylint: disable=import-outside-toplevel
        ref = stored[len(_KEYRING_PREFIX):]
        value = keyring.get_password(_KEYRING_SERVICE, ref)
        if value is None:
            raise OSError(f"Keyring entry '{ref}' not found.")
        return value
    return stored  # legacy plaintext row (pre-encryption migration)


def _fingerprint(value: str | bytes) -> str:
    """Non-reversible audit fingerprint of a secret (first 12 hex of SHA-256)."""
    raw = value if isinstance(value, bytes) else str(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]

# Portable Vault Resolution
# This was `Path(os.getenv("NOUGEN_VAULT_DIR", ".nougen_vault"))`, which had two
# defects that split one logical vault into several real ones:
#
#   1. `.nougen_vault` is CWD-RELATIVE. The store moved with the working
#      directory, so a secret ingested from one directory was invisible from
#      another -- get_secret returned None and callers concluded the credential
#      had never been ingested.
#   2. NOUGEN_VAULT_DIR is the MEMORY vault (the shard cluster). Sharing it
#      pointed the secrets DB at a directory holding 40+ shard databases, and
#      init_vault() then tried to icacls that whole tree, which timed out at 30s
#      and made vault init fail outright.
#
# Measured on a live deployment: 44 secrets across four stores, one stranded alone.
#
# Resolution is DETERMINISTIC -- explicit env, else a user-anchored default.
# Searching upward from CWD for a nearby `.nougen_vault` was implemented and
# rejected: it is the same CWD-sensitivity in a longer form. Legacy stores are
# surfaced by find_legacy_stores() so drift is migrated deliberately.
ENV_SECRETS_VAULT = "NOUGEN_SECRETS_VAULT_DIR"
_LEGACY_VAULT_DIRNAME = ".nougen_vault"
DB_FILENAME = "agent_secrets.db"


def resolve_secrets_vault_dir() -> Path:
    explicit = os.getenv(ENV_SECRETS_VAULT, "").strip()
    if explicit:
        return Path(explicit)
    return Path.home() / ".nougen" / "secrets"


def find_legacy_stores(roots=None) -> list:
    """Secret stores outside the canonical vault, so fragmentation is reported.

    `get_secret` returning None reads exactly like "never ingested" rather than
    "you are pointed at the wrong file", which is why this is worth surfacing.
    """
    canonical = resolve_secrets_vault_dir().resolve()
    if roots is None:
        home = Path.home()
        roots = [home / "Watchtower", home]
    seen, found = set(), []
    for root in roots:
        try:
            candidates = list(Path(root).glob(f"*/{_LEGACY_VAULT_DIRNAME}/{DB_FILENAME}"))
            candidates += list(Path(root).glob(f"*/*/{_LEGACY_VAULT_DIRNAME}/{DB_FILENAME}"))
            candidates += list(Path(root).glob(f"*/{DB_FILENAME}"))
        except OSError:
            continue
        for path in candidates:
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved in seen or resolved.parent == canonical:
                continue
            seen.add(resolved)
            found.append(resolved)
    return sorted(found)


# Live Probe-Chain Discovery (Rule 0.2: probe, don't trust)
# Deterministic resolution above says where the store SHOULD be; it cannot say
# whether anything is actually there. Measured 2026-08-15: a moved vault left
# the env var aimed at the old, EMPTY store, and get_secret's silent None read
# exactly like "never ingested" -- three provider lanes were burned diagnosing
# credentials that sat safely in another store the whole time. The probe chain
# below checks every candidate LIVE (exists, opens read-only, holds >0 secrets
# rows) so that "wrong store" and "never ingested" become distinguishable, and
# a divergence fails loud instead of None.
ENV_VAULT_PROBE = "NOUGEN_VAULT_PROBE"          # "0" disables discovery (tests)
ENV_VAULT_DIVERGENCE = "NOUGEN_VAULT_DIVERGENCE"  # warn (default) | error | adopt
_DIVERGENCE_MODES = ("warn", "error", "adopt")


class VaultDivergenceError(RuntimeError):
    """A requested key lives in a live store other than the active one."""


def _probe_enabled() -> bool:
    return os.getenv(ENV_VAULT_PROBE, "1").strip() != "0"


def _divergence_mode() -> str:
    mode = os.getenv(ENV_VAULT_DIVERGENCE, "warn").strip().lower() or "warn"
    if mode not in _DIVERGENCE_MODES:
        logger.warning("%s=%r is not one of %s; using 'warn'.",
                       ENV_VAULT_DIVERGENCE, mode, "|".join(_DIVERGENCE_MODES))
        mode = "warn"
    return mode


def _probe_store(db_path: Path) -> Optional[dict]:
    """Live-probes one candidate store, strictly read-only.

    A store is LIVE only if the file exists, opens as SQLite, and its
    `secrets` table holds at least one row -- an initialized-but-empty store
    is dead for discovery purposes, because falling back past it is exactly
    what rescues the moved-vault scenario. Returns the probe evidence
    (path, row count, newest rotation) or None.
    """
    try:
        if not db_path.is_file():
            return None
        conn = sqlite3.connect(str(db_path.resolve()), timeout=5.0)
        try:
            count, newest = conn.execute(
                "SELECT COUNT(*), MAX(last_rotated) FROM secrets").fetchone()
        finally:
            conn.close()
    except (sqlite3.Error, OSError, ValueError):
        return None
    if not count:
        return None
    return {"path": db_path.resolve(), "rows": int(count), "newest_rotation": newest}


def candidate_stores() -> list:
    """Every location this deployment might keep the secrets DB, in trust
    order: explicit env, then the user-anchored convention, then legacy
    strays surfaced by find_legacy_stores(). Deduplicated, order-preserving."""
    ordered = []
    explicit = os.getenv(ENV_SECRETS_VAULT, "").strip()
    if explicit:
        ordered.append(Path(explicit) / DB_FILENAME)
    ordered.append(Path.home() / ".nougen" / "secrets" / DB_FILENAME)
    ordered.extend(find_legacy_stores())
    seen, out = set(), []
    for path in ordered:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(path)
    return out


# One probe sweep per resolution context, so the filesystem walk in
# find_legacy_stores runs once per process, not once per get_secret call.
_PROBE_CACHE: dict = {}


def resolve_secrets_store(refresh: bool = False) -> dict:
    """Probes the candidate chain and returns the discovery evidence:

        {"active": Path,          # the store reads are pinned to
         "active_probe": dict|None,  # its probe result (None = dead/empty)
         "live": [dict, ...],     # every live candidate, in trust order
         "candidates": [Path, ...]}

    The ACTIVE store is the env-configured one whenever the env var is set --
    even if it probes dead -- because env intent matters: values are never
    silently served from a store the operator did not point at (divergence
    handling in get_secret decides what happens then). With no env var, the
    first live candidate wins; with nothing live anywhere, the deterministic
    default stands and the emptiness is logged loudly.
    """
    env_value = os.getenv(ENV_SECRETS_VAULT, "").strip()
    cache_key = (env_value, str(Path.home()))
    if not refresh and cache_key in _PROBE_CACHE:
        return _PROBE_CACHE[cache_key]

    fast_candidates = []
    if env_value:
        fast_candidates.append(Path(env_value) / DB_FILENAME)
    fast_candidates.append(Path.home() / "Watchtower" / "agent_secrets.db")
    fast_candidates.append(Path.home() / ".nougen" / "secrets" / DB_FILENAME)
    live = [probe for probe in (_probe_store(c) for c in fast_candidates) if probe]
    if live:
        candidates = fast_candidates
    else:
        candidates = candidate_stores()
        live = [probe for probe in (_probe_store(c) for c in candidates) if probe]

    if env_value:
        active = Path(env_value) / DB_FILENAME
    elif live:
        active = live[0]["path"]
    else:
        active = resolve_secrets_vault_dir() / DB_FILENAME
    try:
        active_resolved = active.resolve()
    except OSError:
        active_resolved = active
    active_probe = next((p for p in live if p["path"] == active_resolved), None)

    # Log the choice exactly once per resolution context.
    if active_probe is not None:
        preferred = candidates[0] if candidates else active
        if preferred.resolve() != active_probe["path"]:
            logger.warning(
                "Preferred secrets store %s is dead or empty; probe chain "
                "selected live store %s (%d rows, newest rotation %s). "
                "Set %s to make this explicit, or consolidate the vaults.",
                preferred, active_probe["path"], active_probe["rows"],
                active_probe["newest_rotation"], ENV_SECRETS_VAULT)
        else:
            logger.info("Keymaker secrets store: %s (%d rows, newest rotation %s)",
                        active_probe["path"], active_probe["rows"],
                        active_probe["newest_rotation"])
    elif live:
        logger.warning(
            "%s points at a dead or empty secrets store (%s), but a live store "
            "exists at %s (%d rows, newest rotation %s). Reads stay pinned to "
            "the configured store; fix %s or consolidate the vaults. "
            "(%s=warn|error|adopt governs per-key divergence.)",
            ENV_SECRETS_VAULT if env_value else "Resolution", active.parent,
            live[0]["path"], live[0]["rows"], live[0]["newest_rotation"],
            ENV_SECRETS_VAULT, ENV_VAULT_DIVERGENCE)
    else:
        logger.warning(
            "No live secrets store found anywhere. Probed: %s. A missing key "
            "here means 'no store', not 'never ingested'.",
            ", ".join(str(c) for c in candidates) or "(no candidates)")

    result = {"active": active, "active_probe": active_probe,
              "live": live, "candidates": candidates}
    _PROBE_CACHE[cache_key] = result
    return result


VAULT_DIR = resolve_secrets_vault_dir()
DB_PATH = VAULT_DIR / DB_FILENAME
CSV_PATH = VAULT_DIR / "shards_secrets.csv"
SECRETS_JSON_DIR = VAULT_DIR / "service_accounts"


def init_vault():
    """Initializes the vault database schema."""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    SECRETS_JSON_DIR.mkdir(parents=True, exist_ok=True)
    # Restrict the vault to the owner on POSIX (Windows relies on per-file ACLs).
    if os.name != "nt":
        for d in (VAULT_DIR, SECRETS_JSON_DIR):
            try:
                os.chmod(d, 0o700)
            except OSError:
                pass

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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS local_vaults (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            table_name TEXT NOT NULL,
            title_col TEXT NOT NULL,
            content_col TEXT NOT NULL,
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
                fp = _fingerprint(stored)
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


def register_local_vault(path: str, table_name: str, title_col: str, content_col: str):
    """Register a local SQLite vault as a federated read source.

    Deliberately NOT the external_dbs table. That path exists for *network*
    databases and its connector rejects sqlite/file URIs on purpose, as an SSRF
    guard — an attacker-influenced external-DB row must never be able to make the
    process open a local file. Local vaults are a different trust class: operator
    -chosen paths on this machine, read-only, no credentials in the connection
    string. Keeping them in their own table means adding them never widens what
    a compromised external_dbs row can reach.

    The path is stored in the clear (unlike external URIs, it carries no
    credentials) but is re-validated at query time, so moving or deleting a vault
    degrades that source instead of breaking federation.
    """
    init_vault()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute('''
        CREATE TABLE IF NOT EXISTS local_vaults (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            table_name TEXT NOT NULL,
            title_col TEXT NOT NULL,
            content_col TEXT NOT NULL,
            registered_at TEXT
        )
    ''')
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Re-registering the same vault updates it rather than erroring, so the
    # register step is safe to re-run after a schema change.
    conn.execute('''
        INSERT INTO local_vaults (path, table_name, title_col, content_col, registered_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            table_name=excluded.table_name,
            title_col=excluded.title_col,
            content_col=excluded.content_col,
            registered_at=excluded.registered_at
    ''', (str(path), table_name, title_col, content_col, timestamp))
    conn.commit()
    conn.close()


def list_local_vaults() -> list:
    """Registered local SQLite vaults. Missing table or DB means none."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM local_vaults").fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


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


def _read_secret_row(db_path: Path, key: str) -> Optional[str]:
    """Fetches one key from one store, strictly read-only; None on any failure."""
    try:
        if not db_path.is_file():
            return None
        conn = sqlite3.connect(str(db_path.resolve()), timeout=5.0)
        try:
            row = conn.execute(
                "SELECT secret_value FROM secrets WHERE secret_key = ?",
                (key,)).fetchone()
        finally:
            conn.close()
        return _unprotect(str(row[0])) if row else None
    except (sqlite3.Error, OSError, ValueError):
        return None


def get_secret(key: str) -> Optional[str]:
    """Retrieves a secret value by key, via probe-chain discovery.

    Reads are pinned to the ACTIVE store from resolve_secrets_store(). When
    the key is absent there but PRESENT in another live store, the vaults
    have diverged -- the answer is not a silent None (which reads exactly
    like "never ingested") but whatever NOUGEN_VAULT_DIVERGENCE dictates:

        warn  (default) -> log the divergence loudly, return None
        error           -> raise VaultDivergenceError
        adopt           -> return the value, READ-ONLY: nothing is ever
                           written to any store by adoption

    With NOUGEN_VAULT_PROBE=0 discovery is off and this reads exactly one
    deterministic location (the hermetic-test mode).
    """
    if not _probe_enabled():
        return _read_secret_row(DB_PATH, key)

    resolution = resolve_secrets_store()
    value = _read_secret_row(resolution["active"], key)
    if value is not None:
        return value

    # Absent from the active store: check the other live candidates before
    # concluding "never ingested" (the moved-vault trap, measured 2026-08-15).
    try:
        active_resolved = resolution["active"].resolve()
    except OSError:
        active_resolved = resolution["active"]
    for other in resolution["live"]:
        if other["path"] == active_resolved:
            continue
        found = _read_secret_row(other["path"], key)
        if found is None:
            continue
        mode = _divergence_mode()
        msg = (f"Secret '{key}' is absent from the active store "
               f"({resolution['active']}) but exists in {other['path']} -- the "
               f"vault stores have diverged. Set {ENV_SECRETS_VAULT} to the "
               f"store that holds your secrets, or consolidate them. "
               f"({ENV_VAULT_DIVERGENCE}=warn|error|adopt; current: {mode}.)")
        if mode == "error":
            raise VaultDivergenceError(msg)
        if mode == "adopt":
            logger.warning("%s Adopting the value READ-ONLY from %s for this "
                           "call; no store is modified.", msg, other["path"])
            return found
        logger.warning(msg)
        return None
    return None


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
        return migrated
    finally:
        conn.close()
def _run_gcloud_cmd(args: list[str]) -> Optional[str]:
    import subprocess
    cmd_str = "gcloud " + " ".join(args)
    for runner in (
        ["cmd.exe", "/c", cmd_str],
        ["powershell.exe", "-NoProfile", "-Command", cmd_str],
    ):
        try:
            res = subprocess.run(runner, capture_output=True, text=True, timeout=20, shell=False)
            out = res.stdout.strip()
            if out and not out.startswith("ERROR:") and not out.startswith("WARNING:"):
                # Handle possible trailing warnings or multilines
                for line in out.splitlines():
                    clean = line.strip()
                    if clean and not clean.startswith("WARNING:") and not clean.startswith("ERROR:"):
                        return clean
                return out
        except Exception:
            continue
    return None


def get_gcloud_token(auto_ingest: bool = True, force_refresh: bool = False) -> Optional[str]:
    """Resolves active Google Cloud access token, auto-refreshes if older than 45m or on force_refresh, encrypts into Keymaker vault."""
    env_tok = os.getenv("VERTEX_BEARER_TOKEN") or os.getenv("VERTEX_ACCESS_TOKEN") or os.getenv("GCP_ACCESS_TOKEN")
    if env_tok and env_tok.startswith("ya29.") and not force_refresh:
        if auto_ingest:
            try:
                ingest_secret("GCP_ACCESS_TOKEN", env_tok.strip())
            except Exception:
                pass
        return env_tok.strip()

    if not force_refresh:
        resolution = resolve_secrets_store()
        try:
            conn = sqlite3.connect(str(resolution["active"].resolve()), timeout=5.0)
            row = conn.execute("SELECT secret_value, last_rotated FROM secrets WHERE secret_key = 'GCP_ACCESS_TOKEN'").fetchone()
            conn.close()
            if row:
                stored_val, last_rotated = row
                try:
                    rotated_dt = datetime.strptime(last_rotated, "%Y-%m-%d %H:%M:%S")
                    age_seconds = (datetime.now() - rotated_dt).total_seconds()
                except Exception:
                    age_seconds = 9999
                # OAuth tokens expire at 60 minutes; if under 45 minutes, reuse cached
                if age_seconds < 2700:
                    val = _unprotect(str(stored_val))
                    if val and val.startswith("ya29."):
                        return val
        except Exception:
            pass

    tok = _run_gcloud_cmd(["auth", "print-access-token"])
    if tok and tok.startswith("ya29."):
        if auto_ingest:
            try:
                ingest_secret("GCP_ACCESS_TOKEN", tok)
            except Exception:
                pass
        return tok
    return None


def get_active_gcp_project(auto_ingest: bool = True) -> Optional[str]:
    """Resolves active Google Cloud project ID from env, vault, or gcloud CLI."""
    env_proj = os.getenv("NOUGENSTYLE_VERTEX_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
    if env_proj and env_proj != "(unset)":
        if auto_ingest:
            try:
                ingest_secret("GCP_PROJECT_ID", env_proj.strip())
            except Exception:
                pass
        return env_proj.strip()

    cached = get_secret("GCP_PROJECT_ID")
    if cached and cached != "(unset)":
        return cached

    proj = _run_gcloud_cmd(["config", "get-value", "project"])
    if proj and proj != "(unset)":
        if auto_ingest:
            try:
                ingest_secret("GCP_PROJECT_ID", proj)
            except Exception:
                pass
        return proj
    return None


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

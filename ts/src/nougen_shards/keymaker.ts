/**
 * Keymaker Agent: Secure Secret Ingestion & Management (TS mimic of keymaker.py)
 * Mimics the 'Atibon' workflow for the NouGenAi franchise.
 */
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import * as path from "node:path";
import { createDatabase } from "./_db.js";

// Marker prefix for values encrypted at rest via Windows DPAPI (user-bound).
const _DPAPI_PREFIX = "dpapi1:";
// Marker prefix for values stored in the OS keyring (macOS Keychain / Secret Service).
const _KEYRING_PREFIX = "keyring1:";

/** True if the stored value is protected (DPAPI or keyring), not legacy plaintext. */
function _is_encrypted(stored: string): boolean {
  return String(stored).startsWith(_DPAPI_PREFIX) || String(stored).startsWith(_KEYRING_PREFIX);
}

/**
 * Invokes Windows DPAPI (CryptProtectData/CryptUnprotectData) via PowerShell's
 * System.Security.Cryptography.ProtectedData (the ctypes-free Node equivalent).
 * Input is passed through an environment variable to avoid shell injection.
 */
function _dpapi_call(mode: "protect" | "unprotect", data_b64: string): string {
  const script =
    mode === "protect"
      ? "Add-Type -AssemblyName System.Security; " +
        "[Convert]::ToBase64String([Security.Cryptography.ProtectedData]::Protect(" +
        "[Convert]::FromBase64String($env:NGS_DPAPI_IN), $null, 'CurrentUser'))"
      : "Add-Type -AssemblyName System.Security; " +
        "[Convert]::ToBase64String([Security.Cryptography.ProtectedData]::Unprotect(" +
        "[Convert]::FromBase64String($env:NGS_DPAPI_IN), $null, 'CurrentUser'))";
  const out = execFileSync("powershell", ["-NoProfile", "-NonInteractive", "-Command", script], {
    env: { ...process.env, NGS_DPAPI_IN: data_b64 },
    encoding: "utf-8",
  });
  return out.trim();
}

/**
 * Encrypts a secret value at rest. Fails closed: never stores plaintext silently.
 *
 * Windows  -> DPAPI (user-bound).
 * Other OS -> no keyring backend is bundled with the TS port; refuse unless
 *             NOUGEN_ALLOW_PLAINTEXT_VAULT=1 (mirrors the Python ImportError path).
 */
function _protect(value: string, _key: string | null = null): string {
  if (process.platform === "win32") {
    const encrypted_b64 = _dpapi_call("protect", Buffer.from(value, "utf-8").toString("base64"));
    return _DPAPI_PREFIX + encrypted_b64;
  }

  if (process.env.NOUGEN_ALLOW_PLAINTEXT_VAULT === "1") {
    return value;
  }
  throw new Error(
    "No OS keyring backend available on this platform. " +
      "Set NOUGEN_ALLOW_PLAINTEXT_VAULT=1 to override (not recommended).",
  );
}

/** Decrypts a stored value; passes through legacy plaintext rows untouched. */
function _unprotect(stored: string): string {
  if (stored.startsWith(_DPAPI_PREFIX)) {
    const raw_b64 = stored.slice(_DPAPI_PREFIX.length);
    const plain_b64 = _dpapi_call("unprotect", raw_b64);
    return Buffer.from(plain_b64, "base64").toString("utf-8");
  }
  if (stored.startsWith(_KEYRING_PREFIX)) {
    // Keyring rows were written by the Python vault; the TS port cannot read them.
    throw new Error(`Keyring entry '${stored.slice(_KEYRING_PREFIX.length)}' not readable from the TS port.`);
  }
  return stored; // legacy plaintext row (pre-encryption migration)
}

/** Non-reversible audit fingerprint of a secret (first 12 hex of SHA-256). */
function _fingerprint(value: string): string {
  return createHash("sha256").update(value, "utf-8").digest("hex").slice(0, 12);
}

// Portable Vault Resolution
export const VAULT_DIR = process.env.NOUGEN_VAULT_DIR ?? ".nougen_vault";
export const DB_PATH = path.join(VAULT_DIR, "shards_secrets.db");
export const CSV_PATH = path.join(VAULT_DIR, "shards_secrets.csv");
export const SECRETS_JSON_DIR = path.join(VAULT_DIR, "service_accounts");

/** Initializes the vault database schema. */
export function init_vault(): void {
  mkdirSync(VAULT_DIR, { recursive: true });
  mkdirSync(SECRETS_JSON_DIR, { recursive: true });

  const conn = createDatabase(DB_PATH);
  conn.exec(`
        CREATE TABLE IF NOT EXISTS secrets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            secret_key TEXT UNIQUE NOT NULL,
            secret_value TEXT NOT NULL,
            last_rotated TEXT NOT NULL
        )
    `);
  conn.exec(`
        CREATE TABLE IF NOT EXISTS external_dbs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uri TEXT NOT NULL,
            table_name TEXT NOT NULL,
            title_col TEXT NOT NULL,
            content_col TEXT NOT NULL,
            last_connected TEXT NOT NULL
        )
    `);
  conn.exec(`
        CREATE TABLE IF NOT EXISTS cloud_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            last_connected TEXT NOT NULL
        )
    `);
  conn.close();
}

function _csv_escape(field: string): string {
  if (/[",\n\r]/.test(field)) {
    return `"${field.replace(/"/g, '""')}"`;
  }
  return field;
}

/** Exports a metadata-only audit ledger. NEVER writes secret values to disk. */
function _export_to_csv(): void {
  const conn = createDatabase(DB_PATH);
  try {
    const rows = conn.prepare("SELECT id, secret_key, secret_value, last_rotated FROM secrets").all() as Record<
      string,
      any
    >[];
    const lines = ["id,secret_key,fingerprint_sha256_12,encrypted,last_rotated"];
    for (const row of rows) {
      let fp: string;
      try {
        fp = _fingerprint(_unprotect(String(row.secret_value)));
      } catch {
        fp = "unreadable";
      }
      lines.push(
        [
          String(row.id),
          _csv_escape(String(row.secret_key)),
          fp,
          _is_encrypted(String(row.secret_value)) ? "True" : "False",
          _csv_escape(String(row.last_rotated)),
        ].join(","),
      );
    }
    writeFileSync(CSV_PATH, lines.join("\r\n") + "\r\n", "utf-8");
  } catch {
    /* mirror sqlite3.Error pass */
  } finally {
    conn.close();
  }
}

function _now_stamp(): string {
  // Python strftime('%Y-%m-%d %H:%M:%S') mimic, local time.
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/**
 * Ingests a secret into the DB, exports to CSV, and redacts output.
 */
export function ingest_secret(key: string, value: string): void {
  init_vault();
  const timestamp = _now_stamp();
  const conn = createDatabase(DB_PATH);
  try {
    conn
      .prepare(`
            INSERT OR REPLACE INTO secrets (secret_key, secret_value, last_rotated)
            VALUES (?, ?, ?)
        `)
      .run(key, _protect(value, key), timestamp);
    console.log(`  [+] Ingested: ${key} (Value Redacted)`);
    _export_to_csv();
  } catch (exc) {
    console.log(`  [!] Error ingesting ${key}: ${exc}`);
  } finally {
    conn.close();
  }
}

/**
 * Ingests a Google Service Account JSON, saves to file, and stores project metadata.
 */
export function ingest_service_account(json_data: string): void {
  try {
    const data = JSON.parse(json_data);
    const project_id: string = data.project_id ?? "unknown_project";
    const client_email: string = data.client_email ?? "unknown_email";

    const file_name = `${project_id}_service_account.json`;
    const target_path = path.join(SECRETS_JSON_DIR, file_name);

    mkdirSync(SECRETS_JSON_DIR, { recursive: true });
    writeFileSync(target_path, JSON.stringify(data, null, 2), "utf-8");

    // Lock file ACL to the current user only (constitution 0.2 rule 3)
    if (process.platform === "win32") {
      const user = process.env.USERNAME ?? "";
      if (user) {
        try {
          execFileSync("icacls", [target_path, "/inheritance:r", "/grant:r", `${user}:F`], {
            stdio: "ignore",
          });
        } catch {
          /* check=False mimic */
        }
      }
    }

    // Store metadata in DB
    ingest_secret(`GCP_SA_${project_id.toUpperCase()}`, client_email);
    console.log(`  [+] Service Account for ${project_id} stored at ${target_path}`);
  } catch (exc) {
    console.log(`  [!] Error ingesting service account: ${exc}`);
  }
}

/** Registers a new external database connection. */
export function register_external_db(uri: string, table_name: string, title_col: string, content_col: string): void {
  init_vault();
  const conn = createDatabase(DB_PATH);
  const timestamp = _now_stamp();
  conn
    .prepare(`
        INSERT INTO external_dbs (uri, table_name, title_col, content_col, last_connected)
        VALUES (?, ?, ?, ?, ?)
    `)
    .run(uri, table_name, title_col, content_col, timestamp);
  conn.close();
}

/** Returns all registered external database configurations. */
export function list_external_dbs(): Record<string, any>[] {
  if (!existsSync(DB_PATH)) {
    return [];
  }
  const conn = createDatabase(DB_PATH);
  try {
    return (conn.prepare("SELECT * FROM external_dbs").all() as Record<string, any>[]).map((r) => ({ ...r }));
  } catch {
    return [];
  } finally {
    conn.close();
  }
}

/** Registers a new remote NouGenShards cloud node. */
export function register_cloud_node(url: string, name: string): void {
  init_vault();
  const conn = createDatabase(DB_PATH);
  const timestamp = _now_stamp();
  conn
    .prepare(`
        INSERT OR REPLACE INTO cloud_nodes (url, name, last_connected)
        VALUES (?, ?, ?)
    `)
    .run(url, name, timestamp);
  conn.close();
}

/** Returns all registered cloud node configurations. */
export function list_cloud_nodes(): Record<string, any>[] {
  if (!existsSync(DB_PATH)) {
    return [];
  }
  const conn = createDatabase(DB_PATH);
  try {
    return (conn.prepare("SELECT * FROM cloud_nodes").all() as Record<string, any>[]).map((r) => ({ ...r }));
  } catch {
    return [];
  } finally {
    conn.close();
  }
}

/** Retrieves a secret value from the DB by its key. */
export function get_secret(key: string): string | null {
  if (!existsSync(DB_PATH)) {
    return null;
  }
  const conn = createDatabase(DB_PATH);
  try {
    const row = conn.prepare("SELECT secret_value FROM secrets WHERE secret_key = ?").get(key) as
      | Record<string, any>
      | undefined;
    return row ? _unprotect(String(row.secret_value)) : null;
  } catch {
    return null;
  } finally {
    conn.close();
  }
}

/** Returns a list of keys currently stored in the vault. */
export function list_providers(): string[] {
  if (!existsSync(DB_PATH)) {
    return [];
  }
  const conn = createDatabase(DB_PATH);
  try {
    return (conn.prepare("SELECT secret_key FROM secrets").all() as Record<string, any>[]).map((r) =>
      String(r.secret_key),
    );
  } catch {
    return [];
  } finally {
    conn.close();
  }
}

/** Re-encrypts any legacy plaintext rows in place. Returns count migrated. */
export function migrate_to_encrypted(): number {
  if (!existsSync(DB_PATH)) {
    return 0;
  }
  const conn = createDatabase(DB_PATH);
  let migrated = 0;
  try {
    const rows = conn.prepare("SELECT secret_key, secret_value FROM secrets").all() as Record<string, any>[];
    for (const row of rows) {
      const stored = String(row.secret_value);
      if (!_is_encrypted(stored)) {
        conn
          .prepare("UPDATE secrets SET secret_value = ? WHERE secret_key = ?")
          .run(_protect(stored, String(row.secret_key)), String(row.secret_key));
        migrated += 1;
      }
    }
  } finally {
    conn.close();
  }
  if (migrated) {
    _export_to_csv();
  }
  return migrated;
}

// __main__ mimic: node dist/nougen_shards/keymaker.js init | add <key> <value> | sa <json> | migrate
import { pathToFileURL } from "node:url";
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const argv = process.argv.slice(2);
  if (argv.length < 1) {
    console.log("Usage: node keymaker.js init | add <key> <value> | sa <json_content> | migrate");
    process.exit(1);
  }

  const CMD = argv[0];
  if (CMD === "migrate") {
    const COUNT = migrate_to_encrypted();
    console.log(`[*] Migrated ${COUNT} legacy plaintext secrets to DPAPI encryption.`);
  } else if (CMD === "init") {
    init_vault();
    console.log(`[*] Keymaker initialized at ${path.resolve(VAULT_DIR)}`);
  } else if (CMD === "add" && argv.length === 3) {
    ingest_secret(argv[1], argv[2]);
  } else if (CMD === "sa" && argv.length === 2) {
    ingest_service_account(argv[1]);
  } else {
    console.log("Invalid command or arguments.");
  }
}

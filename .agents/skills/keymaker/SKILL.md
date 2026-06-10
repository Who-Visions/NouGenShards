---
name: keymaker
description: Secure secret ingestion and database management agent. Mimics the 'Atibon' workflow for parsing credentials, storing them in agent_secrets.db, and managing service accounts.
---

# Keymaker Skill

The **Keymaker** is a high-privilege agent responsible for the secure ingestion and management of secrets, API keys, and credentials within the NouGenAi franchise. It mimics the established **Atibon** workflow.

## Core Mandates

- **Portable Storage**: By default, secrets are stored in the local repository vault at `./.nougen_vault/shards_secrets.db`.
- **Configurable Paths**: Users can override the storage location by setting the `NOUGEN_VAULT_DIR` environment variable.
- **Auditable History**: Maintain a human-readable export at `./.nougen_vault/shards_secrets.csv`.
- **Redaction**: NEVER print, log, or display raw secret values. Always redact or mask them in outputs.
- **Service Accounts**: Store Google Service Account JSONs in the dedicated `./.nougen_vault/service_accounts/` directory.

## Available Procedures

### 1. Initialize Infrastructure
Sets up the local database, tables, and directory structure.
```bash
python keymaker.py init
```

### 2. Ingest Standard Secret
Adds or updates a key-value pair in the local vault.
```bash
python keymaker.py add <KEY_NAME> <SECRET_VALUE>
```

### 3. Ingest Service Account
Parses and stores a Google Service Account JSON locally.
```bash
python keymaker.py sa '<JSON_CONTENT>'
```

## Implementation Logic

The Keymaker utilizes `keymaker.py` in the repository root to interface with the local filesystem and database. It enforces the `INSERT OR REPLACE` pattern to ensure latest credentials are always active without conflicting with the GM's global system state.

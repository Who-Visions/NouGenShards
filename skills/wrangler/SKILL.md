---
name: wrangler
description: Comprehensive Cloudflare Workers & Wrangler CLI operational skill. Guides development, bundling (esbuild), configuration (wrangler.jsonc / wrangler.toml), environment bindings, secret management, non-interactive CI/CD deployments, and direct Cloudflare REST API fallback deployment recipes.
---

# ⛅ Cloudflare Wrangler & Workers Mastery Skill

This skill provides exhaustive guidance, canonical commands, configuration architectures, and zero-downtime deployment patterns for Cloudflare Workers, Cloudflare Pages, and the Wrangler CLI toolchain.

---

## 1. Core Architectural Pillars

1. **Configuration Precedence**:
   - Modern Cloudflare Workers prefer **`wrangler.jsonc`** over legacy `wrangler.toml`.
   - `wrangler.jsonc` supports standard JSON with comments and trailing commas.
   - Entry point is designated via `"main": "src/worker.js"` (or `"src/index.ts"`).

2. **Authentication Modes**:
   - **Interactive Dev**: `npx wrangler login` (opens OAuth consent screen).
   - **Headless / CI / Fleet**: Export `CLOUDFLARE_API_TOKEN` and optionally `CLOUDFLARE_ACCOUNT_ID`.
   - **Direct REST API Fallback**: When Wrangler cannot prompt or is missing dependencies, upload worker modules directly via `PUT /accounts/{account_id}/workers/scripts/{script_name}/content` (as demonstrated in `deploy.py`).

---

## 2. Canonical Wrangler Commands

### Project Initialization & Local Dev
```powershell
# Run local dev server with edge simulation (Miniflare)
npx wrangler dev

# Run dev server on specific port with local persistent storage
npx wrangler dev --port 8787 --persist-to .wrangler/state

# Stream live real-time production logs
npx wrangler tail [WORKER_NAME]
```

### Deployment & Environments
```powershell
# Deploy to production (default environment)
npx wrangler deploy

# Deploy to specific named environment (e.g., staging, canary)
npx wrangler deploy --env staging

# Dry-run validation (checks bundle, syntax, bindings without uploading)
npx wrangler deploy --dry-run
```

### Secrets & Environment Variables
```powershell
# Interactive secret storage (encrypted at edge, never exposed in source)
npx wrangler secret put SECRET_NAME

# Bulk upload secrets from .env file
npx wrangler secret:bulk .env.production

# List secret names (never returns secret values)
npx wrangler secret list

# Delete a secret
npx wrangler secret delete SECRET_NAME
```

### Cloudflare Storage Bindings (KV, D1, R2, Vectorize)
```powershell
# KV Namespaces
npx wrangler kv:namespace create CACHE_KV
npx wrangler kv:key put --binding=CACHE_KV "user:123" "data"

# D1 Serverless SQL Databases
npx wrangler d1 create fleet_db
npx wrangler d1 execute fleet_db --command "SELECT * FROM users"
npx wrangler d1 execute fleet_db --file=./schema.sql

# R2 Object Storage Buckets
npx wrangler r2 bucket create fleet-assets

# Vectorize Vector Databases
npx wrangler vectorize create fleet-index --dimensions=768 --metric=cosine
```

---

## 3. Configuration Reference (`wrangler.jsonc`)

```jsonc
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "my-worker",
  "main": "src/worker.js",
  "compatibility_date": "2026-08-01",
  "compatibility_flags": [
    "nodejs_compat"
  ],
  "vars": {
    "ENVIRONMENT": "production",
    "API_HOST": "https://api.domain.com"
  },
  "kv_namespaces": [
    {
      "binding": "KV_CACHE",
      "id": "xxxxxx",
      "preview_id": "yyyyyy"
    }
  ],
  "d1_databases": [
    {
      "binding": "DB",
      "database_name": "fleet_db",
      "database_id": "zzzzzz"
    }
  ],
  "r2_buckets": [
    {
      "binding": "ASSETS",
      "bucket_name": "fleet-assets"
    }
  ],
  "env": {
    "staging": {
      "vars": {
        "ENVIRONMENT": "staging"
      }
    }
  }
}
```

---

---

## 4. Native NouGen Cloudflare Edge Engine (`nougen cf` & `cf`)

NouGen provides a first-class, zero-VRAM, context-intelligent Cloudflare management engine built directly into `nougen_shards.cloudflare`:

### Global CLI Commands
The `cf` command is globally available on any terminal or PowerShell prompt:
```powershell
# Check edge account, deployed workers, storage, and local directory context
cf status

# List all active workers in orbit with modification dates and routes
cf list

# Inspect local directory for worker config, entrypoint, bindings, and live status
cf inspect [path]

# Zero-config auto-deploy: detects wrangler.jsonc/toml, runs node --check, publishes
cf deploy [path] [--name <worker_name>]

# Verify API token, API latency, and fleet MCP gateway status
cf ping

# Manage edge secrets
cf secrets <worker_name>
cf secret-set <worker_name> <key> <value>

# Intelligently sync secrets from Keymaker DPAPI vault to worker
cf sync-secrets <worker_name>

# Execute zero-VRAM Workers AI edge inference
cf ai run "Explain the NouGen fleet architecture"
cf ai models
cf ai embed "NouGen memory substrate vector"

# Query D1 and storage
cf d1 list
cf d1 query <database_name> "SELECT * FROM users LIMIT 10"
cf kv list
cf r2
```

### Python SDK Integration
Any agent or script can access the substrate natively:
```python
from nougen_shards.cloudflare import CloudflareClient

cf = CloudflareClient()  # Auto-discovers token from Keymaker DPAPI vault
workers = cf.list_workers()
result = cf.auto_deploy(Path.cwd())
response = cf.run_ai("Hello from NouGen")
```

---

## 5. Headless REST API Direct Deployment Pattern (Fleet Recipe)

When running inside headless agent loops where `npx wrangler login` cannot open interactive browsers, deploy directly via Cloudflare's v4 REST API using `CLOUDFLARE_API_TOKEN_NOUGEN_FULL` stored in Keymaker:

```python
import json
import urllib.request
from pathlib import Path
from nougen_shards import keymaker

token = keymaker.get_secret("CLOUDFLARE_API_TOKEN_NOUGEN_FULL")
worker_code = Path("src/worker.js").read_bytes()

boundary = "----WebKitFormBoundaryFleetDeploy"
metadata = json.dumps({"main_module": "worker.js"}).encode("utf-8")

body = bytearray()
body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"metadata\"\r\nContent-Type: application/json\r\n\r\n".encode())
body.extend(metadata)
body.extend(b"\r\n")
body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"worker.js\"; filename=\"worker.js\"\r\nContent-Type: application/javascript+module\r\n\r\n".encode())
body.extend(worker_code)
body.extend(f"\r\n--{boundary}--\r\n".encode())

req = urllib.request.Request(
    f"https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts/{script_name}/content",
    data=body,
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    },
    method="PUT",
)
```

---

## 6. Troubleshooting & Guardrails

- **Error: `UV_HANDLE_CLOSING` / Node crash**: Occurs when interactive Wrangler processes exit abruptly on Windows without closing UV handles. Use `cf deploy` or direct REST API deploy.
- **Error: `CLOUDFLARE_API_TOKEN` missing**: Stored securely in Keymaker as `CLOUDFLARE_API_TOKEN_NOUGEN_FULL`. Set via `nougen auth set-key cf <token>`.
- **Error: `entry-point file not found`**: Ensure `main` in `wrangler.jsonc` matches your actual directory layout (e.g. `src/worker.js` vs `worker.js`). Run `cf inspect` to check paths.


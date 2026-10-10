# NouGenShards Distribution Boundary Map

**Authority Root**: `C:\Users\super\.nougen`  
**Substrate**: NouGenShards 9-DB SQLite Grid (`nougen_shards_1.db` through `nougen_shards_9.db`)  
**Publisher**: Who Visions LLC (`contact@whovisions.com`)  
**License Tier**: Source-Available / Proprietary Core ([licensing.md](file:///C:/Users/super/Outpost/NouGen-rsi-ledger/docs/licensing.md))

---

## 1. Architectural Distribution Boundaries

```
+-------------------------------------------------------------------------------+
|                       Who Visions Cloud / Network Services                     |
|  - Hosted Inference Gateway (whovisions_cloud provider)                       |
|  - Remote Managed Sync Nodes & Multi-Tenant Relay                             |
|  - Commercial Rights & Enterprise Subscriptions                               |
+-------------------------------------------------------------------------------+
                                    ^
                           Network Boundary (TLS / BYOK)
                                    v
+-------------------------------------------------------------------------------+
|                    NouGen Local Engine (Source-Available)                     |
|  - 9-DB Local SQLite Grid (C:\Users\super\.nougen\nougen_shards_*.db)          |
|  - FastMCP / Streamable HTTP Server (src/nougen_shards/mcp.py, app.py)        |
|  - Local Ollama & LM Studio Engine Adapter (gemma4:e2b-qat, Yukiai)           |
|  - AES-256-GCM Private Vault (cryptography>=50.0.0)                           |
|  - Deduplication Index, Session WAL & Pulse Bus                               |
+-------------------------------------------------------------------------------+
```

---

## 2. Dependency Classification & License Matrix

Verified against active `pyproject.toml` pins and distribution scope:

| Package | Pinned Floor | Runtime Layer | Distribution Permissibility | Notes |
|---|---|---|---|---|
| `mcp` | `>=2.0` | MCP Server / RPC | Permitted (MIT) | 2.x streamable HTTP & MCPServer protocol |
| `fastapi` | `>=0.110` | Web & IPC API | Permitted (MIT) | Core REST & streaming transports |
| `uvicorn` | `>=0.29` | ASGI Runtime | Permitted (BSD-3) | Local HTTP daemon engine |
| `sqlalchemy` | `>=2.0` | Connector | Permitted (MIT) | SQL 2.0 API connectors |
| `gradio` | `>=4.0` | Tactical Web UI | Permitted (Apache-2.0) | Optional interactive visualization |
| `cryptography` | `>=50.0.0` | Private Vault | Permitted (Apache-2.0 / BSD) | Hard floor clears CVE-2026-69247 (AES-256-GCM) |
| `ollama` | `>=0.4.0` | Model Client | Permitted (MIT) | Local GPU zero-cost inference harness |
| `openai` | `>=1.0` | Embedding Client| Permitted (Apache-2.0) | text-embedding-3-small provider |
| `pydantic` | `>=2.0` | Data Validation | Permitted (MIT) | Validation & serialization schemas |
| `numpy` | `>=1.24` | Core Vector Math | Permitted (BSD-3) | Shard math and cosine indexing |
| `z3-solver` | `>=4.12.0` | Formal Engine | Permitted (MIT) | SMT / constraint proof solving |
| `google-api-python-client` | `>=2.100` | Tool Port | Permitted (Apache-2.0) | Native Google Workspace connector |
| `google-auth` / `oauthlib` | `>=2.25` / `>=1.2` | Workspace Auth | Permitted (Apache-2.0) | Zero credentials retained externally |

---

## 3. Commercial Boundaries & Permitted Scope

1. **Free Local Usage**:
   - Infinite local shards across `nougen_shards_1.db` through `nougen_shards_9.db`.
   - Local model inference via Ollama (`Yukiai:e2b`, `solai:latest`).
   - BYOK (Bring Your Own Key) execution for direct cloud APIs without surcharge.

2. **Proprietary Who Visions Gateways**:
   - Enterprise multi-tenant sync nodes.
   - Hosted cloud proxying (`whovisions_cloud`).
   - Corporate redistribution, sublicensing, or training competing intelligence substrates.

# gogcli — scope assessment (research only, no code written)

Source: [openclaw/gogcli](https://github.com/openclaw/gogcli) (README fetched 2026-09-22, no repo clone/checkout performed).

## What it is

CLI tool **and** MCP server, written in **Go**, single binary with hierarchical subcommands. Description: *"gog is one command-line client for Gmail, Calendar, Drive, Docs, Sheets, and the wider Google Workspace surface."*

## What it does

- **Gmail**: `gog gmail search` (Gmail query syntax, e.g. `is:unread newer_than:7d`), message retrieval, `--json`/`--plain` output.
- **Calendar**: `gog calendar events`, filterable (`--today`, timeframe).
- **Drive**: `gog drive ls`, `gog drive audit sharing` (folder-level access audits).
- **Also covers**: Docs, Sheets, Slides, Forms, Contacts, Tasks, meeting management, Analytics, Search Console, Workspace admin tools.
- **Auth**: OAuth2, service accounts, Application Default Credentials; tokens stored in platform keyring (encrypted-file fallback headless).
- **MCP mode**: `gog mcp` exposes a **typed stdio MCP server**, no generic shell/command bridge, **read-only by default** — writes require explicit command and tool authorization. Schema is self-documenting via `gog schema`/`gog help`.
- **Safety posture**: read-only modes, command allowlists, policy-based restrictions; stderr for prompts/progress/warnings, stdout reserved for structured `--json`/`--plain` output.
- Distributed via Homebrew, Go module install, Docker, manual binaries.

## Overlap / dedup assessment vs existing port

NouGen already has a native Google Workspace MCP port at `src/nougen_shards/google_workspace/` (docstring: `docs/google-workspace-mcp-port.md`, currently only present on commit `f83b06d` / branch `feat/google-workspace-mcp-port` — not yet merged into `fleet/nougenmorph-elevation`'s working tree at research time). That port is:

- **Python**, ported from `taylorwilsdon/google_workspace_mcp`, built against NouGen's own `MCPServer`/`FastMCP` compat shim in `nougen_shards/mcp.py`.
- Scope: Gmail (6 tools: list/search/get/send/draft/labels), Calendar (6: list/list-events/search/create/update/delete), Drive (5: search/metadata/download/upload/create-folder) — **17 tools total**.
- Explicitly deferred: Docs, Sheets, Slides, Forms, Chat, Tasks, Contacts, Apps Script, Custom Search.
- Auth: `google-auth`/`google-auth-oauthlib` refresh-token flow, NouGen-specific env vars (`NOUGEN_GOOGLE_CLIENT_ID`/`_SECRET`/`_SECRET_FILE`/`_TOKEN_DIR`), interactive `auth mint` command.

gogcli covers substantially the **same surface** (Gmail, Calendar, Drive, plus more — Docs/Sheets/Slides/Forms/Tasks/Contacts that NouGen's port explicitly deferred) and **also ships an MCP server mode**, so at the tool-surface level it is a direct functional overlap, not a complementary piece.

Key differences:
- **Language/integration**: gogcli is a Go binary invoked as an external process; NouGen's port is native Python inside `nougen_shards`, using NouGen's own MCP compat shim, env-var conventions, and vault/token-dir conventions (`NOUGEN_VAULT_DIR` fallback chain). Adopting gogcli would mean shelling out to a foreign binary rather than importing a module — a different integration shape than the rest of `nougen_shards`.
- **Auth model**: gogcli supports service accounts and ADC in addition to OAuth2/keyring; NouGen's port is refresh-token-only via its own env vars.
- **Safety**: gogcli's read-only-default + explicit write-authorization model is arguably stronger/more auditable than NouGen's current port (which exposes write tools like `send_message`, `create_event`, `delete_event`, `upload_file` directly).
- **Breadth**: gogcli covers Docs/Sheets/Slides/Forms/Tasks/Contacts/Admin/Analytics — areas NouGen's port deliberately deferred.

## Recommendation: **skip** (do not port gogcli)

Reasons:
1. NouGen's existing `google_workspace/` module already covers the core surface (Gmail/Calendar/Drive) natively, in-process, using NouGen's own MCP conventions — a Go external-binary dependency would be a step backward in integration coherence for no gain on that surface.
2. The genuinely new surface gogcli adds (Docs, Sheets, Slides, Forms, Tasks, Contacts, Admin, Analytics) is exactly the list NouGen's port already catalogued as "deferred, not built" — if that breadth is wanted, the lower-friction path is extending the existing native Python module file-by-file (mirroring its own `gmail.py`/`calendar.py`/`drive.py` pattern), not introducing a second, differently-shaped Google integration.
3. gogcli's read-only-default/write-authorization design is worth **studying** as a pattern (see below) even though the binary itself shouldn't be adopted.

## If breadth is wanted later: what a "merge-into-existing" alternative would require

Rather than porting gogcli, extend `src/nougen_shards/google_workspace/`:
- Add `docs.py`, `sheets.py`, `slides.py`, `forms.py`, `tasks.py`, `contacts.py` following the existing file-per-service pattern, registered in `server.py` alongside the current 17 tools.
- Borrow gogcli's **read-only-by-default + explicit write-allowlist** convention for the existing write tools (`send_message`, `create_event`, `update_event`, `delete_event`, `upload_file`) — currently these appear registered without a stated read/write gate.
- Scopes would need to expand per new service (docs, sheets, forms, tasks, contacts scopes) beyond the current `gmail.*`/`calendar`/`drive.*` set.
- No new language/toolchain dependency (stays Python), no external binary, no Go build/release pipeline to maintain.

## What porting gogcli itself would require (not recommended, for completeness)

- Vendoring/building a Go binary (or depending on a Homebrew/Docker install) as an external process NouGen shells out to — a new deployment dependency the rest of `nougen_shards` doesn't have.
- A wrapper module to invoke `gog mcp` as a stdio MCP subprocess and bridge it into NouGen's fleet-MCP topology, duplicating what NouGen's native port already does for Gmail/Calendar/Drive.
- Reconciling two divergent auth/credential-storage models (gogcli's platform keyring vs NouGen's `NOUGEN_VAULT_DIR`/`NOUGEN_GOOGLE_TOKEN_DIR` env-var convention) if both were to coexist.

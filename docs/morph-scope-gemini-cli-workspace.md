# gemini-cli-extensions/workspace — scope assessment

Source: [gemini-cli-extensions/workspace](https://github.com/gemini-cli-extensions/workspace) (README, `gemini-extension.json`, `workspace-server/` tree read via `gh api` 2026-09-22 — WebFetch could not reach github.com from this session, gh CLI was used instead).

## What it is

The official **Google Workspace extension for Gemini CLI**, published by Google under the `gemini-cli-extensions` GitHub org. It is installed into Gemini CLI with `gemini extensions install https://github.com/gemini-cli-extensions/workspace` and exposes Google Workspace (Docs, Sheets, Slides, Gmail, Calendar, Drive, Chat, Tasks, People/Contacts, plus a Time helper) as MCP tools, alongside a handful of Gemini CLI slash commands (`/calendar:get-schedule`, `/drive:search`, etc.) and `skills/`.

## What it does

- Registers a single MCP server (`google-workspace`) launched via `node scripts/start.js` from the extension's own directory (`gemini-extension.json`: `"mcpServers": {"google-workspace": {"command": "node", "args": ["scripts/start.js"], "cwd": "${extensionPath}"}}`).
- `workspace-server/src/services/` implements one service class per Workspace API: `CalendarService.ts` (+`CalendarValidation.ts`), `ChatService.ts`, `DocsService.ts`, `DriveService.ts`, `GmailService.ts`, `PeopleService.ts`, `SheetsService.ts`, `SlidesService.ts`, `TasksService.ts`, `TimeService.ts` — 9 Workspace surfaces plus a time utility.
- `src/index.ts` (62,867 bytes) is the single MCP server entrypoint wiring all tools together; `src/features/` (`feature-config.ts`, `feature-resolver.ts`) does feature/tool gating; `src/auth/` handles OAuth, including a **headless/remote login path** (`npm run auth-utils -- login`) that prints an OAuth URL for out-of-band browser auth and reads pasted credentials from `/dev/tty` so they never enter model context.
- `cloud_function/` + `docs/GCP-RECREATION.md` indicate the canonical deployment relies on a **Google-hosted OAuth/token-exchange Cloud Function**, with a guide to self-host that infrastructure if desired — i.e. this is not a bare "bring your own OAuth client ID" flow like NouGen's port.
- README explicitly flags **indirect prompt-injection risk**: the server can read/modify/delete the user's Google Account data, and warns never to feed it untrusted mail/doc content.

## Language / stack

- **TypeScript / Node.js** (esbuild-bundled: `esbuild.config.js`, `esbuild.auth-utils.js`, `esbuild.headless-login.js`), Jest for tests, ESLint + Prettier.
- Ships as a **Gemini CLI extension package** (`gemini-extension.json` manifest, `commands/`, `skills/`, `docs/`), not a standalone pip-installable Python module.
- Distinct runtime and packaging model from NouGen's fleet, which is Python-first (`nougen_shards/`) for this kind of module.

## Overlap / dedup assessment vs `src/nougen_shards/google_workspace/`

NouGen already has a **native Python MCP port** (`~\Outpost\NouGen\src\nougen_shards\google_workspace\`, documented at `docs/google-workspace-mcp-port.md`, ported from `taylorwilsdon/google_workspace_mcp`) covering:

| Surface | NouGen native port | gemini-cli-extensions/workspace |
|---|---|---|
| Gmail | ✅ (`gmail.py` — list/search/get/send/draft/labels) | ✅ (`GmailService.ts`) |
| Calendar | ✅ (`calendar.py` — list/search/create/update/delete) | ✅ (`CalendarService.ts`) |
| Drive | ✅ (`drive.py` — search/metadata/download/upload/folder) | ✅ (`DriveService.ts`) |
| Docs | ❌ deferred | ✅ (`DocsService.ts`) |
| Sheets | ❌ deferred | ✅ (`SheetsService.ts`) |
| Slides | ❌ deferred | ✅ (`SlidesService.ts`) |
| Tasks | ❌ deferred | ✅ (`TasksService.ts`) |
| Chat | ❌ deferred | ✅ (`ChatService.ts`) |
| Contacts/People | ❌ deferred (Contacts out of scope) | ✅ (`PeopleService.ts`) |
| Forms | ❌ deferred | not present here either |

**Overlap is real but partial.** The three services NouGen already ported (Gmail/Calendar/Drive) are duplicated here in a different language and auth model. The services NouGen explicitly deferred (Docs, Sheets, Slides, Tasks, Chat, People) are the ones this repo *does* implement — so it is a useful reference for exactly the gap NouGen left open, not a reason to redo the part already done.

Auth models differ materially: NouGen's port uses a Dave-owned Google Cloud OAuth client (env vars `NOUGEN_GOOGLE_CLIENT_ID`/`SECRET` or a client-secret file, local token cache under `~/.nougen/shards/google_workspace`). This repo's default path routes through a Google-hosted Cloud Function for token exchange (self-hostable per `docs/GCP-RECREATION.md`), plus a separate headless-login utility. Adopting it as-is would mean trusting Google's hosted auth infra (or standing up the Cloud Function) rather than NouGen's own OAuth client — a different trust boundary than Rule 0.0/0.6 assume for the rest of the fleet's memory and credential handling.

## Recommendation: **skip full port; reference-only for the deferred services**

- **Do not port Gmail/Calendar/Drive from this repo** — NouGen's existing native Python module already covers them, is already wired into `pyproject.toml` and the MCP compat shim (`nougen_shards/mcp.py` pattern), and re-porting in TypeScript would add a second runtime (Node.js) and a second, incompatible auth model for surfaces NouGen already owns.
- **Do not adopt the Node/Gemini-CLI-extension package wholesale.** It's built to run *inside* Gemini CLI as an extension (its own `gemini-extension.json`, slash commands, skills) — bolting it onto the fleet would mean running a second MCP server stack with a different auth story from every other NouGen module, for a use case (Gmail/Calendar/Drive) already served.
- **Merge-into-existing, selectively, later:** when NouGen eventually builds the deferred Docs/Sheets/Slides/Tasks/Chat/People tools (currently listed only as "future work" in `docs/google-workspace-mcp-port.md`), use this repo's `workspace-server/src/services/*.ts` as an **API-shape reference** (request/response fields, scopes needed, edge cases already handled) while re-implementing natively in Python under `nougen_shards/google_workspace/`, following the same pattern as the existing `gmail.py`/`calendar.py`/`drive.py` modules and the standalone `server.py`. This keeps one runtime, one auth model, and one credential-storage convention for the whole module.

## What a (selective, future) port would require

1. Pick one deferred service at a time (Docs is the largest single gap upstream lists tool-counts for — 19 tools in `taylorwilsdon/google_workspace_mcp`; this repo's `DocsService.ts` is a second reference point for the same surface).
2. Read `workspace-server/src/services/<X>Service.ts` for the operations and Google API calls it wraps; do not vendor the TypeScript — reimplement in Python against `google-api-python-client`, matching NouGen's existing module structure (`<x>.py` with plain functions, registered as `@mcp.tool()` in `server.py`).
3. Extend the scopes list in `docs/google-workspace-mcp-port.md` (`gmail.*`, `calendar`, `drive.*`) with the new service's minimum scopes (e.g. `documents`, `spreadsheets`, `presentations`, `tasks`, `chat.*`, `contacts.readonly`) and re-mint the token (`python -m nougen_shards.google_workspace.auth mint`) so the existing refresh token covers the new scopes.
4. No Node.js, esbuild, or Cloud Function infra needs to be introduced — the existing Python auth flow (`auth.py`) and token cache location already generalize to additional scopes without new dependencies.
5. Explicitly carry forward this repo's README warning on indirect prompt injection into any new tool docstrings/skill text, since it applies identically to a Python re-implementation.

# Google Workspace MCP — native port

Source: [taylorwilsdon/google_workspace_mcp](https://github.com/taylorwilsdon/google_workspace_mcp) (README + repo tree read 2026-09-22).
Ported as a native NouGen module — not vendored, not a wrapper around upstream code.

## What was ported

`C:\Users\super\Outpost\NouGen\src\nougen_shards\google_workspace\`

| File | Scope |
|---|---|
| `__init__.py` | Package docstring, exports the 4 submodules |
| `auth.py` | OAuth2 refresh-token flow (google-auth + google-auth-oauthlib), token cache resolution, interactive mint command |
| `gmail.py` | `list_messages`, `search_messages`, `get_message`, `send_message`, `create_draft`, `list_labels` |
| `calendar.py` | `list_calendars`, `list_events`, `search_events`, `create_event`, `update_event`, `delete_event` |
| `drive.py` | `search_files`, `get_file_metadata`, `download_file_content`, `upload_file`, `create_folder` |
| `server.py` | Standalone MCP server (`python -m nougen_shards.google_workspace.server`) registering all 17 tools with NouGen's exact `MCPServer`/`FastMCP` compat shim and `@mcp.tool()` pattern from `nougen_shards/mcp.py` |

`C:\Users\super\Outpost\NouGen\pyproject.toml` — added `google-api-python-client>=2.100`, `google-auth>=2.25`, `google-auth-oauthlib>=1.2`, `google-auth-httplib2>=0.2` to `[project.dependencies]`. No other dependency lines touched.

### Why standalone server.py, not registered into nougen_shards/mcp.py

`nougen_shards/mcp.py` is memory-and-skills scoped (capture/recall/apply_skills) and its instructions travel with every handshake. Google credentials are optional and per-operator — not every node will have a Google OAuth client configured — so bolting 17 more tools onto the primary server's roster would advertise capability that fails on nodes without credentials. `server.py` reuses the identical `MCPServer`/`FastMCP` version-compat shim, `@mcp.tool()` decorator style, docstring-driven descriptions, and try/except-log-reraise error handling as `mcp.py`, just as its own process.

### Scopes used (minimum per service, Step 3 §7)

```
gmail.readonly, gmail.send, gmail.compose
calendar (full — read/write needed for create/update/delete event tools)
drive.readonly, drive.file
```

### Deferred (not built)

Per upstream's README tool counts, these services exist upstream but are out of scope here — listed by upstream tool-file name so a future port knows where to start:

- **Docs** (19 tools) — `gdocs/docs_tools.py`
- **Sheets** (14 tools) — `gsheets/sheets_tools.py`
- **Slides** (7 tools) — `gslides/slides_tools.py`
- **Forms** (6 tools) — `gforms/forms_tools.py`
- **Chat** (6 tools) — `gchat/chat_tools.py`
- **Tasks** (6 tools) — `gtasks/tasks_tools.py`
- Also present upstream but out of scope for this port: Contacts (`gcontacts/`), Apps Script (`gappsscript/`), Custom Search (`gsearch/`)

## Existing Google OAuth config in ~\.nougen

Checked `C:\Users\super\.nougen\auth-import\` and `C:\Users\super\.nougen\shards\` (filenames only, no values read) for anything matching `google|oauth|client_secret|gmail|calendar|drive`. **Nothing found.** No existing Google OAuth client config or token cache is present on this box — Dave needs to supply a client from scratch.

## What Dave needs to supply to finish wiring this up

1. **Create a Google Cloud OAuth client** at console.cloud.google.com:
   - Create/select a project → APIs & Services → Credentials → Create Credentials → OAuth client ID.
   - Application type: **Desktop app** (simplest for the refresh-token/local-server flow `auth.run_interactive_auth_flow` uses), or "Web application" if a fixed redirect URI is preferred.
   - Enable APIs: **Gmail API**, **Google Calendar API**, **Google Drive API** (APIs & Services → Library).
   - Download the client JSON, or copy the Client ID + Client Secret directly.

2. **Redirect URI** (only matters for the Web application client type; Desktop app clients use a dynamic loopback and don't need one registered): `http://localhost:8765/oauth2callback` (also overridable via `NOUGEN_GOOGLE_REDIRECT_URI`).

3. **Env vars to set** (one of the two credential paths):
   - `NOUGEN_GOOGLE_CLIENT_ID` + `NOUGEN_GOOGLE_CLIENT_SECRET`, **or**
   - `NOUGEN_GOOGLE_CLIENT_SECRET_FILE` = path to the downloaded client JSON.
   - Optional: `NOUGEN_GOOGLE_TOKEN_DIR` to pin the token cache location (falls back to `<NOUGEN_VAULT_DIR>/google_workspace`, then `~/.nougen/shards/google_workspace`).

4. **Install the new dependencies** (they're now in `pyproject.toml` but need an actual `pip install`):
   ```
   pip install -e "C:\Users\super\Outpost\NouGen"
   ```

5. **One-time interactive auth to mint the first refresh token**:
   ```
   python -m nougen_shards.google_workspace.auth mint
   ```
   This opens a browser, walks through consent, and writes the token cache (including `refresh_token`) to `NOUGEN_GOOGLE_TOKEN_DIR/token.json` (or the fallback path above). After this, all tools work unattended via `auth.get_credentials()`, which refreshes silently.

6. **Launch the server** once credentials exist:
   ```
   python -m nougen_shards.google_workspace.server
   ```

## Shard capture

Attempted via `mcp__nougen-shards__shards_capture` under domain_key `google-workspace-mcp-port` — see final report for outcome.

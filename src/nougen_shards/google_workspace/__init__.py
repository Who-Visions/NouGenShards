"""Native Google Workspace integration for NouGenShards.

Ported (structurally, not vendored) from taylorwilsdon/google_workspace_mcp:
Gmail, Calendar and Drive tool surfaces, rebuilt against NouGen's own MCP
registration pattern (nougen_shards.mcp / MCPServer.tool()) and NouGen's
env-var-driven config-path convention (see private_vault.py's
NOUGEN_VAULT_DIR precedent, mirrored here as NOUGEN_GOOGLE_TOKEN_DIR).

Deferred (not built — see docs/google-workspace-mcp-port.md for the
upstream tool-name inventory of each): Docs, Sheets, Slides, Forms, Chat,
Tasks, Contacts, Apps Script, Custom Search.

Modules:
    auth.py     — OAuth2 refresh-token flow, credential caching/refresh.
    gmail.py    — list/search/get/send/draft/labels tools.
    calendar.py — list/get/search/create/update/delete event + calendar tools.
    drive.py    — search/metadata/download/upload/create-folder tools.
    server.py   — standalone MCP server wiring the three modules together.
"""

from . import auth, gmail, calendar, drive  # noqa: F401

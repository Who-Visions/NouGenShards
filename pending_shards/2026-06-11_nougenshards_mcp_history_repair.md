# NouGenShards MCP Fleet Registry Repair - 2026-06-11

## Finding

NouGenShards repo MCP startup repair completed for `nougenai-fleet-registry`.
The failure `MCP startup failed: handshaking with MCP server failed: connection closed: initialize response`
was caused by the Watchtower `local_search_mcp.py` server exiting before `initialize`.

In this Codex sandbox, the server could not create its default lock at
`%USERPROFILE%\.codex\memories\local_search_mcp.lock`, producing `PermissionError`
and closing stdio. Earlier, a stale/active lock pointed at PID `57608`.

A separate config risk was that some MCP configs launched `python`, which was not on
PATH in this environment.

## Implementation

Project path:
`%USERPROFILE%\Watchtower\NouGen\NouGenShards`

Repo fix:

- Added `tools/nougenai_fleet_registry_mcp.py`, a workspace-safe launcher.
- The wrapper sets `NOUGENAI_MCP_LOCK_DIR` to repo-local `.mcp-locks/<pid>`.
- The wrapper sets `WATCHTOWER_ROOT`, prepends Watchtower to `sys.path`, and runpy-runs
  `%USERPROFILE%\Watchtower\local_search_mcp.py` unchanged.
- Updated `src/nougen_shards/openrouter_mcp_client.py` to include
  `nougenai-fleet-registry` in the MCP allowlist.
- Normalized `python` and `python3` commands to `sys.executable`.
- Routed the fleet registry through the wrapper when present.
- Added `NOUGEN_MCP_CONFIG_PATH` support for testable config override.
- Added `.mcp-locks/` to `.gitignore`.

## Verification

- Direct MCP `initialize` against the wrapper succeeded.
- `list_tools` returned 24 tools, including `recall_context`.
- `mesh_health` call returned content.
- Focused tests passed with `PYTHONPATH=src`:
  `tests/test_openrouter_mcp_client.py` and `tests/test_context_client.py`, 15 passed.

## Related Test-Isolation Issue

Full suite result was 115 passed, 6 failed. Those failures are unrelated to MCP.

Cause:

- `history.py` uses `Path.home() / ".nougen" / "shards" / "history.db"` independently.
- `tests/test_shards.py` monkeypatches only `core` shard DB paths, not
  `history.HISTORY_DIR` and `history.DB_PATH`.
- In this sandbox, SQLite WAL cannot open that home history DB path.

Future fix:

- Make history storage configurable through `NOUGEN_HOME` or `NOUGEN_SHARDS_DIR`, or
  monkeypatch `history.HISTORY_DIR` and `history.DB_PATH` in shard/history tests.

## Tags

`nougenshards,mcp,fleet-registry,local_search_mcp,codex,history.py,sqlite,tests`

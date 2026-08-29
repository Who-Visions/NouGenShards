<!-- route: ollama-cloud-davemeralus -->

**Mapping of proposed next‑gen connector tools to existing infrastructure**

| TOOL | ALREADY EXISTS AS | VERDICT | ONE‑LINE JUSTIFICATION |
|------|-------------------|---------|------------------------|
| repo_scan | `run_brain_scan` (MCP) | **BUILD** | Scans code‑base, not brain; needs repo‑specific logic. |
| repo_read | fleet connector `read` | **ALIAS** | Directly matches the existing *read* endpoint. |
| repo_grep | fleet connector `search` | **ALIAS** | Text search over repo is already provided by *search*. |
| shards_related | MCP tool `recall_related` | **ALIAS** | Same semantics – fetch related shards. |
| shard_from_diff | MCP tool `promote_context_to_shard` (wrapped) | **THIN‑WRAP** | Create a shard from diff by feeding diff as context. |
| repo_diff | – | **BUILD** | No repo‑diff capability in current codebase. |
| repo_status | fleet connector `status` | **ALIAS** | Existing *status* endpoint reports repo/fleet state. |
| fleet_activity | fleet connector `tracker_daily` (wrapped) | **THIN‑WRAP** | Daily activity can be derived from the tracker. |
| fleet_compare | – | **BUILD** | No tool that compares two fleet snapshots side‑by‑side. |
| tests_run | – | **BUILD** | No test‑execution harness in the repo. |
| command_run | MCP tool `execute_sandboxed_code` | **ALIAS** | Executes arbitrary code in a sandboxed environment. |
| relay_from_failure | fleet connector `relay_open` (wrapped) | **THIN‑WRAP** | Needs error‑aware wrapper around existing relay. |
| readme_sync | – | **BUILD** | No dedicated sync of README with shard store. |
| service_health | script `gateway_probe.py` | **ALIAS** | Performs health‑check probing of services. |
| logs_query | MCP tool `search_context` | **ALIAS** | Queries logged context events. |
| incident_trace | MCP tools `
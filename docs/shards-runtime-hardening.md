# Shards runtime hardening

The node/tunnel owner is the versioned `tools/start_grid.py`. The installed
runtime copy is `%USERPROFILE%/.nougen/bin/start_grid.py`; the node boot task
syncs it atomically with `tools/install_grid_supervisor.ps1` before starting the
watcher. Do not enable the legacy `NouGen Shard Gateway` task: it can start a
second quick tunnel.

## Liveness

The watcher runs `tools/gateway_probe.py` on each watch tick. The probe performs
OAuth registration, token exchange, and an authenticated `shards_recall` MCP
call. Results contain no credential values:

- `%USERPROFILE%/.nougen/state/gateway_probe.json` — last result
- `%USERPROFILE%/.nougen/state/gateway_probe.alert` — present only on failure
- `%USERPROFILE%/.nougen/bin/gateway_probe.log` — bounded diagnostic log

The independent `NouGen Shards Authenticated Probe` task is also installed for
five-minute checks. Its non-zero exit is visible in Task Scheduler.

## Backups

Use `tools/vault_backup_restore.py snapshot --only graph.db` for a fast drill,
or repeat `--only nougen_shards_N.db` for the large stores. `snapshot --db-only`
selects only root SQLite stores; omit it to include the artifact tree. Every
snapshot records hashes, and the snapshot command runs a temporary SQLite
restore plus `PRAGMA integrity_check`. Backups resolve from
`NOUGEN_BACKUP_DIR` (default `%USERPROFILE%/.nougen/backups/shards`).

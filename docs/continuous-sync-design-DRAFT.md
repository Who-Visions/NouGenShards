# Shard Highway: Blade Primary and Who-Art Standby

> Drafted by local Ollama `gemma4:e2b-qat`; reviewed and corrected by Codex on 2026-08-17.

Blade is the sole public write primary for the nine-database NouGen shard grid. Both
Cloudflare Tunnel connectors share one tunnel, and both terminate
`shards.nougenai.com` traffic at Blade. This avoids the split-brain risk created by
letting replicas write independent SQLite grids.

On Who-Art, `127.0.0.1:4444` is an SSH forward to Blade's `127.0.0.1:4444`; the
Cloudflare connector sends its public traffic through that lane. Who-Art's complete
local standby listens separately on `0.0.0.0:4445` and is not a public writer.

Every five minutes, Who-Art runs an authenticated missing-hash sync from Blade to the
standby. The sync compares compact `id,file_hash` manifests and transfers only absent
records, including private records through the shared private-vault key. It is additive
and idempotent; it does not replay SQLite WAL files or use last-write-wins clocks.

The synchronized baseline is 199,362 rows and 199,362 unique hashes. Both nodes have
the same durable identity digest:

`077eaa5d7a6bd1f76cdd685acd78bec7ff95ca3547fa72af32b2129cce72f0f8`

All nine databases pass `PRAGMA integrity_check`. Promotion of Who-Art remains manual:
stop or isolate the old primary, run a final sync when reachable, verify counts and the
identity digest, then redirect Who-Art's public lane from the SSH forward to its local
standby. Independent active writers are outside this design.

# Read-only shards replica (Docker)

Search-only copy of the phoebus vaults. The launchd node stays the only writer.

    ./snapshot.sh                      # snapshots/<stamp>/ + snapshots/LATEST.json
    docker compose up -d --build       # serves 127.0.0.1:7870
    curl -s localhost:7870/health

- `snapshot.sh` copies each vault with `sqlite3 .backup`, switches the copy to
  `journal_mode=DELETE`, and publishes `LATEST.json` last. It fails if the source
  has no `nougen_shards_*.db`.
- The container runs in snapshot mode (`NOUGEN_SNAPSHOT_DIR=/vault`,
  `NOUGEN_SNAPSHOT_LOCALIZE=0`), so every DB opens `immutable=1&mode=ro`.
- Refresh: rerun `./snapshot.sh`; the replica picks up the new `LATEST.json`
  within `NOUGEN_SNAPSHOT_REFRESH_S` (300s), or `docker compose restart`.
- Token: put `NGS_NODE_TOKEN=...` in `replica.env`. It is gitignored and excluded
  from the Docker build context by the root `.dockerignore`.

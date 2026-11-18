# Read-only shards replica (Docker)

Search-only copy of the phoebus vaults. The launchd node stays the only writer.

    ./snapshot.sh                      # copy vaults with sqlite .backup
    docker compose up -d --build       # serves 127.0.0.1:7870
    curl -s localhost:7870/health

Refresh: rerun `./snapshot.sh`, then `docker compose restart`.
Token: put `NGS_NODE_TOKEN=...` in `replica.env` (gitignored).

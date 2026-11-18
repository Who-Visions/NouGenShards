#!/usr/bin/env bash
# Point-in-time copy of the shard vaults for the read-only Docker replica.
# sqlite3 .backup is WAL-safe and takes no long lock on the live node.
# Never mount ~/.nougen/shards into a container directly.
set -euo pipefail
SRC="${NOUGEN_VAULT_SRC:-$HOME/.nougen/shards}"
DST="${REPLICA_DIR:-$HOME/.nougen/replica/shards}"
rm -rf "$DST.tmp"; mkdir -p "$DST.tmp"
for db in "$SRC"/nougen_shards_*.db; do
  name=$(basename "$db")
  sqlite3 "$db" ".backup '$DST.tmp/$name'"
  echo "snapshot $name"
done
date -u +%Y-%m-%dT%H:%M:%SZ > "$DST.tmp/SNAPSHOT_AT"
rm -rf "$DST.old"; [ -d "$DST" ] && mv "$DST" "$DST.old"
mv "$DST.tmp" "$DST"; rm -rf "$DST.old"
echo "replica at $DST ($(du -sh "$DST" | cut -f1))"

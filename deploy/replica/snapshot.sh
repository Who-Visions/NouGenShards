#!/usr/bin/env bash
# Point-in-time snapshot of the shard vaults for the read-only Docker replica.
# Layout matches snapshot_mode: $DST/snapshots/<stamp>/ + $DST/snapshots/LATEST.json.
# sqlite3 .backup is WAL-safe and takes no long lock on the live node; the copy is
# switched to journal_mode=DELETE so it needs no -wal/-shm sidecars.
# Never mount ~/.nougen/shards into a container directly.
set -euo pipefail
shopt -s nullglob
SRC="${NOUGEN_VAULT_SRC:-$HOME/.nougen/shards}"
DST="${REPLICA_DIR:-$HOME/.nougen/replica}"
dbs=("$SRC"/nougen_shards_*.db)
if [ ${#dbs[@]} -eq 0 ]; then
  echo "snapshot.sh: no nougen_shards_*.db found in $SRC" >&2
  exit 1
fi
SNAPS="$DST/snapshots"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
STAGE="$SNAPS/.$STAMP.tmp"
mkdir -p "$SNAPS"
rm -rf "$STAGE"; mkdir -p "$STAGE"
trap 'rm -rf "$STAGE"' EXIT
for db in "${dbs[@]}"; do
  name=$(basename "$db")
  sqlite3 "$db" ".backup '$STAGE/$name'"
  sqlite3 "$STAGE/$name" "PRAGMA journal_mode=DELETE;" >/dev/null
  echo "snapshot $name"
done
date -u +%Y-%m-%dT%H:%M:%SZ > "$STAGE/SNAPSHOT_AT"
mv "$STAGE" "$SNAPS/$STAMP"
trap - EXIT
printf '{"stamp":"%s"}\n' "$STAMP" > "$SNAPS/.LATEST.json.tmp"
mv -f "$SNAPS/.LATEST.json.tmp" "$SNAPS/LATEST.json"
for old in "$SNAPS"/*; do
  base=$(basename "$old")
  if [ "$base" != "$STAMP" ] && [ "$base" != "LATEST.json" ]; then rm -rf "$old"; fi
done
echo "replica snapshot $STAMP at $SNAPS/$STAMP ($(du -sh "$SNAPS/$STAMP" | cut -f1))"
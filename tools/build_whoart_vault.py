"""Build a machine's federation snapshot: merge its local 9-DB shard grid into
one FTS5-indexed vault DB for registration on the canonical node's keymaker
(register, don't bulk-copy — decision 16729). The canonical node's federation
sweep reads through the snapshot; the source machine's rows never enter the
canonical grid.

Re-run any time to refresh the snapshot (drops and rebuilds), then ship it to
the canonical node's vault directory — registration keys on the path, so a
refresh to the same path survives without re-registering.

Sensitivity fence: only rows with sensitivity 'normal' (a TEXT column, not a
flag) and enc=0 are exported — the exposure policy keeps journal/personal rows
on their home machine, and a federated store is readable by every owner
surface.

Config (env-first, logged fallbacks per the lane conventions):
  NOUGEN_VAULT_DIR    source grid directory   (default ~/.nougen/shards)
  NOUGEN_SNAPSHOT_OUT output snapshot path    (default <vault>/<host>_grid_vault.db)
"""
import glob
import os
import platform
import sqlite3

VAULT_DIR = os.environ.get("NOUGEN_VAULT_DIR") or os.path.join(
    os.path.expanduser("~"), ".nougen", "shards")
SRC_GLOB = os.path.join(VAULT_DIR, "nougen_shards_*.db")
HOST = platform.node().lower() or "local"
OUT = os.environ.get("NOUGEN_SNAPSHOT_OUT") or os.path.join(
    VAULT_DIR, f"{HOST}_grid_vault.db")
MAX_CONTENT = 100_000  # bound row size so one giant import can't bloat the vault

if os.path.exists(OUT):
    os.remove(OUT)

out = sqlite3.connect(OUT)
out.execute("""create table shards (
    title text, content text, tags text, event_type text,
    timestamp text, src_db text, src_id integer)""")

total = skipped = 0
for path in sorted(glob.glob(SRC_GLOB)):
    name = os.path.basename(path)
    src = sqlite3.connect(path)
    rows = src.execute("""select id, timestamp, event_type, title, content, tags,
        coalesce(sensitivity, 'normal'), coalesce(enc, 0) from shards""")
    for sid, ts, etype, title, content, tags, sens, enc in rows:
        if (sens or "normal").lower() not in ("normal", "") or enc:
            skipped += 1
            continue
        out.execute("insert into shards values (?,?,?,?,?,?,?)",
                    (title or "", (content or "")[:MAX_CONTENT], tags or "",
                     etype or "", ts or "", name, sid))
        total += 1
    src.close()

out.execute("create virtual table shards_fts using fts5(title, content, tags, content=shards)")
out.execute("insert into shards_fts(rowid, title, content, tags) select rowid, title, content, tags from shards")
out.commit()

size_mb = os.path.getsize(OUT) / 1e6
print(f"source : {SRC_GLOB}")
print(f"rows: {total}  skipped(sensitive/enc): {skipped}  size: {size_mb:.0f} MB")
print("out:", OUT)

# Distinctive sample rows for the mandatory index-on-arrival smoke test
# (decision 16729: a federated store proves itself with a known-content query
# returning its own provenance before anyone trusts it).
print("\nsmoke candidates (oldest distinctive titles):")
for title, ts in out.execute("""select title, timestamp from shards
        where length(title) > 30 and title not like '[CODEX]%'
        order by timestamp asc limit 5"""):
    print(" ", ts[:10], "|", title[:80])

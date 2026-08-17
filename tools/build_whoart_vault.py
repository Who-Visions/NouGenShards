"""Build whoart's federation snapshot: merge the local 9-DB shard grid into one
FTS5-indexed vault DB for registration on blade (register, don't bulk-copy —
decision 16729). Blade's sweep reads through it; whoart's rows never enter the
canonical grid.

Re-run any time to refresh the snapshot (drops and rebuilds), then copy it to
the configured vault path on the reader node; registration survives refreshes
because the path stays the same.

Sensitivity fence: rows marked sensitive (sensitivity flag) or encrypted (enc)
are EXCLUDED — the exposure policy says journal/personal stays owner-lane, and
a federated store on blade is readable by every owner surface.
"""
import glob
import os
import sqlite3
from pathlib import Path

_SHARDS = Path(os.environ.get(
    "NOUGEN_VAULT_DIR", str(Path.home() / ".nougen" / "shards")
))
SRC_GLOB = str(_SHARDS / "nougen_shards_*.db")
OUT = str(_SHARDS / "whoart_grid_vault.db")
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
        # sensitivity is text ('normal' = exportable); anything else stays home,
        # as does any encrypted row.
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
print(f"rows: {total}  skipped(sensitive/enc): {skipped}  size: {size_mb:.0f} MB")
print("out:", OUT)

# Distinctive sample rows for the mandatory index-on-arrival smoke test.
print("\nsmoke candidates (oldest distinctive titles):")
for title, ts in out.execute("""select title, timestamp from shards
        where length(title) > 30 and title not like '[CODEX]%'
        order by timestamp asc limit 5"""):
    print(" ", ts[:10], "|", title[:80])

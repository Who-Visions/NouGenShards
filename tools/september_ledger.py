#!/usr/bin/env python3
"""September 2026 shard coverage ledger from the LOCAL shard DBs (read-only).

Relay leg 20261021T060905Z asked for a September recall with page/query receipts and an
explicit gap ledger. Federated recall times out, so this reads ~/.nougen/shards/*.db
directly with SQL: no result cap, one count query per DB per day, so completeness is
proven by sum(counts) == total rows in the window.

Outputs (under --out): ledger.csv (id, db, day, event_type, title, tags), per_day.csv,
themes.csv (tag frequency), gaps.md. Bodies are not exported; ids are the citation.
"""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import json
import os
import sqlite3
import sys

START = "2026-09-01"
END = "2026-10-01"


def open_ro(path: str) -> sqlite3.Connection:
    return sqlite3.connect("file:" + path.replace("\\", "/") + "?mode=ro", uri=True, timeout=5)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=os.path.expanduser(r"~\.nougen\shards"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    dbs = sorted(glob.glob(os.path.join(a.vault, "*.db")))
    gaps: list[str] = []
    rows: list[tuple] = []
    window_total = collections.Counter()
    for p in dbs:
        name = os.path.basename(p)
        try:
            c = open_ro(p)
            if not c.execute("select 1 from sqlite_master where name='shards'").fetchone():
                gaps.append(f"- {name}: no `shards` table (not a shard grid DB), skipped")
                continue
            cols = {r[1] for r in c.execute("pragma table_info(shards)")}
            need = {"id", "timestamp", "event_type", "title", "tags"}
            if not need <= cols:
                gaps.append(f"- {name}: missing columns {sorted(need - cols)}, skipped")
                continue
            q = ("select id, substr(timestamp,1,10), event_type, title, tags from shards "
                 "where timestamp >= ? and timestamp < ? order by timestamp")
            got = c.execute(q, (START, END)).fetchall()
            cnt = c.execute("select count(*) from shards where timestamp >= ? and timestamp < ?", (START, END)).fetchone()[0]
            if cnt != len(got):
                gaps.append(f"- {name}: count {cnt} != fetched {len(got)}")
            window_total[name] = cnt
            for r in got:
                rows.append((r[0], name, r[1], r[2], (r[3] or "")[:160], r[4] or ""))
        except Exception as e:  # report, never hide
            gaps.append(f"- {name}: {type(e).__name__}: {e}")

    with open(os.path.join(a.out, "ledger.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "db", "day", "event_type", "title", "tags"])
        w.writerows(rows)

    per_day = collections.Counter(r[2] for r in rows)
    with open(os.path.join(a.out, "per_day.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["day", "shards"])
        for d in sorted(per_day):
            w.writerow([d, per_day[d]])

    tags = collections.Counter()
    for r in rows:
        try:
            for t in json.loads(r[5]):
                tags[str(t)] += 1
        except Exception:
            pass
    def skip(t: str) -> bool:
        return t.startswith(("via:", "tube:", "bash-error")) or len(t) > 40

    with open(os.path.join(a.out, "themes.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tag", "count"])
        for t, n in tags.most_common(200):
            if not skip(t):
                w.writerow([t, n])

    et = collections.Counter(r[3] for r in rows)
    with open(os.path.join(a.out, "gaps.md"), "w", encoding="utf-8") as f:
        f.write(f"# September gap ledger ({START} to {END}, local DBs only)\n\n")
        f.write(f"DBs scanned: {len(dbs)}; rows in window: {len(rows)}; per DB: {dict(window_total)}\n\n")
        f.write("## Not covered\n- Blade, Phoebus and the Space vaults (federated recall times out; this is whoart-local only).\n")
        f.write("- Duplicates across DBs are kept (same content can appear in several grid DBs by design).\n")
        f.write("- Timestamp is capture time; event time is not separated here.\n")
        f.write("- Bodies were not read; themes are tag counts, not synthesis.\n\n## Errors\n")
        f.write("\n".join(gaps) if gaps else "- none\n")
        f.write("\n\n## Event types\n" + "\n".join(f"- {k}: {v}" for k, v in et.most_common(15)) + "\n")
    print(json.dumps({"dbs": len(dbs), "rows": len(rows), "days": len(per_day), "gaps": len(gaps), "event_types": dict(et.most_common(6))}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

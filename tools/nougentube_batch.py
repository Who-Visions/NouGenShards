"""NouGenTube batch runner — sweep every seed in the roster CSV, stamping genre/category tags.

Roster: transcripts/channels.csv with header seed_url,handle,genre,category,notes
(path overridable via NOUGEN_YT_ROSTER). Sweeps run sequentially to stay under
YouTube rate limits; each row shells out to nougentube.py, which is idempotent.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROSTER = Path(os.environ.get("NOUGEN_YT_ROSTER", str(_REPO_ROOT / "transcripts" / "channels.csv")))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--days", type=int, default=int(os.environ.get("NOUGEN_YT_DAYS", "30")))
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--only", default="", help="Comma-separated handle filter (substring match)")
    parser.add_argument("--max-new-total", type=int, default=int(os.environ.get("NOUGEN_YT_DRIP_CAP", "0")),
                        help="GLOBAL cap on new transcript fetches across all seeds this run "
                             "(0 = unlimited). Drip-backfill throttle; see wargames/drip-backfill.md.")
    args = parser.parse_args()

    rows = [r for r in csv.DictReader(args.roster.open(encoding="utf-8")) if r.get("seed_url", "").startswith("http")]
    only = [s.strip().lower() for s in args.only.split(",") if s.strip()]
    if only:
        rows = [r for r in rows if any(o in r.get("handle", "").lower() for o in only)]
    if args.max_new_total and rows:
        # Rotate the starting seed daily so early CSV rows can't hog the drip
        # budget until their whole backlog drains.
        import datetime
        k = datetime.date.today().timetuple().tm_yday % len(rows)
        rows = rows[k:] + rows[:k]
    print(f"roster: {len(rows)} seeds from {args.roster}")

    budget = args.max_new_total
    failures = []
    for i, row in enumerate(rows, 1):
        if args.max_new_total and budget <= 0:
            print(f"\ndrip budget spent — stopping before remaining {len(rows) - i + 1} seeds (resume tomorrow)")
            break
        tags = ",".join(
            f"{k}:{row[k].strip()}" for k in ("genre", "category")
            if row.get(k, "").strip() and row[k].strip().lower() != "tbd"
        )
        cmd = [sys.executable, str(_REPO_ROOT / "tools" / "nougentube.py"),
               "--seed", row["seed_url"], "--days", str(args.days)]
        if tags:
            cmd += ["--tags", tags]
        if args.confirm:
            cmd.append("--confirm")
        if args.max_new_total:
            cmd += ["--max-new", str(budget)]
        print(f"\n===== [{i}/{len(rows)}] {row.get('handle') or row['seed_url']} ({tags or 'no tags'}) =====",
              flush=True)
        env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "src")}
        if args.max_new_total:
            proc = subprocess.run(cmd, env=env, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
            print(proc.stdout, end="", flush=True)
            if proc.stderr.strip():
                print(proc.stderr, end="", file=sys.stderr, flush=True)
            m = re.search(r"^NEW_FETCHES: (\d+)$", proc.stdout, re.MULTILINE)
            # Fail-closed: a child that died before printing the marker is charged
            # the full remaining budget — never overshoot the drip cap on a bad day.
            budget -= int(m.group(1)) if m else budget
        else:
            proc = subprocess.run(cmd, env=env)
        if proc.returncode == 3:
            print("\nrate-limit circuit open — aborting batch (resume later; runs are idempotent)")
            sys.exit(3)
        if proc.returncode != 0:
            failures.append(row.get("handle") or row["seed_url"])

    print(f"\nbatch done: {len(rows) - len(failures)}/{len(rows)} ok" +
          (f"; failed: {', '.join(failures)}" if failures else ""))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

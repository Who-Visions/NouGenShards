"""NouGenTube batch runner — sweep every seed in the roster CSV, stamping genre/category tags.

Roster: transcripts/channels.csv with header seed_url,handle,genre,category,notes
(path overridable via NOUGEN_YT_ROSTER). Sweeps run sequentially to stay under
YouTube rate limits; each row shells out to nougentube.py, which is idempotent.
"""
from __future__ import annotations

import argparse
import csv
import os
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
    args = parser.parse_args()

    rows = [r for r in csv.DictReader(args.roster.open(encoding="utf-8")) if r.get("seed_url", "").startswith("http")]
    only = [s.strip().lower() for s in args.only.split(",") if s.strip()]
    if only:
        rows = [r for r in rows if any(o in r.get("handle", "").lower() for o in only)]
    print(f"roster: {len(rows)} seeds from {args.roster}")

    failures = []
    for i, row in enumerate(rows, 1):
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
        print(f"\n===== [{i}/{len(rows)}] {row.get('handle') or row['seed_url']} ({tags or 'no tags'}) =====",
              flush=True)
        env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "src")}
        proc = subprocess.run(cmd, env=env)
        if proc.returncode != 0:
            failures.append(row.get("handle") or row["seed_url"])

    print(f"\nbatch done: {len(rows) - len(failures)}/{len(rows)} ok" +
          (f"; failed: {', '.join(failures)}" if failures else ""))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

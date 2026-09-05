"""Publish a consistent whole-file snapshot of blade's grid to the HF bucket.

Architecture (GM decision B, 2026-08-31): the Space is a READ-ONLY consumer
of snapshot artifacts. Row-wise replication corrupted the Space's sqlite grid
on every storage backend tried - network-backed mounts do not honor sqlite's
locking - so blade builds the DB files and ships them WHOLE; the Space opens
them immutable (no writes = no corruption) and forwards captures to blade.

Per DB: the sqlite backup API produces a consistent copy against live
writers, the copy is checkpointed to journal_mode=DELETE (immutable readers
must never look for a WAL), sha256'd into a manifest, and the set is synced
to bucket snapshots/<stamp>/. snapshots/LATEST.json is written LAST so
readers only ever see complete sets. Older snapshots are pruned after
cutover (keep the newest N, env NOUGEN_SNAPSHOT_KEEP, default 1).

Run from NouGenShards-push-main:
    .venv\\Scripts\\python.exe tools\\publish_vault_snapshot.py [--bucket OWNER/NAME]
"""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from huggingface_hub import HfApi  # noqa: E402

from nougen_shards import core  # noqa: E402

DEFAULT_BUCKET = os.environ.get("NOUGEN_SNAPSHOT_BUCKET", "nougenai/ngs-vault")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def backup_db(index: int, dest: Path) -> dict | None:
    src_path = core.get_db_path(index)
    if not src_path.exists():
        return None
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True, timeout=30)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
        # Immutable readers must not expect a WAL; flatten the journal mode.
        dst.execute("PRAGMA journal_mode=DELETE;")
        dst.commit()
        rows = dst.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
    finally:
        src.close()
        dst.close()
    return {"file": dest.name, "rows": rows, "bytes": dest.stat().st_size,
            "sha256": sha256_file(dest)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", default=DEFAULT_BUCKET)
    ap.add_argument("--keep", type=int,
                    default=int(os.environ.get("NOUGEN_SNAPSHOT_KEEP", "1")))
    args = ap.parse_args()
    api = HfApi()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tmp = Path(tempfile.mkdtemp(prefix="ngs_snapshot_"))
    try:
        dbs = []
        t0 = time.time()
        for i in range(1, core.MAX_DB_COUNT + 1):
            entry = backup_db(i, tmp / f"nougen_shards_{i}.db")
            if entry:
                entry["index"] = i
                dbs.append(entry)
                print(f"[*] db{i}: {entry['rows']} rows, "
                      f"{entry['bytes']/1e6:.0f}MB", flush=True)
        manifest = {
            "stamp": stamp,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "source_host": os.environ.get("COMPUTERNAME", "unknown"),
            "total_rows": sum(d["rows"] for d in dbs),
            "total_bytes": sum(d["bytes"] for d in dbs),
            "databases": dbs,
        }
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2),
                                           encoding="utf-8")
        print(f"[*] snapshot built: {manifest['total_rows']} rows, "
              f"{manifest['total_bytes']/1e9:.2f}GB in {time.time()-t0:.0f}s; "
              f"uploading to {args.bucket}/snapshots/{stamp}/ ...", flush=True)
        api.sync_bucket(source=str(tmp),
                        dest=f"hf://buckets/{args.bucket}/snapshots/{stamp}")
        # LATEST last: readers switch only when the set is complete.
        latest_payload = json.dumps({"stamp": stamp,
                                     "path": f"snapshots/{stamp}",
                                     "total_rows": manifest["total_rows"]}).encode()
        api.batch_bucket_files(args.bucket,
                               add=[(latest_payload, "snapshots/LATEST.json")])
        print(f"[*] LATEST -> {stamp}", flush=True)
        # prune older snapshot dirs beyond --keep
        try:
            tree = list(api.list_bucket_tree(args.bucket, prefix="snapshots",
                                             recursive=True))
            files = [t.path for t in tree if hasattr(t, "size")]
            stamps = sorted({f.split("/")[1] for f in files
                             if f.count("/") >= 2})
            for old_stamp in (stamps[:-args.keep] if args.keep else []):
                doomed = [f for f in files if f.startswith(f"snapshots/{old_stamp}/")]
                if doomed:
                    api.batch_bucket_files(args.bucket, delete=doomed)
                    print(f"[*] pruned {old_stamp} ({len(doomed)} files)", flush=True)
        except Exception as exc:  # pruning is best-effort
            print(f"[!] prune skipped: {type(exc).__name__}: {exc}", flush=True)
        print(f"[OK] snapshot {stamp} published: {manifest['total_rows']} rows",
              flush=True)
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

"""Batched shard push to a remote NouGenShards relay node.

The CLI's `nougen node push` sends the whole vault in one POST with a 10s
timeout — fine for a handful of shards, hopeless for 20k+. This pushes in
chunks, resumes from any offset, and reads NGS_NODE_TOKEN from the keymaker
vault in-process so the secret never touches argv, env, or logs.

Usage:
    python tools/relay_push.py [--url URL] [--batch N] [--start N] [--dry-run]
"""
import argparse
import itertools
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nougen_shards import keymaker  # noqa: E402
from nougen_shards.brain_scan.redaction import redact_content  # noqa: E402

DEFAULT_URL = "https://nougenai-nougenshards.hf.space"
DEFAULT_VAULT = Path.home() / ".nougen" / "shards"


def _decode_embedding(value):
    """Decode both legacy JSON embeddings and current float32 BLOBs."""
    if value is None:
        return None
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        try:
            return json.loads(value.decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            if len(value) % np.dtype(np.float32).itemsize:
                return None
            return np.frombuffer(value, dtype=np.float32).astype(float).tolist()
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, list) else None


def iter_shards(vault_dir: Path):
    """Yield shards without materializing the entire fleet grid in RAM.

    Reads nougen_shards_N.db directly rather than through core so the vault
    location is independent of NOUGEN_VAULT_DIR (which keymaker also honors).
    """
    for db in sorted(vault_dir.glob("nougen_shards_*.db")):
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("SELECT * FROM shards ORDER BY id")
            for r in cursor:
                d = dict(r)
                d["embedding"] = _decode_embedding(d.get("embedding"))
                yield d
        finally:
            conn.close()


def count_shards(vault_dir: Path) -> int:
    total = 0
    for db in sorted(vault_dir.glob("nougen_shards_*.db")):
        conn = sqlite3.connect(db)
        try:
            total += conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
        finally:
            conn.close()
    return total


def plan_missing_shards(vault_dir: Path, known_hashes: set[str]) -> list[tuple[Path, list[int]]]:
    """Plan missing row IDs without reading large content/embedding columns."""
    plan = []
    for db in sorted(vault_dir.glob("nougen_shards_*.db")):
        conn = sqlite3.connect(db)
        try:
            ids = [row[0] for row in conn.execute(
                "SELECT id, file_hash FROM shards ORDER BY id")
                   if str(row[1] or "") not in known_hashes]
        finally:
            conn.close()
        if ids:
            plan.append((db, ids))
    return plan


def iter_planned_shards(plan: list[tuple[Path, list[int]]]):
    """Read full rows only for IDs already proven absent from the target."""
    for db, ids in plan:
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        try:
            for offset in range(0, len(ids), 500):
                chunk = ids[offset:offset + 500]
                placeholders = ",".join("?" for _ in chunk)
                cursor = conn.execute(
                    f"SELECT * FROM shards WHERE id IN ({placeholders}) ORDER BY id", chunk)
                for row in cursor:
                    shard = dict(row)
                    shard["embedding"] = _decode_embedding(shard.get("embedding"))
                    yield shard
        finally:
            conn.close()


def push_batch(url: str, token: str, batch: list, timeout: float = 180.0) -> dict:
    req = urllib.request.Request(
        f"{url.rstrip('/')}/sync/push",
        data=json.dumps({"shards": batch}).encode(),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("X-NGS-Token", token)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode())


def fetch_remote_hashes(url: str, token: str, timeout: float = 180.0) -> set[str]:
    req = urllib.request.Request(f"{url.rstrip('/')}/sync/hashes", method="GET")
    req.add_header("X-NGS-Token", token)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        payload = json.loads(res.read().decode())
    hashes = payload.get("hashes", []) if isinstance(payload, dict) else payload
    return {str(value) for value in hashes}


def prepare_for_relay(shards: list, include_private: bool = False) -> tuple[list, int, int]:
    """Return a secret-redacted transport copy and publication counters.

    Private/secret shards stay local unless the operator explicitly requests a
    shared-key transfer. If redaction changes durable text, discard its old
    embedding and hash: both describe the pre-redaction body and must not cross
    the publication boundary.
    """
    prepared = []
    private_skipped = 0
    redacted = 0
    for original in shards:
        sensitivity = str(original.get("sensitivity") or "normal").lower()
        if sensitivity in {"private", "secret"} and not include_private:
            private_skipped += 1
            continue

        shard = dict(original)
        safe_title = redact_content(str(shard.get("title") or ""))
        safe_content = redact_content(str(shard.get("content") or ""))
        tags = shard.get("tags")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except ValueError:
                tags = []
        safe_tags = [redact_content(str(tag)) for tag in (tags or [])]
        changed = (safe_title != shard.get("title") or
                   safe_content != shard.get("content") or
                   safe_tags != (tags or []))
        shard["title"] = safe_title
        shard["content"] = safe_content
        shard["tags"] = safe_tags
        if changed:
            shard["embedding"] = None
            shard["file_hash"] = None
            redacted += 1
        prepared.append(shard)
    return prepared, private_skipped, redacted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--vault-dir", type=Path, default=DEFAULT_VAULT)
    ap.add_argument("--batch", type=int, default=200)
    ap.add_argument("--start", type=int, default=0, help="shard offset to resume from")
    ap.add_argument("--limit", type=int, default=None,
                    help="push at most this many shards from --start")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-private", action="store_true",
                    help="relay private/secret rows; requires a shared private-vault key")
    ap.add_argument("--missing-only", action="store_true",
                    help="fetch the target hash manifest and send only absent rows")
    args = ap.parse_args()

    token = keymaker.get_secret("NGS_NODE_TOKEN")
    if not token:
        print("[!] NGS_NODE_TOKEN not found in keymaker vault.")
        sys.exit(1)

    source_total = count_shards(args.vault_dir)
    remote_hashes = fetch_remote_hashes(args.url, token) if args.missing_only else set()
    if args.missing_only:
        missing_plan = plan_missing_shards(args.vault_dir, remote_hashes)
        candidate_total = sum(len(ids) for _, ids in missing_plan)
        source = iter_planned_shards(missing_plan)
        remote_known = source_total - candidate_total
    else:
        candidate_total = source_total
        source = iter_shards(args.vault_dir)
        remote_known = 0
    end = candidate_total if args.limit is None else min(
        candidate_total, args.start + args.limit)
    print(f"[*] {source_total} shards at {args.vault_dir}; {candidate_total} candidates; "
          f"streaming offsets "
          f"{args.start}:{end} in batches of {args.batch} to {args.url}", flush=True)

    pushed = skipped = failed = private_skipped = redacted = publishable = 0
    stream = itertools.islice(source, args.start, end)
    i = args.start
    while i < end:
        raw_batch = list(itertools.islice(stream, args.batch))
        if not raw_batch:
            break
        consumed = len(raw_batch)
        batch, batch_private, batch_redacted = prepare_for_relay(
            raw_batch, include_private=args.include_private)
        private_skipped += batch_private
        redacted += batch_redacted
        publishable += len(batch)

        if not args.dry_run and batch:
            for attempt in range(1, 4):
                try:
                    res = push_batch(args.url, token, batch)
                    pushed += res.get("count", 0)
                    skipped += res.get("skipped", 0)
                    break
                except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                    print(f"[!] batch @{i} attempt {attempt}: {type(exc).__name__}: {exc}",
                          flush=True)
                    time.sleep(10 * attempt)
            else:
                failed += len(batch)
                print(f"[!] batch @{i} abandoned after 3 attempts; "
                      f"resume later with --start {i}", flush=True)
        i += consumed
        print(f"    {i}/{end}  (new: {pushed}, deduped/skipped: {skipped}, "
              f"redacted: {redacted})", flush=True)

    mode = "DRY RUN" if args.dry_run else "OK"
    print(f"[{mode}] Done. publishable={publishable} private_skipped={private_skipped} "
          f"remote_known={remote_known} redacted={redacted} new={pushed} "
          f"skipped={skipped} failed={failed}", flush=True)


if __name__ == "__main__":
    main()

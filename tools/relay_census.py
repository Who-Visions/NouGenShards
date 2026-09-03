#!/usr/bin/env python
"""Direct Git census of the NouGenRelay registry: the reconciler's ledger read.

Reads legs and claims from the fetched registry branch (origin/<branch>), never
the working tree and never the connector's 25-leg window, so the numbers are
the ledger's numbers. One `git cat-file --batch` stream, decoded UTF-8, no
per-file subprocess.

  python tools/relay_census.py            # summary table (JSON)
  python tools/relay_census.py --no-fetch # skip the fetch
  python tools/relay_census.py --open     # also list open leg ids by owner

Env: NOUGEN_RELAY_DIR / NOUGEN_RELAY_REPO (clone; default Watchtower/NouGen/NouGenRelay
beside this repo), NOUGEN_RELAY_BRANCH (else origin/HEAD, else main),
NOUGEN_RELAY_LIVE_GIT_TIMEOUT_S (40), NOUGEN_CENSUS_AGE_BUCKETS_D (default 1,3,7,14).
"""
from __future__ import annotations

import argparse
import calendar
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def relay_dir() -> Path:
    for raw in (os.environ.get("NOUGEN_RELAY_DIR", ""), os.environ.get("NOUGEN_RELAY_REPO", "")):
        if raw.strip() and Path(raw).is_dir():
            return Path(raw)
    guess = HERE.parent.parent / "NouGenRelay"
    return guess if guess.is_dir() else Path.home() / ".nougen" / "relay"


def _timeout() -> float:
    try:
        return float(os.environ.get("NOUGEN_RELAY_LIVE_GIT_TIMEOUT_S", "") or 40)
    except ValueError:
        return 40.0


def _git(repo: Path, *args: str, input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", input=input_text, timeout=_timeout(), creationflags=NO_WINDOW)


def registry_ref(repo: Path) -> str:
    raw = os.environ.get("NOUGEN_RELAY_BRANCH", "").strip()
    if raw:
        return f"origin/{raw}"
    r = _git(repo, "symbolic-ref", "-q", "refs/remotes/origin/HEAD")
    if r.returncode == 0 and r.stdout.strip():
        return "origin/" + r.stdout.strip().rsplit("/", 1)[-1]
    return "origin/main"


def read_json_blobs(repo: Path, ref: str, subdir: str) -> tuple[dict, list]:
    """All <subdir>/*.json blobs on ref as {path: dict}; second value lists paths that failed to parse."""
    ls = _git(repo, "ls-tree", "-r", "-z", ref, subdir)
    if ls.returncode != 0:
        return {}, [f"ls-tree failed: {ls.stderr.strip()[:120]}"]
    entries = []
    for rec in ls.stdout.split("\0"):
        if not rec.strip():
            continue
        meta, path = rec.split("\t", 1)
        sha = meta.split()[2]
        if path.endswith(".json") and path.count("/") == subdir.rstrip("/").count("/") + 1:
            entries.append((sha, path))
    if not entries:
        return {}, []
    # bytes on purpose: the batch header's size is a byte count, so the stream is
    # sliced as bytes and each body decoded on its own (a text decode first would
    # misalign on the first non-ASCII leg)
    cat = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"], capture_output=True,
                         input=("\n".join(sha for sha, _ in entries) + "\n").encode("ascii"),
                         timeout=_timeout(), creationflags=NO_WINDOW)
    out, bad = {}, []
    pos, data = 0, cat.stdout
    for sha, path in entries:
        nl = data.find(b"\n", pos)
        if nl < 0:
            bad.append(path); continue
        header = data[pos:nl].split()
        if len(header) < 3 or header[1] == b"missing":
            bad.append(path); pos = nl + 1; continue
        size = int(header[2])
        body = data[nl + 1: nl + 1 + size]
        pos = nl + 1 + size + 1
        try:
            out[path] = json.loads(body.decode("utf-8", errors="replace"))
        except ValueError:
            bad.append(path)
    return out, bad


def _epoch(iso: str) -> float | None:
    try:
        return float(calendar.timegm(time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")))
    except (ValueError, TypeError):
        return None


def census(repo: Path | None = None, *, fetch: bool = True, list_open: bool = False, now: float | None = None) -> dict:
    repo = repo or relay_dir()
    if fetch:
        _git(repo, "fetch", "--quiet", "origin")
    ref = registry_ref(repo)
    head = _git(repo, "rev-parse", ref).stdout.strip()
    legs, bad_legs = read_json_blobs(repo, ref, ".handoffs")
    claims, bad_claims = read_json_blobs(repo, ref, ".handoffs/claims")
    now = now or time.time()
    buckets = [float(x) for x in (os.environ.get("NOUGEN_CENSUS_AGE_BUCKETS_D", "") or "1,3,7,14").split(",")]
    status = Counter(str(v.get("status") or "?") for v in legs.values())
    open_legs = {p: v for p, v in legs.items() if v.get("status") == "open"}
    age = Counter()
    for v in open_legs.values():
        born = _epoch(str(v.get("created_utc") or ""))
        days = (now - born) / 86400 if born else None
        label = "unknown" if days is None else next((f"<{int(b)}d" for b in buckets if days < b), f">={int(buckets[-1])}d")
        age[label] += 1
    owners = Counter(f"{v.get('machine', '?')}/{v.get('agent', '?')}" for v in open_legs.values())
    claim_status = Counter(str(v.get("status") or "?") for v in claims.values())
    active = [v for v in claims.values() if v.get("status") == "active"]
    out = {
        "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "repo": str(repo), "ref": ref, "head": head,
        "legs": len(legs), "legs_unparsable": bad_legs, "status": dict(status),
        "open": len(open_legs), "open_by_age": dict(age), "open_by_owner": dict(owners.most_common(8)),
        "claims": len(claims), "claims_unparsable": bad_claims, "claims_by_status": dict(claim_status),
        "active_claims": [{"leg_id": c.get("leg_id"), "machine": c.get("machine"), "agent": c.get("agent"),
                           "created_utc": c.get("created_utc"), "ttl_hours": c.get("ttl_hours")} for c in active],
    }
    if list_open:
        out["open_legs"] = sorted(Path(p).stem for p in open_legs)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="direct Git census of the relay registry")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--open", action="store_true", help="list open leg ids")
    a = ap.parse_args(argv)
    print(json.dumps(census(fetch=not a.no_fetch, list_open=a.open), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

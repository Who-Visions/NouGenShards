#!/usr/bin/env python3
"""Cache arXiv lane freshness to a small marker file.

Why this exists: the startup probe (`sol_hi_probe.ps1`) reported
"arXiv Lane: No shards found" while the lane was healthy. It scanned the
constitution's vault_dir for `intelligence_shard_arxiv_*` while the writers
were landing shards in the dir `arxiv_lane_config.resolve_vault_root()`
resolves to. Pointing the probe at the real dir is correct but not free:
globbing that pattern costs ~3.2s over 88k files, and the fast greeting
budget is ~7.7s total.

So the expensive answer is computed here, out of band, and cached. The probe
reads a ~200-byte JSON instead of enumerating a six-figure directory.

Every path, prefix and threshold resolves env -> config -> logged fallback
(Rule 0.2); nothing environment-shaped is pinned in a shipped line.

    python tools/arxiv_lane_marker.py            # refresh the marker
    python tools/arxiv_lane_marker.py --print    # refresh and echo the JSON
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import arxiv_lane_config as lane_config  # noqa: E402

#: Fallbacks only. Each is overridable and the resolved source is reported in
#: the marker itself, so a stale value can never masquerade as measured truth.
FALLBACK_MARKER = "~/.nougen/arxiv_lane.json"
FALLBACK_SHARD_PREFIX = "intelligence_shard_arxiv_"


def _resolve(env_name: str, fallback: str) -> tuple[str, str]:
    raw = os.environ.get(env_name)
    if raw:
        return raw, "env:" + env_name
    return fallback, "fallback"


def marker_path() -> tuple[Path, str]:
    raw, source = _resolve("NOUGEN_ARXIV_LANE_MARKER", FALLBACK_MARKER)
    return Path(os.path.expanduser(raw)), source


def compute() -> dict:
    started = time.time()
    vault, vault_source = lane_config.resolve_vault_root()
    prefix, prefix_source = _resolve(
        "NOUGEN_ARXIV_SHARD_PREFIX", FALLBACK_SHARD_PREFIX
    )

    matches = glob.glob(os.path.join(vault, prefix + "*.md"))
    newest_path, newest_mtime = None, None
    for path in matches:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if newest_mtime is None or mtime > newest_mtime:
            newest_path, newest_mtime = path, mtime

    now = time.time()
    return {
        "schema_version": "1.0",
        "vault_dir": vault,
        "vault_dir_source": vault_source,
        "shard_prefix": prefix,
        "shard_prefix_source": prefix_source,
        "shard_count": len(matches),
        "newest_file": os.path.basename(newest_path) if newest_path else None,
        "newest_mtime_epoch": newest_mtime,
        "age_hours": round((now - newest_mtime) / 3600.0, 2) if newest_mtime else None,
        "computed_epoch": now,
        "computed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "compute_ms": int((now - started) * 1000),
    }


def write(data: dict) -> Path:
    path, _ = marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic-ish: a probe reading mid-write must never see a truncated file.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print", dest="echo", action="store_true",
                        help="echo the marker JSON to stdout")
    args = parser.parse_args()

    data = compute()
    path = write(data)
    if args.echo:
        print(json.dumps(data, indent=2))
    else:
        print(
            f"{path}: {data['shard_count']} shards, "
            f"age {data['age_hours']}h, {data['compute_ms']}ms "
            f"(vault via {data['vault_dir_source']})"
        )
    return 0 if data["shard_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

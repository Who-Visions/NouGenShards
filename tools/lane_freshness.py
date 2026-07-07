"""Lane-freshness probe — pipelines must announce their own death (HARDENING #3).

The sync agent died May 9 and the arxiv scanner died Jun 18; both failed
silently for weeks because no lane exposed its last-success age. This probe
reports the newest-artifact age per ingestion lane and flags anything stale
beyond its threshold. It never raises and always exits 0 — it is a sensor,
not a gate — so hooks and startup probes can call it unconditionally.

Usage: python tools/lane_freshness.py [--json]
"""
import argparse
import datetime
import glob
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _resolve_vault_dir():
    """Portable vault resolution — mirrors handoff_guard/nougen_shards.core:
    NOUGEN_VAULT_DIR env -> ~/.nougen/config.json -> repo .vault -> default."""
    env = os.environ.get("NOUGEN_VAULT_DIR")
    if env:
        return Path(env)
    try:
        cfg = json.loads((Path.home() / ".nougen" / "config.json").read_text(encoding="utf-8"))
        if cfg.get("vault_dir"):
            return Path(cfg["vault_dir"])
    except Exception:
        pass
    local = REPO / ".vault"
    if local.is_dir():
        return local
    return Path.home() / ".nougen" / "shards"


def _newest_age_hours(patterns):
    """Age in hours of the newest file matching any pattern; None if no files."""
    newest = None
    for pat in patterns:
        for f in glob.iglob(pat):
            try:
                mt = os.path.getmtime(f)
            except OSError:
                continue
            if newest is None or mt > newest:
                newest = mt
    if newest is None:
        return None
    return (datetime.datetime.now().timestamp() - newest) / 3600.0


def check_lanes():
    vault = _resolve_vault_dir()
    handoffs = Path(os.environ.get("NOUGEN_HANDOFF_DIR", str(REPO / ".handoffs")))
    # (lane, glob patterns, stale threshold in hours)
    lanes = [
        ("arxiv", [str(vault / "arxiv_cs_AI_*.md"),
                   str(vault / "intelligence_shard_arxiv_*.md")], 48),
        ("vault-intel", [str(vault / "intelligence_shard_*.md")], 48),
        ("handoffs", [str(handoffs / "handoff_*.md")], 72),
    ]
    results = []
    for name, patterns, threshold in lanes:
        age = _newest_age_hours(patterns)
        if age is None:
            status = "EMPTY"
        elif age > threshold:
            status = "STALE"
        else:
            status = "OK"
        results.append({
            "lane": name,
            "newest_age_hours": None if age is None else round(age, 1),
            "threshold_hours": threshold,
            "status": status,
        })
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()
    try:
        results = check_lanes()
    except Exception as e:  # sensor must never wedge a caller
        print(f"lane_freshness: probe error ({e})")
        return 0
    if args.json:
        print(json.dumps(results))
        return 0
    for r in results:
        age = "no files" if r["newest_age_hours"] is None else f"{r['newest_age_hours']}h old"
        # ASCII only: Windows consoles default to cp1252 and a sensor must
        # never crash on encoding.
        marker = "[WARN] " if r["status"] in ("STALE", "EMPTY") else "[OK]   "
        print(f"{marker}{r['lane']}: {r['status']} (newest {age}, threshold {r['threshold_hours']}h)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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


# Env-discovered knobs (Rule 0.2 — no bare inline literals). The floor is a
# safety net so a lane that has only ever produced one artifact still has a
# sane bound; the factor scales the derived threshold above a lane's normal gap.
def _env_float(name, default):
    try:
        return float(os.environ.get(name, str(default)))
    except (ValueError, TypeError):
        return default


def _env_int(name, default):
    try:
        return int(os.environ.get(name, str(default)))
    except (ValueError, TypeError):
        return default


FLOOR_HOURS = _env_float("NOUGEN_LANE_FLOOR_HOURS", 48.0)
STALE_FACTOR = _env_float("NOUGEN_LANE_STALE_FACTOR", 3.0)
CADENCE_SAMPLE = _env_int("NOUGEN_LANE_CADENCE_SAMPLE", 20)


def _mtimes(patterns):
    """Sorted (desc) modification times of all files matching any pattern."""
    times = []
    for pat in patterns:
        for f in glob.iglob(pat, recursive=True):
            try:
                times.append(os.path.getmtime(f))
            except OSError:
                continue
    times.sort(reverse=True)
    return times


def _median(xs):
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def _derive_threshold_hours(times):
    """Algorithmic stale threshold: derived from the lane's OWN cadence rather
    than a fixed constant. Uses the median inter-arrival gap of the most recent
    CADENCE_SAMPLE artifacts, scaled by STALE_FACTOR, floored at FLOOR_HOURS.
    A lane that normally emits hourly is flagged in ~STALE_FACTOR hours; a
    weekly lane gets a proportionally longer leash. Too few samples → floor."""
    if len(times) < 3:
        return FLOOR_HOURS
    recent = times[:CADENCE_SAMPLE]
    gaps = [(recent[i] - recent[i + 1]) / 3600.0 for i in range(len(recent) - 1)]
    gaps = [g for g in gaps if g > 0]
    med = _median(gaps)
    if not med:
        return FLOOR_HOURS
    return max(FLOOR_HOURS, STALE_FACTOR * med)


def check_lanes():
    vault = _resolve_vault_dir()
    handoffs = Path(os.environ.get("NOUGEN_HANDOFF_DIR", str(REPO / ".handoffs")))
    # (lane, glob patterns) — thresholds are derived per lane, not hardcoded.
    lanes = [
        # One lane per artifact type: a combined glob takes the newest across
        # both, so one artifact flowing masks the other dying (the daily-doc
        # lane died 2026-07-06 unnoticed for 5 days behind flowing shards).
        ("arxiv-daily-docs", [str(vault / "arxiv_cs_AI_*.md")]),
        ("arxiv-shards", [str(vault / "intelligence_shard_arxiv_*.md")]),
        ("vault-intel", [str(vault / "intelligence_shard_*.md")]),
        ("handoffs", [str(handoffs / "handoff_*.md"),
                      str(handoffs / "**" / "handoff_*.md")]),
    ]
    now = datetime.datetime.now().timestamp()
    results = []
    for name, patterns in lanes:
        times = _mtimes(patterns)
        age = None if not times else (now - times[0]) / 3600.0
        threshold = _derive_threshold_hours(times)
        if age is None:
            status = "EMPTY"
        elif age > threshold:
            status = "STALE"
        else:
            status = "OK"
        results.append({
            "lane": name,
            "newest_age_hours": None if age is None else round(age, 1),
            "threshold_hours": round(threshold, 1),
            "cadence_samples": len(times),
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

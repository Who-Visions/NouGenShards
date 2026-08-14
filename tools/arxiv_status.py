"""arXiv ingestion status — one JSON payload for the vinext dashboard page.

Combines two signals the morning scan already produces:
  * lane freshness (reuses lane_freshness.check_lanes — no duplicated thresholds)
  * the newest daily docs parsed into structured paper cards

It is a read-only sensor: never raises, always exits 0, prints one JSON object
on stdout so an API route can `JSON.parse` it directly. Vault path, doc limit,
and glob are all env-resolved (Rule 0.2 — no bare inline literals).

Usage: python tools/arxiv_status.py [--limit N]
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys
from pathlib import Path

# Reuse the canonical lane logic instead of re-deriving thresholds here.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lane_freshness import check_lanes, _resolve_vault_dir  # noqa: E402

DOC_GLOB = os.environ.get("NOUGEN_ARXIV_DOC_GLOB", "arxiv_cs_AI_*.md")
DEFAULT_LIMIT = int(os.environ.get("NOUGEN_ARXIV_STATUS_LIMIT", "24"))
FNAME_DATE = re.compile(r"arxiv_cs_AI_(\d{8})_")


def _field(text, label):
    m = re.search(rf"^\*\*{label}:\*\*\s*(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else None


def _abstract(text):
    m = re.search(r"##\s*Abstract\s*\n+(.+?)(?:\n##|\Z)", text, re.DOTALL)
    return " ".join(m.group(1).split()) if m else None


def _parse_doc(path):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    title_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    fn = os.path.basename(path)
    dm = FNAME_DATE.search(fn)
    submit_date = None
    if dm:
        d = dm.group(1)
        submit_date = f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
    authors = _field(text, "Authors")
    abstract = _abstract(text)
    return {
        "title": (title_m.group(1).strip() if title_m else fn),
        "submitDate": submit_date,
        "published": _field(text, "Published"),
        "authors": authors,
        "authorCount": len([a for a in authors.split(",")]) if authors else 0,
        "link": _field(text, "Link"),
        "category": _field(text, "Category"),
        "abstract": (abstract[:600] + "…") if abstract and len(abstract) > 600 else abstract,
        "mtime": os.path.getmtime(path),
    }


def build(limit):
    vault = _resolve_vault_dir()
    paths = sorted(
        glob.glob(str(vault / DOC_GLOB)),
        key=lambda p: os.path.getmtime(p),
        reverse=True,
    )
    total_docs = len(paths)
    papers = [p for p in (_parse_doc(x) for x in paths[:limit]) if p]
    for p in papers:  # mtime was only needed for ordering; drop from payload
        p.pop("mtime", None)
    # group counts by submission date across the whole vault (cheap: filename only)
    by_date = {}
    for path in paths:
        dm = FNAME_DATE.search(os.path.basename(path))
        if dm:
            d = dm.group(1)
            key = f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
            by_date[key] = by_date.get(key, 0) + 1
    recent_days = sorted(by_date.items(), reverse=True)[:14]
    return {
        "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "vault": str(vault),
        "totalDocs": total_docs,
        "lanes": check_lanes(),
        "papers": papers,
        "byDate": [{"date": k, "count": v} for k, v in recent_days],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = ap.parse_args()
    try:
        payload = build(args.limit)
    except Exception as e:  # sensor: never wedge the caller
        payload = {"error": str(e), "lanes": [], "papers": [], "byDate": [], "totalDocs": 0}
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Crawl docs.api.nvidia.com (NIM models, NGC, Cloud Functions, Attestation, TRT Cloud) and shard every page.

The site serves each page's source as Markdown at `<url>.md`, so no HTML scraping. Seeds come from the
sitemap, then every in-site link found inside a page is followed too (recursive), so pages the sitemap
misses are still reached. Raw Markdown is kept permanently under canon/nvidia-api-docs/; one NouGen shard
per page (long pages split into parts). Re-runs are idempotent: capture dedupes by content hash, and a
page whose Markdown is unchanged since the last run is skipped.

  python tools/nvidia_docs_shard.py                 # full crawl
  python tools/nvidia_docs_shard.py --max 50        # first 50 pages
  python tools/nvidia_docs_shard.py --section nim   # one top-level section
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from nougen_shards.core import capture  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = "https://docs.api.nvidia.com"
UA = {"User-Agent": "Mozilla/5.0 (NouGen docs sharder)"}
PART = 12000
DOMAIN = "nvidia-api-docs"
OUT = ROOT / "canon" / "nvidia-api-docs"
LINK = re.compile(r"\]\((/[^)\s#]*|https://docs\.api\.nvidia\.com/[^)\s#]*)")


def fetch(url: str, tries: int = 3) -> str | None:
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return None
        except Exception:
            pass
        time.sleep(1.5 * (i + 1))
    return None


def sitemap_paths() -> list[str]:
    xml = fetch(f"{BASE}/sitemap.xml") or ""
    return sorted({urlparse(u).path.rstrip("/") or "/" for u in re.findall(r"<loc>([^<]+)</loc>", xml)})


def norm(href: str) -> str | None:
    p = urlparse(urljoin(BASE + "/", href))
    if p.netloc and p.netloc != "docs.api.nvidia.com":
        return None
    path = p.path.rstrip("/")
    if not path or path.endswith((".png", ".jpg", ".svg", ".gif", ".json", ".yaml")):
        return None
    return path[:-3] if path.endswith(".md") else path


def title_of(md: str, path: str) -> str:
    m = re.search(r"^#\s+(.+)$", md, re.M)
    return (m.group(1).strip() if m else path.strip("/").split("/")[-1]).replace("  ", " ")


def split(md: str) -> list[str]:
    if len(md) <= PART:
        return [md]
    parts, cur = [], ""
    for block in re.split(r"(?m)^(?=## )", md):
        if len(cur) + len(block) > PART and cur:
            parts.append(cur); cur = ""
        while len(block) > PART:
            parts.append(block[:PART]); block = block[PART:]
        cur += block
    return parts + ([cur] if cur else [])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max", type=int, default=5000)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--section", default="", help="only paths under /<section>/ (e.g. nim, ngc)")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    state_f = OUT / "_state.json"
    state = json.loads(state_f.read_text(encoding="utf-8")) if state_f.exists() else {}
    manifest_f = OUT / "_manifest.json"
    prev_manifest = json.loads(manifest_f.read_text(encoding="utf-8")) if manifest_f.exists() else []
    by_path: dict[str, list[dict]] = {}
    for entry in prev_manifest if isinstance(prev_manifest, list) else []:
        if isinstance(entry, dict) and entry.get("path"):
            by_path.setdefault(entry["path"], []).append(entry)

    seeds = [p for p in sitemap_paths() if p != "/" and (not a.section or p.startswith(f"/{a.section}/"))]
    queue, seen = deque(seeds), set(seeds)
    pages: dict[str, str] = {}
    while queue and len(pages) < a.max:
        batch = [queue.popleft() for _ in range(min(a.workers * 4, len(queue)))]
        with ThreadPoolExecutor(a.workers) as ex:
            got = list(ex.map(lambda p: (p, fetch(f"{BASE}{p}.md")), batch))
        for path, md in got:
            if not md or len(pages) >= a.max:
                continue
            pages[path] = md
            for m in LINK.finditer(md):                      # recurse into in-site links
                n = norm(m.group(1))
                if n and n not in seen and (not a.section or n.startswith(f"/{a.section}/")):
                    seen.add(n); queue.append(n)
        print(f"fetched {len(pages)}  queued {len(queue)}", flush=True)

    written = skipped = failed = 0
    for path, md in sorted(pages.items()):
        f = OUT / (path.strip("/") + ".md")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(md, encoding="utf-8")
        h = hashlib.sha256(md.encode()).hexdigest()[:16]
        if state.get(path) == h:
            skipped += 1
            continue
        title = title_of(md, path)
        section = path.strip("/").split("/")[0]
        parts = split(md)
        page_entries = []
        page_ok = True
        for k, body in enumerate(parts, 1):
            head = f"SOURCE: {BASE}{path}\nSECTION: {section}\n" + (f"PART: {k}/{len(parts)}\n" if len(parts) > 1 else "") + "\n"
            try:
                r = capture("doc-page", f"NVIDIA API docs: {title}" + (f" (part {k}/{len(parts)})" if len(parts) > 1 else ""),
                            head + body, tags=["nvidia-api-docs", section], domain_key=DOMAIN, source_uri=f"{BASE}{path}")
            except Exception as exc:
                print(f"[!] {path} part {k}: {exc}", file=sys.stderr)
                page_ok = False
                break
            reason = r.get("reason") if isinstance(r, dict) else None
            if reason == "written":
                written += 1
            elif reason != "duplicate" and not (isinstance(r, dict) and r.get("shard_id")):
                page_ok = False
                break
            page_entries.append({"path": path, "part": k, "shard": r.get("shard_id") if isinstance(r, dict) else None,
                                 "db": r.get("db_index") if isinstance(r, dict) else None})
        if page_ok:
            state[path] = h
            by_path[path] = page_entries
        else:
            failed += 1
    manifest = [entry for p in sorted(by_path) for entry in by_path[p]]
    state_f.write_text(json.dumps(state, indent=1), encoding="utf-8")
    manifest_f.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps({"pages": len(pages), "sitemap_seeds": len(seeds), "found_by_links": len(pages) - len([p for p in pages if p in set(seeds)]),
                      "shards_written": written, "unchanged_skipped": skipped, "failed_pages": failed, "mirror": str(OUT)}))
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

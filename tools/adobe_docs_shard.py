"""Crawl an Adobe developer docs tree via its Markdown sources and shard every page.

developer.adobe.com pages render client-side, but each page's source is served as Markdown
(`<path>/index.md` or `<path>.md`). This walks every in-scope link breadth-first from a start page,
saves the raw Markdown under canon/<slug>/ (permanent), and captures one NouGen shard per page
(long pages split into parts). Re-runs are idempotent: capture dedupes by content hash.

  python adobe_docs_shard.py https://developer.adobe.com/firefly-services/docs/guides/ \
      --scope /firefly-services/docs/ --domain adobe-firefly-services-docs --slug adobe-firefly-docs
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

os.environ.setdefault("NOUGEN_VAULT_DIR", str(Path.home() / ".nougen" / "shards"))
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from nougen_shards.core import capture  # noqa: E402
for _s in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252; never crash printing model output
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = "https://developer.adobe.com"
UA = {"User-Agent": "Mozilla/5.0 (NouGen docs sharder)"}
PART = 12000  # chars per shard part
LINK = re.compile(r"\]\(([^)\s]+)\)|href=\"([^\"]+)\"")
SKIP_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".zip", ".pdf", ".mp4", ".json", ".yaml", ".yml")


def fetch(url: str) -> str | None:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                if r.status == 200:
                    return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(1 + 2 * attempt)
    return None


def md_for(path: str) -> tuple[str, str] | None:
    """Page path -> (md url, markdown). Tries <path>/index.md, then <path>.md."""
    p = path if path.endswith("/") else path + "/"
    stem = path.rstrip("/")
    cands = [p + "index.md", stem + ".md"]
    if "_" in stem:  # links often use snake_case while the sources are kebab-case (3 Events pages, 9/13/2026)
        h = stem.replace("_", "-")
        cands += [h + "/index.md", h + ".md"]
    for cand in cands:
        t = fetch(BASE + cand)
        if t and not t.lstrip().lower().startswith("<!doctype"):
            return BASE + cand, t
    # Some trees (App Builder, Runtime) don't serve .md; the page shell names its GitHub source instead.
    html = fetch(BASE + p)
    # the value may be escaped ("https\://") and HTML-entity encoded; normalize before matching
    shell = (html or "").replace("\\://", "://").replace("&#x2F;", "/").replace("&#47;", "/")
    m = re.search(r'githubblobpath[^h]{0,40}(https?://github\.com/([^/]+)/([^/]+)/blob/([^/"\s<]+)/([^"\s<\']+\.md))', shell)
    if m:
        raw = f"https://raw.githubusercontent.com/{m.group(2)}/{m.group(3)}/{m.group(4)}/{m.group(5)}"
        t = fetch(raw)
        if t and not t.lstrip().lower().startswith("<!doctype"):
            return raw, t
    return None


def norm(href: str, page_path: str, scope: str) -> str | None:
    if not href or href.startswith(("mailto:", "#", "javascript:")):
        return None
    u = urlparse(urljoin(BASE + page_path, href))
    if u.netloc and u.netloc != "developer.adobe.com":
        return None
    path = re.sub(r"(/index)?\.md$", "/", u.path)
    if not path.startswith(scope) or path.lower().endswith(SKIP_EXT):
        return None
    return path if path.endswith("/") else path + "/"


def title_of(md: str, path: str) -> str:
    m = re.search(r"^title:\s*(.+)$", md, re.M) or re.search(r"^#\s+(.+)$", md, re.M)
    return (m.group(1).strip().strip('"') if m else path.strip("/").split("/")[-1])[:140]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("start")
    ap.add_argument("--scope", required=True)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--max", type=int, default=800)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    # Git Bash (MSYS path conversion) rewrites "/express/docs/" into "C:/Program Files/Git/express/docs/" (9/13/2026: three
    # crawls stopped at 1 page). Undo it with plain string handling (a regex here was itself mangled once by a heredoc).
    sc = a.scope.replace(chr(92), "/")
    if len(sc) > 2 and sc[1] == ":" and "/Git/" in sc:
        fixed = "/" + sc.split("/Git/", 1)[1]
        print(f"  scope looked MSYS-mangled ({a.scope!r}); using {fixed!r}", flush=True)
        a.scope = fixed
    if not a.scope.startswith("/"):
        raise SystemExit(f"--scope must be a site path like /express/docs/, got {a.scope!r}")

    out = ROOT / "canon" / a.slug
    out.mkdir(parents=True, exist_ok=True)
    start = urlparse(a.start).path
    seen, queue, pages, missing = {start}, deque([start]), {}, []
    # Every AdobeDocs site keeps its full navigation in <site>/config.md (9/13/2026: the guides index pages
    # link only a handful of pages, so a link-following crawl stopped at 1 page on three sites). Seed from it.
    site = "/".join(a.scope.strip("/").split("/")[:3])
    try:
        nav = urllib.request.urlopen(urllib.request.Request(f"{BASE}/{site}/config.md", headers={"User-Agent": "Mozilla/5.0"}),
                                     timeout=30).read().decode("utf-8", "replace")
        for m in LINK.finditer(nav):
            n = norm(m.group(1) or m.group(2), start, a.scope)
            if n and n not in seen:
                seen.add(n)
                queue.append(n)
        print(f"  seeded {len(queue) - 1} pages from {site}/config.md", flush=True)
    except Exception as e:  # noqa: BLE001 - no nav file: plain link-following crawl
        print(f"  no config.md nav for {site}: {type(e).__name__}", flush=True)
    with ThreadPoolExecutor(a.workers) as ex:
        while queue and len(pages) < a.max:
            batch = [queue.popleft() for _ in range(min(len(queue), a.workers * 2))]
            for path, res in zip(batch, ex.map(md_for, batch)):
                if not res:
                    missing.append(path)
                    continue
                url, md = res
                pages[path] = {"md_url": url, "md": md}
                for m in LINK.finditer(md):
                    n = norm(m.group(1) or m.group(2), path, a.scope)
                    if n and n not in seen:
                        seen.add(n)
                        queue.append(n)
            print(f"  crawled {len(pages)} pages, queue {len(queue)}, missing {len(missing)}", flush=True)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    shards, new = [], 0
    for path in sorted(pages):
        md = pages[path]["md"]
        fn = out / (path.strip("/").replace("/", "__") or "index")
        fn.with_suffix(".md").write_text(md, encoding="utf-8")
        title = title_of(md, path)
        parts = [md[i:i + PART] for i in range(0, len(md), PART)] or [""]
        for k, body in enumerate(parts, 1):
            # No fetch timestamp in the body: capture dedupes by content hash, and a stamp made every
            # re-crawl look new (110 duplicate shards on 9/13/2026). Fetch time lives in the manifest.
            head = f"SOURCE: {BASE}{path}\nMARKDOWN: {pages[path]['md_url']}\nPART: {k}/{len(parts)}\n\n"
            r = capture("doc-page", f"{title}" + (f" (part {k}/{len(parts)})" if len(parts) > 1 else ""), head + body,
                        tags=["adobe-docs", a.slug, *[s for s in path.strip("/").split("/")[1:3] if s]],
                        domain_key=a.domain, source_uri=f"{BASE}{path}")
            new += bool(isinstance(r, dict) and r.get("reason") == "written")
            shards.append({"path": path, "part": k, "shard": r.get("shard_id") if isinstance(r, dict) else None,
                           "db": r.get("db_index") if isinstance(r, dict) else None})
    # Merge into the slug's manifest (a narrower re-crawl must not erase a wider one's entries)
    mf = out / "_manifest.json"
    old = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
    merged = {(e["path"], e["part"]): e for e in old.get("index", [])}
    for e in shards:
        merged[(e["path"], e["part"])] = {**e, "fetched_utc": stamp}
    runs = old.get("runs", []) + [{"start": a.start, "scope": a.scope, "fetched_utc": stamp, "pages": len(pages), "new_shards": new}]
    have = {p for p, _ in merged}
    manifest = {"domain": a.domain, "runs": runs, "pages": len(have), "shards": len(merged),
                "new_shards": new, "missing": sorted((set(old.get("missing", [])) | set(missing)) - have),  # fetched pages leave the list
                "index": [merged[k] for k in sorted(merged)]}
    mf.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("pages", "shards", "new_shards")} | {"missing": len(missing), "dir": str(out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

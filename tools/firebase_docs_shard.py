"""Crawl firebase.google.com/docs via its Markdown sources and shard every section.

Sibling of adobe_docs_shard.py. Firebase's devsite serves each page's Markdown at `<path>.md.txt`, so no
HTML scraping is needed. Pages are seeded from the site's sitemap (robots.txt allows /docs/ and names
it), filtered to the scope prefixes, fetched with modest concurrency, cached under canon/firebase-docs/,
and captured one shard per `##` section under domain_key `firebase-docs`. Re-runs are idempotent:
capture dedupes by content hash, and the fetch date lives in the manifest, not the shard body.

  pythonw firebase_docs_shard.py            # default scope (auth, admin, firestore, rules, app-check, emulators)
  python  firebase_docs_shard.py --prefix /docs/auth/web/ --max 50
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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

# Keep an explicitly configured absolute vault (tenant/isolated installs); a missing or relative value
# would resolve against cwd (the stray-.vault trap), so fall back to the canonical absolute path.
if not os.path.isabs(os.environ.get("NOUGEN_VAULT_DIR", "")):
    os.environ["NOUGEN_VAULT_DIR"] = str(Path.home() / ".nougen" / "shards")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from nougen_shards.core import capture  # noqa: E402
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = "https://firebase.google.com"
UA = {"User-Agent": "Mozilla/5.0 (NouGen docs sharder)"}
PART = 12000
SCOPE = [  # priority order from the brief
    "/docs/auth/web/", "/docs/auth/admin/", "/docs/auth/", "/docs/admin/", "/docs/reference/admin/node/firebase-admin.auth",
    "/docs/firestore/", "/docs/rules/", "/docs/app-check/", "/docs/emulator-suite/",
    "/docs/hosting/frameworks/nextjs", "/docs/app-hosting/", "/docs/web/setup", "/docs/web/learn-more",
]
SEEDS = ["/docs/auth/web/start", "/docs/auth/web/password-auth", "/docs/auth/web/google-signin", "/docs/auth/web/manage-users",
         "/docs/auth/web/email-link-auth", "/docs/auth/admin/verify-id-tokens", "/docs/auth/admin/custom-claims",
         "/docs/auth/admin/manage-sessions", "/docs/auth/admin/manage-cookies", "/docs/admin/setup", "/docs/firestore",
         "/docs/firestore/security/get-started", "/docs/firestore/security/rules-structure", "/docs/firestore/manage-data/transactions",
         "/docs/firestore/manage-data/data-types", "/docs/firestore/query-data/indexing", "/docs/firestore/data-model",
         "/docs/rules", "/docs/app-check", "/docs/app-check/web/recaptcha-enterprise-provider", "/docs/emulator-suite",
         "/docs/emulator-suite/connect_auth", "/docs/emulator-suite/connect_firestore", "/docs/app-hosting",
         "/docs/hosting/frameworks/nextjs", "/docs/web/setup"]
SKIP = ("/docs/auth/android", "/docs/auth/ios", "/docs/auth/flutter", "/docs/auth/unity", "/docs/auth/cpp",
        "/docs/app-check/android", "/docs/app-check/ios", "/docs/app-check/flutter", "/docs/app-check/unity",
        "/docs/app-check/cpp", "/docs/firestore/solutions/", "/docs/firestore/enterprise/", "/docs/reference/")


def retry_after(value: str | None, default: float) -> float:
    """Seconds to wait from a Retry-After header (delta-seconds or HTTP-date), capped at 120."""
    try:
        return min(max(float(value), 0), 120)
    except (TypeError, ValueError):
        pass
    try:
        when = parsedate_to_datetime(value)
        return min(max((when - datetime.now(timezone.utc)).total_seconds(), 0), 120)
    except (TypeError, ValueError):
        return default


def fetch(url: str) -> str | None:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return None
            if e.code == 429:  # 24 pages lost to 429s on the 2026-10-26 re-run; honour Retry-After
                time.sleep(retry_after(e.headers.get("Retry-After"), 20 * (attempt + 1)))
                continue
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(1 + 2 * attempt)
    return None


def sitemap_paths() -> list[str]:
    seen, todo, out = set(), [BASE + "/sitemap.xml"], []
    while todo:
        u = todo.pop()
        if u in seen:
            continue
        seen.add(u)
        xml = fetch(u) or ""
        for loc in re.findall(r"<loc>([^<]+)</loc>", xml):
            loc = loc.strip().replace("&amp;", "&")
            if loc.endswith(".xml"):
                todo.append(loc)
            elif loc.startswith(BASE + "/docs/") and "hl=" not in loc:
                out.append(loc[len(BASE):].split("?")[0].split("#")[0])
    return sorted(set(out))


LINK = re.compile(r"\]\((?:https://firebase\.google\.com)?(/docs/[^)\s#?]+)")


def crawl_links(prefixes: list[str], cap: int) -> list[str]:
    seeds = [x.rstrip("/") for x in prefixes + SEEDS if in_scope(x, prefixes) or x in prefixes]
    seen, frontier, found = set(seeds), list(seeds), []
    with ThreadPoolExecutor(4) as ex:
        while frontier and len(found) < cap * 2:
            batch, frontier = frontier[:16], frontier[16:]
            for p, md in zip(batch, ex.map(lambda q: fetch(BASE + q + ".md.txt"), batch)):
                if not md or md.lstrip().lower().startswith("<!doctype"):
                    continue
                found.append(p)
                for m in LINK.finditer(md):
                    n = m.group(1).rstrip("/")
                    if n not in seen and in_scope(n + "/", prefixes) or (n not in seen and in_scope(n, prefixes)):
                        seen.add(n)
                        frontier.append(n)
            time.sleep(0.5)
    return found


def in_scope(p: str, prefixes: list[str]) -> bool:
    return any(p.startswith(x) for x in prefixes) and not any(p.startswith(s) for s in SKIP)


def sections(md: str) -> list[tuple[str, str]]:
    """Split on `## ` headings; text before the first heading is the page intro."""
    chunks, head, buf = [], "Overview", []
    for line in md.splitlines():
        if line.startswith("## "):
            if "".join(buf).strip():
                chunks.append((head, "\n".join(buf).strip()))
            head, buf = line[3:].strip(), [line]
        else:
            buf.append(line)
    if "".join(buf).strip():
        chunks.append((head, "\n".join(buf).strip()))
    return chunks


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefix", action="append", help="override scope prefix (repeatable)")
    ap.add_argument("--max", type=int, default=600)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--domain", default="firebase-docs")
    a = ap.parse_args(argv)
    prefixes = a.prefix or SCOPE
    out = ROOT / "canon" / "firebase-docs"
    (out / "pages").mkdir(parents=True, exist_ok=True)

    paths = [p for p in sitemap_paths() if in_scope(p, prefixes)]
    if not paths:  # sitemap_N_of_2.xml answered 500 on 2026-10-25: fall back to following .md.txt links
        print("  sitemap gave nothing; link-following from scope seeds", flush=True)
        paths = crawl_links(prefixes, a.max)
    paths.sort(key=lambda p: next((i for i, x in enumerate(prefixes) if (p + "/").startswith(x) or p.startswith(x)), len(prefixes)))
    paths = paths[: a.max]
    print(f"  {len(paths)} in-scope pages from sitemap", flush=True)

    def get(p):
        time.sleep(0.25)  # be polite: ~4 req/s ceiling at 4 workers
        return p, fetch(BASE + p.rstrip("/") + ".md.txt")

    pages, missing = {}, []
    with ThreadPoolExecutor(a.workers) as ex:
        for i, (p, md) in enumerate(ex.map(get, paths), 1):
            (pages.__setitem__(p, md) if md and not md.lstrip().lower().startswith("<!doctype") else missing.append(p))
            if i % 25 == 0:
                print(f"  fetched {i}/{len(paths)}", flush=True)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    index, new = [], 0
    for p in sorted(pages):
        md = pages[p]
        (out / "pages" / (p.strip("/").replace("/", "__") + ".md")).write_text(md, encoding="utf-8")
        page_title = " / ".join(p.strip("/").split("/")[1:])
        tags = ["firebase-docs", *[s for s in p.strip("/").split("/")[1:3] if s]]
        for n, (head, body) in enumerate(sections(md), 1):
            parts = [body[i:i + PART] for i in range(0, len(body), PART)]
            for k, chunk in enumerate(parts, 1):
                title = f"Firebase {page_title} — {head}" + (f" (part {k}/{len(parts)})" if len(parts) > 1 else "")
                text = f"SOURCE: {BASE}{p}\nSECTION: {head}\n\n{chunk}"
                r = capture("doc-section", title[:200], text, tags=tags, domain_key=a.domain, source_uri=f"{BASE}{p}")
                new += bool(isinstance(r, dict) and r.get("reason") == "written")
                index.append({"path": p, "section": n, "part": k, "heading": head,
                              "shard": r.get("shard_id") if isinstance(r, dict) else None,
                              "db": r.get("db_index") if isinstance(r, dict) else None, "fetched_utc": stamp})
    mf = out / "_manifest.json"
    old = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
    merged = {(e["path"], e["section"], e["part"]): e for e in old.get("index", [])}
    merged.update({(e["path"], e["section"], e["part"]): e for e in index})
    manifest = {"domain": a.domain, "runs": old.get("runs", []) + [{"fetched_utc": stamp, "pages": len(pages), "new_shards": new}],
                "pages": len({k[0] for k in merged}), "shards": len(merged), "missing": missing,
                "index": [merged[k] for k in sorted(merged)]}
    mf.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"pages": len(pages), "shards": len(merged), "new_shards": new, "missing": len(missing), "dir": str(out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

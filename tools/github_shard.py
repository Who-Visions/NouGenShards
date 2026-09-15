"""Shard a GitHub repo's documentation: every Markdown file (plus optional code globs) via the gh CLI.

Walks the repo tree at HEAD (gh api .../git/trees/HEAD?recursive=1), fetches each matching file raw,
saves it under canon/<slug>/<owner>__<repo>/..., and captures one NouGen shard per file (split at 12k
chars). The index shard lists every file plus repo facts (license, default branch, description).
No fetch stamp in shard bodies, so re-runs dedupe; manifest merges across runs. Also reports the
other GitHub repos the docs link to, for the next level of recursion.

  python github_shard.py ollama/ollama ollama/ollama-python --domain ollama-github --slug ollama-github \
      --include "*.md" --include "examples/*.py"
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("NOUGEN_VAULT_DIR", r"C:\Users\super\.nougen\shards")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from nougen_shards.core import capture  # noqa: E402
for _s in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252; never crash printing model output
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PART = 12000
NO_WINDOW = 0x08000000


def gh(*args: str) -> str:
    r = subprocess.run(["gh", "api", *args], capture_output=True, text=True, encoding="utf-8", timeout=120,
                       creationflags=NO_WINDOW if os.name == "nt" else 0)
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[:300])
    return r.stdout


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repos", nargs="+", help="owner/name")
    ap.add_argument("--domain", required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--include", action="append", default=[], help="glob on repo path (repeatable); default *.md")
    ap.add_argument("--exclude", action="append", default=[], help="glob to skip (vendored code, changelogs…)")
    ap.add_argument("--max-files", type=int, default=400)
    a = ap.parse_args(argv)
    inc = a.include or ["*.md"]
    exc = a.exclude + ["*/node_modules/*", "*/vendor/*", "*/third_party/*", "*/testdata/*", "*CHANGELOG*"]
    out = ROOT / "canon" / a.slug
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows, linked = [], Counter()
    for repo in a.repos:
        meta = json.loads(gh(f"repos/{repo}"))
        tree = json.loads(gh(f"repos/{repo}/git/trees/{meta['default_branch']}?recursive=1")).get("tree", [])
        files = sorted(t["path"] for t in tree if t["type"] == "blob"
                       and any(fnmatch.fnmatch(t["path"], g) or fnmatch.fnmatch(t["path"].split("/")[-1], g) for g in inc)
                       and not any(fnmatch.fnmatch(t["path"], g) for g in exc))[: a.max_files]
        base = out / repo.replace("/", "__")

        def get(path: str):
            try:
                return path, gh(f"repos/{repo}/contents/{path}?ref={meta['default_branch']}", "-H", "Accept: application/vnd.github.raw")
            except Exception as e:
                return path, e

        new = 0
        with ThreadPoolExecutor(6) as ex:
            got = list(ex.map(get, files))
        for path, body in got:
            if isinstance(body, Exception):
                rows.append({"repo": repo, "path": path, "error": str(body)[:120]})
                continue
            dst = base / path
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(body, encoding="utf-8")
            for m in re.findall(r"github\.com/([\w.-]+/[\w.-]+)", body):
                if m.lower() != repo.lower():
                    linked[m.rstrip(".").removesuffix(".git")] += 1
            title = next((l.lstrip("# ").strip() for l in body.splitlines() if l.startswith("#") and l.lstrip("# ").strip()), path)[:100]
            parts = [body[i:i + PART] for i in range(0, len(body), PART)] or [""]
            url = f"https://github.com/{repo}/blob/{meta['default_branch']}/{path}"
            for k, part in enumerate(parts, 1):
                r = capture("doc-page", f"{repo}: {path} — {title}" + (f" (part {k}/{len(parts)})" if len(parts) > 1 else ""),
                            f"SOURCE: {url}\nREPO: {repo} ({(meta.get('license') or {}).get('spdx_id', 'no license')})\nPART: {k}/{len(parts)}\n\n{part}",
                            tags=["github-docs", a.slug, repo.split("/")[1]], domain_key=a.domain, source_uri=url)
                new += isinstance(r, dict) and r.get("reason") == "written"
                rows.append({"repo": repo, "path": path, "part": k, "shard": r.get("shard_id") if isinstance(r, dict) else None,
                             "db": r.get("db_index") if isinstance(r, dict) else None, "fetched_utc": stamp})
        idx = capture("doc-index", f"INDEX: github.com/{repo} docs ({len(files)} files)",
                      f"REPO: https://github.com/{repo}\nDESCRIPTION: {meta.get('description')}\nLICENSE: {(meta.get('license') or {}).get('spdx_id')}\n"
                      f"DEFAULT BRANCH: {meta['default_branch']}\nSTARS: {meta.get('stargazers_count')}\nINCLUDED: {', '.join(inc)}\n\nFILES:\n" + "\n".join(files),
                      tags=["github-docs", a.slug, "index"], domain_key=a.domain, source_uri=f"https://github.com/{repo}")
        print(json.dumps({"repo": repo, "license": (meta.get("license") or {}).get("spdx_id"), "files": len(files), "new_shards": new,
                          "index_shard": idx.get("shard_id") if isinstance(idx, dict) else None}), flush=True)
    mf = out / "_manifest.json"
    old = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
    # A slug may already hold a docs-crawler manifest (entries keyed by "path", no "repo"): keep those rows untouched.
    foreign = [e for e in old.get("index", []) if "repo" not in e]
    merged = {(e["repo"], e["path"], e.get("part", 0)): e for e in old.get("index", []) if "repo" in e}
    merged.update({(e["repo"], e["path"], e.get("part", 0)): e for e in rows})
    man = {**{k: v for k, v in old.items() if k not in ("index", "repos", "files", "shards", "linked_repos")},
           "domain": a.domain, "repos": sorted(set(old.get("repos", [])) | set(a.repos)), "files": len({(r, p) for r, p, _ in merged}),
           "shards": sum(1 for e in merged.values() if e.get("shard")), "linked_repos": dict(Counter(old.get("linked_repos", {})) + linked),
           "index": foreign + [merged[k] for k in sorted(merged)]}
    out.mkdir(parents=True, exist_ok=True)
    mf.write_text(json.dumps(man, indent=2), encoding="utf-8")
    print("linked repos (next recursion level):", ", ".join(f"{k} x{v}" for k, v in linked.most_common(15)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

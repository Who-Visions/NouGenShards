"""Shard OpenAPI / Swagger specs one operation per shard (docs truth for API references).

Adobe's API reference pages are Redoc renders of a spec file; the prose crawl (adobe_docs_shard.py)
only sees the page shell. This fetches each spec (JSON or YAML, OpenAPI 2 or 3), saves it under
canon/<slug>/specs/, and captures: one index shard per spec (every operation) plus one shard per
operation (summary, description, parameters, request body with $refs resolved one level, responses).
Idempotent: no fetch stamp in shard bodies, so re-runs dedupe by content hash.

  python adobe_spec_shard.py --slug adobe-firefly-docs --domain adobe-firefly-services-docs \
      https://developer.adobe.com/firefly-services/docs/photoshop/photoshopv2-api.json ...
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
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

UA = {"User-Agent": "Mozilla/5.0 (NouGen spec sharder)"}
METHODS = ("get", "post", "put", "patch", "delete", "head")


def load(url: str) -> tuple[bytes, dict]:
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
    if url.endswith((".yaml", ".yml")) or not raw.lstrip().startswith(b"{"):
        import yaml
        return raw, yaml.safe_load(raw)
    return raw, json.loads(raw)


def deref(spec: dict, node, depth: int = 2):
    """Resolve local $refs a couple of levels deep so a shard is readable on its own."""
    if depth < 0:
        return node
    if isinstance(node, dict):
        if "$ref" in node and isinstance(node["$ref"], str) and node["$ref"].startswith("#/"):
            cur = spec
            for part in node["$ref"][2:].split("/"):
                cur = cur.get(part.replace("~1", "/").replace("~0", "~"), {}) if isinstance(cur, dict) else {}
            return {"$ref": node["$ref"], **deref(spec, cur, depth - 1)} if isinstance(cur, dict) else cur
        return {k: deref(spec, v, depth) for k, v in node.items()}
    if isinstance(node, list):
        return [deref(spec, v, depth) for v in node]
    return node


def clip(obj, n: int) -> str:
    s = json.dumps(obj, indent=1, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + f"\n… (truncated, {len(s):,} chars; full spec in canon)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--domain", required=True)
    a = ap.parse_args(argv)
    a.urls = [u.strip() for u in a.urls if u.strip()]  # CRLF lists from Windows files gave 'x.json<CR>' (9/13/2026)
    out = ROOT / "canon" / a.slug / "specs"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = []
    for url in a.urls:
        try:
            raw, spec = load(url)
        except Exception as e:
            report.append({"url": url, "error": f"{type(e).__name__}: {e}"})
            continue
        (out / url.rstrip("/").split("/")[-1]).write_bytes(raw)
        info = spec.get("info", {})
        title = f"{info.get('title', url.split('/')[-1])} {info.get('version', '')}".strip()
        servers = [s.get("url") for s in spec.get("servers", [])] or [spec.get("host", "") + spec.get("basePath", "")]
        ops, new = [], 0
        for path, item in sorted((spec.get("paths") or {}).items()):
            for method in METHODS:
                op = item.get(method)
                if not isinstance(op, dict):
                    continue
                ops.append(f"{method.upper()} {path} — {op.get('summary', '')}")
                params = deref(spec, (item.get("parameters") or []) + (op.get("parameters") or []))
                body = (f"SPEC: {title}\nSOURCE: {url}\nSERVERS: {', '.join(filter(None, servers))}\n\n"
                        f"{method.upper()} {path}\nOPERATION ID: {op.get('operationId', '')}\nSUMMARY: {op.get('summary', '')}\n"
                        f"TAGS: {', '.join(op.get('tags', []))}\nSECURITY: {json.dumps(op.get('security', spec.get('security', [])))}\n\n"
                        f"DESCRIPTION:\n{op.get('description', '')}\n\nPARAMETERS:\n{clip(params, 5000)}\n\n"
                        f"REQUEST BODY:\n{clip(deref(spec, op.get('requestBody', {})), 9000)}\n\n"
                        f"RESPONSES:\n{clip({k: (v.get('description') if isinstance(v, dict) else v) for k, v in (op.get('responses') or {}).items()}, 2000)}")
                r = capture("api-operation", f"{title}: {method.upper()} {path}", body,
                            tags=["adobe-docs", "openapi", a.slug, *[re.sub(r'\W+', '-', t.lower()) for t in op.get("tags", [])[:2]]],
                            domain_key=a.domain, source_uri=f"{url}#{method.upper()} {path}")
                new += isinstance(r, dict) and r.get("reason") == "written"
        schemas = spec.get("definitions") or (spec.get("components") or {}).get("schemas") or {}
        idx = capture("api-index", f"INDEX: {title} ({len(ops)} operations)",
                      f"SPEC: {title}\nSOURCE: {url}\nSERVERS: {', '.join(filter(None, servers))}\nLICENSE: {(info.get('license') or {}).get('name', '')}\n"
                      f"SCHEMAS: {len(schemas)}\n\nDESCRIPTION:\n{info.get('description', '')[:3000]}\n\nOPERATIONS:\n" + "\n".join(ops),
                      tags=["adobe-docs", "openapi", "index", a.slug], domain_key=a.domain, source_uri=url)
        report.append({"url": url, "title": title, "operations": len(ops), "new_op_shards": new, "schemas": len(schemas),
                       "index_shard": idx.get("shard_id") if isinstance(idx, dict) else None})
    mf = out / "_specs_manifest.json"
    old = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {"specs": {}}
    for r in report:
        old["specs"][r["url"]] = {**r, "fetched_utc": stamp}
    mf.write_text(json.dumps(old, indent=2), encoding="utf-8")
    for r in report:
        print(json.dumps(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())

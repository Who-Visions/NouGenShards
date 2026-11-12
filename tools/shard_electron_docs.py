"""Shard the Electron docs (electron/electron, docs/) into the NouGen vault, one shard per page.

Each page is captured whole under domain_key `electron-docs`, title = its first H1. Capture dedupes by content
hash, so re-runs are idempotent. The vault is set explicitly: the default resolution can silently land in a stray
local .vault (shards memory, Rule 0.0 / vault cwd trap).

  python tools/shard_electron_docs.py canon/electron-docs/docs            # capture all pages
  python tools/shard_electron_docs.py canon/electron-docs/docs --dry-run  # count only
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("NOUGEN_VAULT_DIR", str(Path.home() / ".nougen" / "shards"))
sys.path.insert(0, str(ROOT / "src"))

DOMAIN = "electron-docs"
MAX_CHARS = 60000


def _title(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return (m.group(1).strip() if m else fallback)[:200]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docs", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pages = sorted(args.docs.rglob("*.md"))
    if not pages:
        print(f"no markdown under {args.docs}")
        return 1

    if args.dry_run:
        print(f"{len(pages)} pages under {args.docs} would be captured as domain {DOMAIN}")
        return 0

    from nougen_shards import core  # noqa: E402  (after the sys.path insert above)

    captured = failed = 0
    for page in pages:
        try:
            text = page.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            failed += 1
            print(f"[!] {page}: {e}")
            continue
        rel = page.relative_to(args.docs).as_posix()
        title = _title(text, rel)
        body = f"SOURCE: electron/electron docs/{rel}\n\n{text[:MAX_CHARS]}"
        try:
            res = core.capture("doc", title, body, domain_key=DOMAIN)
            if (res and res.get("shard_id")) or (isinstance(res, dict) and res.get("reason") == "duplicate"):
                captured += 1
            else:
                failed += 1
                print(f"[!] {rel}: {res}")
        except Exception as e:  # keep going; one bad page should not stop the run
            failed += 1
            print(f"[!] {rel}: {e}")

    print(f"electron-docs: captured or already present {captured}, failed {failed}, pages {len(pages)}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Ground-truth vendor pricing straight from the official docs URI.

Model prices are the most volatile fact in this system and the one an agent is
most likely to "remember" wrongly. This pulls them live from the vendor's own
pricing page, so the meter is grounded in the published table rather than in
anybody's memory of it.

Two page shapes are supported, chosen per source:

  sections  A heading per model, a sub-heading per tier, rows labelled
            "Input price" / "Output price".            (ai.google.dev)
  matrix    One table, one row per model, prices in named columns.
            (platform.claude.com)

Dated increases ("$0.75 through December 31, 2026. $1.50 starting January 1,
2027.") are preserved as a schedule rather than flattened, so the resolver in
billing.py can pick the price actually in force on a given day.

Sources live in data/pricing/sources.json (override with NOUGEN_PRICING_SOURCES)
so adding a provider is configuration, not a code change.

Usage:
    python tools/import_pricing.py                 # refresh every configured source
    python tools/import_pricing.py --provider google
    python tools/import_pricing.py --provider anthropic --url <override>
    python tools/import_pricing.py --source scraped.md --provider google
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SOURCES = {
    "google": {
        "url": "https://ai.google.dev/gemini-api/docs/pricing",
        "shape": "sections",
        "tier": "Standard",
        "unit": "USD per 1M tokens",
    },
    "anthropic": {
        "url": "https://platform.claude.com/docs/en/about-claude/pricing",
        "shape": "matrix",
        "unit": "USD per 1M tokens",
        "columns": {
            "input": "Base Input Tokens",
            "output": "Output Tokens",
            "cache_read": "Cache Hits & Refreshes",
            "cache_write_5m": "5m Cache Writes",
            "cache_write_1h": "1h Cache Writes",
        },
    },
}

FETCH_TIMEOUT_S = float(os.environ.get("NOUGEN_PRICING_TIMEOUT_S", "30"))
USER_AGENT = os.environ.get("NOUGEN_PRICING_UA", "NouGenShards-pricing-importer/1.0")

_PRICE = re.compile(r"\$\s*([0-9][0-9,]*\.?[0-9]*)")
_STARTING = re.compile(
    r"\$\s*([0-9][0-9,]*\.?[0-9]*)\s*starting\s+([A-Z][a-z]+\s+\d{1,2},\s*\d{4})"
)
_MD_H2 = re.compile(r"^##\s+(.+?)\s*$")
_MD_H3 = re.compile(r"^###\s+(.+?)\s*$")
_MD_ROW = re.compile(r"^\|\s*(Input price|Output price)[^|]*\|([^|]*)\|([^|]*)\|")


# --------------------------------------------------------------------------
# fetching / html
# --------------------------------------------------------------------------

def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, "replace")


class _DocParser(HTMLParser):
    """Collects tables (as cell-text rows) and the heading in force above each."""

    HEADINGS = {"h1", "h2", "h3", "h4"}

    # Pages that price the same models at several service tiers label them in
    # running text rather than in headings. Track the last one seen so a parse
    # can select a tier instead of grabbing whichever table came first.
    TIER_WORDS = ("Standard", "Batch", "Priority", "Flex", "Scale")

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict] = []
        self._last_tier: str | None = None
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._heading_tag: str | None = None
        self._heading_buf: list[str] = []
        self.headings: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag in self.HEADINGS:
            self._heading_tag = tag
            self._heading_buf = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)
        elif self._heading_tag:
            self._heading_buf.append(data)
        elif self._table is None:
            text = data.strip()
            if text in self.TIER_WORDS:
                self._last_tier = text

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(c for c in self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append({
                    "rows": self._table,
                    "headings": dict(self.headings),
                    "tier": self._last_tier,
                })
            self._table = None
        elif tag in self.HEADINGS and self._heading_tag == tag:
            text = " ".join("".join(self._heading_buf).split())
            if text:
                self.headings[tag] = text
                # A new heading invalidates deeper ones (h2 resets h3/h4).
                for deeper in ("h2", "h3", "h4"):
                    if deeper > tag:
                        self.headings.pop(deeper, None)
            self._heading_tag = None


# --------------------------------------------------------------------------
# value parsing
# --------------------------------------------------------------------------

def slug(name: str) -> str:
    ascii_name = name.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"\(.*?\)", " ", ascii_name)
    return re.sub(r"[^a-z0-9.]+", "-", ascii_name.lower()).strip("-")


def parse_cell(cell: str):
    """(price_now, (effective_date_iso, price_then)) — None when not priced."""
    text = (cell or "").strip()
    low = text.lower()
    if not text or low.startswith("not available") or low in {"n/a", "-", "—"}:
        return None, None
    if low.startswith("free of charge") or low == "free":
        return 0.0, None

    future = None
    sched = _STARTING.search(text)
    if sched:
        when = datetime.strptime(sched.group(2).replace(",", ""), "%B %d %Y").date()
        future = (when.isoformat(), float(sched.group(1).replace(",", "")))

    found = _PRICE.findall(text)
    if not found:
        return None, future
    return float(found[0].replace(",", "")), future


def _record(models: dict, name: str, kind: str, cell: str) -> None:
    price, future = parse_cell(cell)
    if price is None:
        return
    entry = models.setdefault(slug(name), {"display_name": name})
    entry[kind] = price
    if future:
        when, amount = future
        entry.setdefault("schedule", {}).setdefault(when, {})[kind] = amount


# --------------------------------------------------------------------------
# shapes
# --------------------------------------------------------------------------

def parse_sections_markdown(md: str, tier: str) -> dict:
    models: dict = {}
    model = current_tier = None
    for line in md.splitlines():
        h2 = _MD_H2.match(line)
        if h2:
            model, current_tier = h2.group(1), None
            continue
        h3 = _MD_H3.match(line)
        if h3:
            current_tier = h3.group(1)
            continue
        if not model or current_tier != tier:
            continue
        row = _MD_ROW.match(line)
        if row:
            kind = "input" if row.group(1) == "Input price" else "output"
            _record(models, model, kind, row.group(3))
    return models


def parse_sections_html(doc: _DocParser, tier: str) -> dict:
    models: dict = {}
    for table in doc.tables:
        heads = table["headings"]
        model, current_tier = heads.get("h2"), heads.get("h3")
        if not model or (tier and current_tier != tier):
            continue
        for row in table["rows"]:
            if not row:
                continue
            label = row[0]
            if label.startswith("Input price"):
                kind = "input"
            elif label.startswith("Output price"):
                kind = "output"
            else:
                continue
            # Paid tier is the last column; free tier sits before it.
            _record(models, model, kind, row[-1])
    return models


def parse_matrix_html(doc: _DocParser, columns: dict, tier: str | None = None) -> dict:
    """One row per model, prices in named columns.

    The header is located by content, not by position: some pages stack a
    spanning group header ('', 'Short context', 'Long context') above the real
    one, so row 0 is not reliably the header.
    """
    models: dict = {}
    wanted = {v: k for k, v in columns.items()}
    for table in doc.tables:
        rows = table["rows"]
        if len(rows) < 2:
            continue
        if tier and table.get("tier") and table["tier"] != tier:
            continue

        header_i, idx = None, {}
        for i, row in enumerate(rows[:3]):
            found = {wanted[h]: j for j, h in enumerate(row) if h in wanted}
            if "input" in found and "output" in found:
                header_i, idx = i, found
                break
        if header_i is None:
            continue

        for row in rows[header_i + 1:]:
            if len(row) <= max(idx.values()):
                continue
            name = row[0]
            # Continuation rows (e.g. a second modality) carry a price, not a name.
            if not name or _PRICE.search(name):
                continue
            for kind, i in idx.items():
                _record(models, name, kind, row[i])
    return models


def parse_json_api(text: str, cfg: dict) -> dict:
    """Provider JSON catalogues (e.g. OpenRouter /api/v1/models).

    Prices there are per-token strings; normalise to per-1M so every table in
    data/pricing shares one unit.
    """
    doc = json.loads(text)
    items = doc.get(cfg.get("items_key", "data"), doc if isinstance(doc, list) else [])
    fields = cfg.get("fields", {"input": "prompt", "output": "completion"})
    scale = float(cfg.get("scale", 1_000_000))

    models: dict = {}
    for item in items:
        ident = item.get(cfg.get("id_key", "id"))
        pricing = item.get(cfg.get("pricing_key", "pricing")) or {}
        if not ident or not isinstance(pricing, dict):
            continue
        entry = {"display_name": item.get("name") or ident}
        for kind, key in fields.items():
            try:
                value = float(pricing.get(key))
            except (TypeError, ValueError):
                continue
            if value < 0:  # -1 marks "varies"/unpriced on some catalogues
                continue
            entry[kind] = round(value * scale, 6)
        if "input" in entry and "output" in entry:
            models[slug(ident)] = entry
    return models


# --------------------------------------------------------------------------

def load_sources() -> dict:
    override = os.environ.get("NOUGEN_PRICING_SOURCES")
    path = Path(override) if override else REPO_ROOT / "data" / "pricing" / "sources.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[!] {path.name} unreadable ({exc}); using built-in sources.", file=sys.stderr)
    return DEFAULT_SOURCES


def build(provider: str, cfg: dict, text: str, origin: str) -> dict:
    shape = cfg.get("shape", "sections")
    looks_html = "<table" in text.lower()

    if shape == "sections":
        models = (parse_sections_html(_feed(text), cfg.get("tier", "Standard"))
                  if looks_html else
                  parse_sections_markdown(text, cfg.get("tier", "Standard")))
    elif shape == "matrix":
        models = parse_matrix_html(_feed(text), cfg.get("columns", {}), cfg.get("tier"))
    elif shape == "json_api":
        models = parse_json_api(text, cfg)
    else:
        raise ValueError(f"unknown shape {shape!r} for provider {provider!r}")

    # Drop partials: a model priced on input alone would misprice completions.
    models = {k: v for k, v in models.items() if "input" in v and "output" in v}
    return {
        "provider": provider,
        "source": origin,
        "shape": shape,
        "tier": cfg.get("tier"),
        "unit": cfg.get("unit", "USD per 1M tokens"),
        "imported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "models": models,
    }


def _feed(html_text: str) -> _DocParser:
    parser = _DocParser()
    parser.feed(html_text)
    return parser


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", default=None, help="Refresh one provider (default: all)")
    ap.add_argument("--url", default=None, help="Override the configured URL")
    ap.add_argument("--source", type=Path, default=None,
                    help="Parse a local scrape instead of fetching")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="Output directory (default: data/pricing)")
    args = ap.parse_args(argv)

    sources = load_sources()
    if args.provider:
        if args.provider not in sources:
            print(f"[X] unknown provider {args.provider!r}. Known: {', '.join(sorted(sources))}",
                  file=sys.stderr)
            return 1
        sources = {args.provider: sources[args.provider]}
    elif args.url or args.source:
        print("[X] --url/--source require --provider.", file=sys.stderr)
        return 1

    out_dir = args.out_dir or (REPO_ROOT / "data" / "pricing")
    out_dir.mkdir(parents=True, exist_ok=True)

    failures = 0
    for provider, cfg in sources.items():
        # A source whose parse isn't trusted yet stays configured but unshipped,
        # so a wrong price never silently reaches the meter.
        if cfg.get("enabled") is False and not args.provider:
            print(f"[--] {provider}: disabled ({cfg.get('note', 'no reason given')})")
            continue
        try:
            if args.source:
                text = args.source.read_text(encoding="utf-8", errors="replace")
                origin = str(args.source)
            else:
                origin = args.url or cfg["url"]
                text = fetch(origin)
            doc = build(provider, cfg, text, origin)
        except Exception as exc:  # network, parse, config — report and keep going
            print(f"[X] {provider}: {type(exc).__name__}: {exc}", file=sys.stderr)
            failures += 1
            continue

        if not doc["models"]:
            print(f"[X] {provider}: no prices parsed from {origin} — page shape may have changed.",
                  file=sys.stderr)
            failures += 1
            continue

        path = out_dir / f"{provider}.json"
        path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        scheduled = sum(1 for m in doc["models"].values() if m.get("schedule"))
        print(f"[OK] {provider}: {len(doc['models'])} models -> {path.name}"
              + (f" ({scheduled} with dated changes)" if scheduled else ""))

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

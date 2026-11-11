"""Ground-truth vendor pricing straight from the official docs URI.

Model prices are the most volatile fact in this system and the one an agent is
most likely to "remember" wrongly. This pulls them live from the vendor's own
pricing page, so the meter is grounded in the published table rather than in
anybody's memory of it.

Page shapes supported (chosen per source):

  sections  A heading per model with Markdoc {% table %} / {% tabs %} or HTML
            tables, rows labelled "Input price" / "Output price"  (ai.google.dev)
  matrix    One table, one row per model, prices in named columns
            (HTML or Markdown pipe table).                       (platform.claude.com)
  json_api  Provider JSON catalog (e.g. OpenRouter /api/v1/models).

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
import html as html_lib
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, date
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
_DATE_CLAUSE = re.compile(
    r"\b(through|starting|effective|after|from)\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
    re.IGNORECASE,
)
_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

# Column header synonym aliases for matrix tables (all lowercase normalized)
_MATRIX_COL_ALIASES = {
    "input": ("base input tokens", "input", "short context input"),
    "output": ("output tokens", "output", "short context output"),
    "cache_read": (
        "cache hits & refreshes",
        "cache hits and refreshes",
        "hits and refreshes",
        "hits & refreshes",
        "cached input",
    ),
    "cache_write_5m": ("5m cache writes", "5m writes"),
    "cache_write_1h": ("1h cache writes", "1h writes"),
}


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
    BLOCK_CELL_TAGS = {"br", "p", "div", "li"}
    TIER_WORDS = ("Standard", "Batch", "Priority", "Flex", "Scale")
    TIER_MAP = {w.lower(): w for w in TIER_WORDS}

    @classmethod
    def match_tier(cls, text: str) -> str | None:
        cleaned = " ".join((text or "").split()).strip().lower()
        if cleaned in cls.TIER_MAP:
            return cls.TIER_MAP[cleaned]
        if cleaned.endswith(" tier") and cleaned[:-5] in cls.TIER_MAP:
            return cls.TIER_MAP[cleaned[:-5]]
        return None

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict] = []
        self._last_tier: str | None = None
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._cell_breaks: list[bool] = []
        self._heading_tag: str | None = None
        self._heading_buf: list[str] = []
        self.headings: dict[str, str] = {}

    def _is_caption_inline(self, attrs: list[tuple[str, str | None]]) -> bool:
        cls_val = dict(attrs).get("class") or ""
        tokens = cls_val.lower().split()
        return any(tok in ("text-caption", "caption", "block") or tok.endswith("-caption") for tok in tokens)

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            self._cell_breaks = []
        elif tag in self.HEADINGS:
            self._heading_tag = tag
            self._heading_buf = []
        elif self._cell is not None:
            if tag in self.BLOCK_CELL_TAGS:
                self._cell.append("\n")
                if tag != "br":
                    self._cell_breaks.append(True)
            elif tag in ("span", "small", "a"):
                should_break = self._is_caption_inline(attrs)
                self._cell_breaks.append(should_break)
                if should_break:
                    self._cell.append("\n")

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)
        elif self._heading_tag:
            self._heading_buf.append(data)
        elif self._table is None:
            matched = self.match_tier(data)
            if matched:
                self._last_tier = matched

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            raw_cell = "".join(self._cell)
            lines = [" ".join(ln.split()) for ln in raw_cell.splitlines()]
            self._row.append("\n".join(ln for ln in lines if ln))
            self._cell = None
            self._cell_breaks = []
        elif self._cell is not None and tag in ("p", "div", "li", "span", "small", "a"):
            if self._cell_breaks and self._cell_breaks.pop():
                self._cell.append("\n")
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
            self._last_tier = None
        elif tag in self.HEADINGS and self._heading_tag == tag:
            text = " ".join("".join(self._heading_buf).split())
            if text:
                self.headings[tag] = text
                for deeper in ("h2", "h3", "h4"):
                    if deeper > tag:
                        self.headings.pop(deeper, None)
            self._heading_tag = None
            self._last_tier = None


# --------------------------------------------------------------------------
# value & date helpers
# --------------------------------------------------------------------------

def slug(name: str) -> str:
    ascii_name = name.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", ascii_name)
    ascii_name = re.sub(r"\(.*?\)", " ", ascii_name)
    return re.sub(r"[^a-z0-9.]+", "-", ascii_name.lower()).strip("-")


def _parse_english_date(date_str: str) -> str | None:
    if not date_str:
        return None
    cleaned = re.sub(r"\s+", " ", date_str.replace(",", " ")).strip()
    m = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2})\s+(\d{4})", cleaned)
    if not m:
        return None
    month = _MONTHS.get(m.group(1).lower())
    if not month:
        return None
    try:
        return date(int(m.group(3)), month, int(m.group(2))).isoformat()
    except ValueError:
        return None


def _clean_cell_text(raw: str) -> str:
    if not raw:
        return ""
    s = html_lib.unescape(raw)
    s = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"{%\s*/?\s*sup\s*%}.*?{%\s*/\s*sup\s*%}", " ", s, flags=re.IGNORECASE | re.DOTALL)
    s = re.sub(r"{%[^%]*%}", " ", s)
    s = re.sub(r"<sup[^>]*>[\s\S]*?</sup>", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", " ", s)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in s.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _detect_unit_multiplier(text: str) -> float | None:
    if not text:
        return None
    low = text.lower()
    if any(bad in low for bad in ("request", "query", "queries", "image", "frame", "second", "min", "hour")):
        if "token" not in low:
            return None
    has_1k = bool(
        re.search(r"/\s*(?:1\s*k|ktok|k\b|thousand)", low)
        or re.search(r"per\s+(?:1\s*k|1000|thousand)", low)
        or re.search(r"\b1k\s*tokens?\b", low)
        or (re.search(r"\b1,?000\b", low) and not re.search(r"\b1,?000,?000\b", low) and "token" in low)
    )
    has_1m = bool(
        re.search(r"/\s*(?:1\s*m|mtok|m\b|million)", low)
        or re.search(r"per\s+(?:1\s*m|1000000|million)", low)
        or re.search(r"\b1m\s*tokens?\b", low)
        or re.search(r"\b1,?000,?000\b", low)
    )
    if has_1k and has_1m:
        return None
    if has_1m:
        return 1.0
    if has_1k:
        return 1000.0
    return None


def _is_non_token_segment(seg_low: str) -> bool:
    if any(tok in seg_low for tok in (
        "storage price", "/ hour", "per hour", "equivalent to",
        "per image", "/image", "per frame", "per second", "per 10s",
        "/min", "/ min", "per min", "search request", "search quer",
        "grounded prompt", "requests per",
    )):
        return True
    if ("request" in seg_low or "quer" in seg_low) and "token" not in seg_low:
        return True
    return False


def _parse_section_paid_cell(cell_raw: str, header_unit: float | None) -> list[tuple[float, str | None, str | None]]:
    """Extract text-compatible token prices [(usd_per_1m, start_iso, end_iso), ...] from Paid Tier cell."""
    cleaned = _clean_cell_text(cell_raw)
    if not cleaned:
        return []

    normalized = re.sub(
        r"\bor\s+\$[0-9]+(?:\.[0-9]+)?\s*/\s*(?:min|10s|sec|second|image|frame|hour)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\bEquivalent to\b[^\n.]*\.?", "", normalized, flags=re.IGNORECASE)

    raw_segments = []
    for line in normalized.splitlines():
        parts = re.split(r"(?=\$[0-9])", line)
        raw_segments.extend(p.strip() for p in parts if p.strip())

    baseline_entries = []
    for seg in raw_segments:
        if "$" not in seg:
            continue
        seg_low = seg.lower()
        if _is_non_token_segment(seg_low):
            continue

        # Exclude audio/video/image-only price lines unless 'text' is explicitly part of the modality
        has_non_text = bool(re.search(r"\b(audio|video|image)\b", seg_low))
        has_text = bool(re.search(r"\btext\b", seg_low))
        if has_non_text and not has_text:
            continue

        # Skip long-context tier rows (> 200k / > 128k)
        if re.search(r">\s*200k|>\s*128k", seg_low):
            continue

        m_dollar = re.search(r"\$([0-9]+(?:\.[0-9]+)?)", seg)
        if not m_dollar:
            continue

        seg_unit = _detect_unit_multiplier(seg)
        unit = seg_unit if seg_unit is not None else header_unit
        if unit is None:
            continue

        val = float(m_dollar.group(1)) * unit
        start_iso, end_iso = None, None
        m_date = _DATE_CLAUSE.search(seg)
        if m_date:
            kw = m_date.group(1).lower()
            parsed_dt = _parse_english_date(m_date.group(2))
            if parsed_dt:
                if kw == "through":
                    end_iso = parsed_dt
                else:
                    start_iso = parsed_dt
        baseline_entries.append((val, start_iso, end_iso))

    return baseline_entries


def _find_gemini_columns(headers: list[str], *, require_feature_name: bool = True) -> tuple[int, int] | None:
    if not headers or len(headers) < 2:
        return None
    norm = [re.sub(r"\s+", " ", _clean_cell_text(h)).strip().lower() for h in headers]
    paid_matches = [i for i, h in enumerate(norm) if "paid tier" in h]
    if len(paid_matches) != 1:
        return None
    paid_idx = paid_matches[0]
    feat_matches = [i for i, h in enumerate(norm) if h == "feature" or h.startswith("feature ")]
    if len(feat_matches) == 1:
        feat_idx = feat_matches[0]
    elif not require_feature_name and not feat_matches and paid_idx != 0 and norm[0] == "":
        feat_idx = 0
    else:
        return None
    if feat_idx == paid_idx:
        return None
    return (feat_idx, paid_idx)


def _record_section_model(
    models: dict,
    key: str,
    display_name: str,
    inp_entries: list[tuple[float, str | None, str | None]],
    out_entries: list[tuple[float, str | None, str | None]],
    cache_entries: list[tuple[float, str | None, str | None]],
) -> None:
    if not (inp_entries and out_entries):
        return

    # Base rate: earliest / pre-transition ('through' or first undated)
    def _base(entries):
        through_list = [e for e in entries if e[2] is not None]
        if through_list:
            return through_list[0][0]
        undated = [e for e in entries if e[1] is None and e[2] is None]
        if undated:
            return undated[0][0]
        return entries[0][0]

    inp_base = _base(inp_entries)
    out_base = _base(out_entries)
    if inp_base <= 0 or out_base <= 0 or out_base < inp_base:
        return

    entry: dict = {
        "display_name": display_name,
        "input": inp_base,
        "output": out_base,
    }
    if cache_entries:
        cache_base = _base(cache_entries)
        if 0 < cache_base < inp_base:
            entry["cache_read"] = cache_base

    # Future dated schedule steps ('starting <date>')
    schedule: dict[str, dict] = {}
    for kind, entries in (("input", inp_entries), ("output", out_entries), ("cache_read", cache_entries)):
        for val, start_iso, _ in entries:
            if start_iso is not None:
                schedule.setdefault(start_iso, {})[kind] = val
    if schedule:
        entry["schedule"] = schedule

    if key not in models:
        models[key] = entry


# --------------------------------------------------------------------------
# shapes: sections (Google Gemini Markdoc & HTML)
# --------------------------------------------------------------------------

def _split_markdoc_rows(table_body: str) -> list[list[str]]:
    raw_rows = re.split(r"\n[ \t]*---+[ \t]*\n", table_body.strip())
    rows = []
    for raw_r in raw_rows:
        r_str = raw_r.strip("\n")
        if not r_str.strip():
            continue
        parts = re.split(r"(?:^|\n)[ \t]*\*(?:[ \t]+|$)", r_str)
        if parts and parts[0].strip() == "":
            parts = parts[1:]
        if parts:
            rows.append([p.strip() for p in parts])
    return rows


def _extract_markdoc_keys(heading_raw: str, pre_tab_text: str) -> list[tuple[str, str]]:
    heading_clean = re.sub(r"{%[^%]*%}", "", heading_raw).strip()
    heading_ascii = heading_clean.encode("ascii", "ignore").decode("ascii").strip()
    low_head = heading_ascii.lower()
    if not heading_ascii or any(skip in low_head for skip in (
        "pricing", "notes", "ai agent context", "gemma ", "lyria", "embedding", "robotics",
    )):
        return []

    out: list[tuple[str, str]] = []
    for m in re.finditer(r"\[\s*`([^`]*)`\s*\]\([^)]*/docs/models/[^)]*\)", pre_tab_text, re.IGNORECASE):
        raw_slug = m.group(1).strip()
        if not raw_slug:
            return []
        s = slug(raw_slug)
        if s and all(k != s for k, _ in out):
            out.append((s, heading_clean if len(out) == 0 else raw_slug))
    if out:
        return out
    s_head = slug(heading_ascii)
    if s_head.startswith("gemini-"):
        return [(s_head, heading_clean)]
    return []


def parse_sections_markdoc(md: str, tier: str = "Standard") -> dict:
    """Parse Google Gemini Markdoc ({% table %} / {% tabs %}) pricing document."""
    models: dict = {}
    if not md or "{% table %}" not in md:
        return models
    md = html_lib.unescape(md)

    sections = re.split(r"^##[ \t]+", md, flags=re.MULTILINE)[1:]
    for sec in sections:
        lines = sec.splitlines()
        heading_raw = lines[0] if lines else ""
        body = "\n".join(lines[1:])

        pre_end = body.find("{% tabs %}")
        if pre_end == -1:
            pre_end = body.find("{% table %}")
        pre_text = body[:pre_end] if pre_end != -1 else body

        key_pairs = _extract_markdoc_keys(heading_raw, pre_text)
        if not key_pairs:
            continue

        if "{% tabs %}" in body:
            tab_m = re.search(
                rf'{{%\s*tab\s+title=["\']{re.escape(tier)}["\']\s*%}}([\s\S]*?){{%\s*/tab\s*%}}',
                body,
                re.IGNORECASE,
            )
            if not tab_m:
                continue
            search_block = tab_m.group(1)
        else:
            search_block = body

        table_m = re.search(r"{%\s*table\s*%}([\s\S]*?){%\s*/table\s*%}", search_block, re.IGNORECASE)
        if not table_m:
            continue

        rows = _split_markdoc_rows(table_m.group(1))
        if len(rows) < 2:
            continue

        headers = rows[0]
        cols = _find_gemini_columns(headers, require_feature_name=True)
        if cols is None:
            continue
        feat_idx, paid_idx = cols
        header_unit = _detect_unit_multiplier(headers[paid_idx])

        inp_entries: list = []
        out_entries: list = []
        cache_entries: list = []
        malformed = False

        for cells in rows[1:]:
            if len(cells) != len(headers):
                malformed = True
                break
            label = _clean_cell_text(cells[feat_idx]).lower()
            paid_raw = cells[paid_idx]
            if "input price" in label and not inp_entries:
                inp_entries = _parse_section_paid_cell(paid_raw, header_unit)
            elif "output price" in label and not out_entries:
                out_entries = _parse_section_paid_cell(paid_raw, header_unit)
            elif "context caching" in label and not cache_entries:
                cache_entries = _parse_section_paid_cell(paid_raw, header_unit)

        if malformed:
            continue

        for k, disp in key_pairs:
            _record_section_model(models, k, disp, inp_entries, out_entries, cache_entries)

    return models


def parse_sections_markdown(md: str, tier: str) -> dict:
    if "{% table %}" in md:
        return parse_sections_markdoc(md, tier=tier)

    models: dict = {}
    model: str | None = None
    current_tier: str | None = None
    cols: tuple[int, int] | None = None
    header_unit: float = 1.0
    inp_entries: list = []
    out_entries: list = []
    cache_entries: list = []

    def _flush() -> None:
        if model:
            s = slug(model)
            if s:
                _record_section_model(models, s, model, inp_entries, out_entries, cache_entries)

    for line in md.splitlines():
        h2 = re.match(r"^##\s+(.+?)\s*$", line)
        if h2:
            _flush()
            model = h2.group(1).strip()
            current_tier = None
            cols = None
            header_unit = 1.0
            inp_entries, out_entries, cache_entries = [], [], []
            continue
        h3 = re.match(r"^###\s+(.+?)\s*$", line)
        if h3:
            _flush()
            raw_t = h3.group(1).strip()
            current_tier = _DocParser.match_tier(raw_t) or raw_t
            cols = None
            header_unit = 1.0
            inp_entries, out_entries, cache_entries = [], [], []
            continue

        if not model or (tier and (not current_tier or current_tier.lower() != tier.lower())):
            continue
        sline = line.strip()
        if not sline.startswith("|"):
            continue
        cells = [c.strip() for c in sline.strip("|").split("|")]
        if not cells or all(not c or re.fullmatch(r":?-+:?", c) for c in cells):
            continue

        if cols is None and not inp_entries and not out_entries:
            found = _find_gemini_columns(cells, require_feature_name=False)
            if found is not None:
                cols = found
                header_unit = _detect_unit_multiplier(cells[cols[1]]) or 1.0
                continue

        if cols is not None:
            if len(cells) <= max(cols):
                continue
            feat_i, paid_i = cols
        else:
            if len(cells) < 2:
                continue
            feat_i, paid_i = 0, -1

        label = _clean_cell_text(cells[feat_i]).lower()
        paid_raw = cells[paid_i]
        if "input price" in label and not inp_entries:
            inp_entries = _parse_section_paid_cell(paid_raw, header_unit)
        elif "output price" in label and not out_entries:
            out_entries = _parse_section_paid_cell(paid_raw, header_unit)
        elif "context caching" in label and not cache_entries:
            cache_entries = _parse_section_paid_cell(paid_raw, header_unit)

    _flush()
    return models


def _resolve_html_table_tier(table: dict) -> str | None:
    """Resolve an HTML table's service tier from button/text context or h4/h3 headings."""
    direct = _DocParser.match_tier(table.get("tier") or "")
    if direct:
        return direct
    heads = table.get("headings") or {}
    for level in ("h4", "h3"):
        matched = _DocParser.match_tier(heads.get(level) or "")
        if matched:
            return matched
    return None


def parse_sections_html(doc: _DocParser, tier: str) -> dict:
    models: dict = {}
    for table in doc.tables:
        heads = table["headings"]
        model = heads.get("h2")
        if not model:
            continue
        if tier:
            resolved_tier = _resolve_html_table_tier(table)
            if not resolved_tier or resolved_tier.lower() != tier.lower():
                continue
        rows = table["rows"]
        if len(rows) < 2:
            continue
        headers = rows[0]
        cols = _find_gemini_columns(headers, require_feature_name=False)
        if cols is None:
            continue
        feat_idx, paid_idx = cols
        header_unit = _detect_unit_multiplier(headers[paid_idx])

        inp_entries: list = []
        out_entries: list = []
        cache_entries: list = []

        for row in rows[1:]:
            if len(row) != len(headers):
                continue
            label = _clean_cell_text(row[feat_idx]).lower()
            paid_raw = row[paid_idx]
            if "input price" in label and not inp_entries:
                inp_entries = _parse_section_paid_cell(paid_raw, header_unit)
            elif "output price" in label and not out_entries:
                out_entries = _parse_section_paid_cell(paid_raw, header_unit)
            elif "context caching" in label and not cache_entries:
                cache_entries = _parse_section_paid_cell(paid_raw, header_unit)

        s = slug(model)
        if s:
            _record_section_model(models, s, model, inp_entries, out_entries, cache_entries)
    return models


# --------------------------------------------------------------------------
# shapes: matrix (Anthropic HTML & Markdown pipe tables)
# --------------------------------------------------------------------------

def _parse_cell_with_schedules(cell: str) -> tuple[float | None, list[tuple[str, float]]]:
    """Parse a matrix cell into (current_price, [(effective_date_iso, future_price), ...])."""
    cleaned = _clean_cell_text(cell or "")
    low = cleaned.lower()
    if not cleaned or low.startswith("not available") or low in {"n/a", "-", "—"}:
        return None, []
    if (low.startswith("free of charge") or low == "free") and "$" not in low:
        return 0.0, []

    segments: list[str] = []
    for line in cleaned.splitlines():
        parts = re.split(r"(?=\$[0-9])", line)
        segments.extend(p.strip() for p in parts if p.strip())

    through_prices: list[float] = []
    undated_prices: list[float] = []
    all_prices: list[float] = []
    schedules: list[tuple[str, float]] = []

    if segments and segments[0].lower().startswith("free") and "$" not in segments[0]:
        undated_prices.append(0.0)
        all_prices.append(0.0)

    for seg in segments:
        m_price = _PRICE.search(seg)
        if not m_price:
            continue
        val = float(m_price.group(1).replace(",", ""))
        all_prices.append(val)

        m_date = _DATE_CLAUSE.search(seg)
        if m_date:
            kw = m_date.group(1).lower()
            parsed_dt = _parse_english_date(m_date.group(2))
            if parsed_dt:
                if kw == "through":
                    through_prices.append(val)
                else:
                    schedules.append((parsed_dt, val))
                continue
        undated_prices.append(val)

    if not all_prices:
        return None, []
    price_now = (
        through_prices[0]
        if through_prices
        else (undated_prices[0] if undated_prices else all_prices[0])
    )
    return price_now, schedules


def parse_cell(cell: str):
    """(price_now, (effective_date_iso, price_then)) — None when not priced."""
    price_now, schedules = _parse_cell_with_schedules(cell)
    return price_now, (schedules[0] if schedules else None)


def _resolve_matrix_columns(headers: list[str], columns: dict) -> dict[str, int]:
    """Match configured column roles against actual headers using case-insensitive aliases."""
    norm_headers = [re.sub(r"\s+", " ", _clean_cell_text(h)).strip().lower() for h in headers]
    idx: dict[str, int] = {}
    for role, configured in columns.items():
        candidates = [configured.lower()] + list(_MATRIX_COL_ALIASES.get(role, ()))
        for cand in candidates:
            hit = next((j for j, h in enumerate(norm_headers) if h == cand), None)
            if hit is not None:
                idx[role] = hit
                break
    return idx


_SKIP_MATRIX_SECTIONS = ("fast mode", "batch", "flex", "priority", "worked example")


def _is_skipped_matrix_heading(heading_text: str) -> bool:
    low = (heading_text or "").lower()
    return any(tok in low for tok in _SKIP_MATRIX_SECTIONS)


def _record_matrix_row(models: dict, name: str, row: list[str], idx: dict[str, int]) -> None:
    if not name or _PRICE.search(name):
        return
    first_line = next((ln.strip() for ln in name.splitlines() if ln.strip()), "")
    if not first_line:
        return
    clean_name = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", first_line)
    clean_name = re.sub(r"<[^>]+>", "", clean_name)
    clean_name = re.sub(r"[\uE000-\uF8FF]", "", clean_name).strip()
    if "over " in clean_name.lower() and "tokens" in clean_name.lower():
        s = slug(clean_name)
        if s in models:
            return
    s = slug(clean_name)
    if not s:
        return
    if s in models:
        return

    entry = models.setdefault(s, {"display_name": clean_name})
    for kind, i in idx.items():
        if i >= len(row):
            continue
        price, schedules = _parse_cell_with_schedules(row[i])
        if price is not None and kind not in entry:
            entry[kind] = price
            for when, amount in schedules:
                entry.setdefault("schedule", {}).setdefault(when, {})[kind] = amount


def parse_matrix_html(doc: _DocParser, columns: dict, tier: str | None = None) -> dict:
    """One row per model, prices in named columns (supports split subheaders like 'Base tokens' -> 'Input')."""
    models: dict = {}
    for table in doc.tables:
        heads_text = " ".join(table.get("headings", {}).values())
        if _is_skipped_matrix_heading(heads_text):
            continue
        rows = table["rows"]
        if len(rows) < 2:
            continue
        if tier and table.get("tier") and table["tier"] != tier:
            continue

        header_i, idx = None, {}
        for i, row in enumerate(rows[:3]):
            found = _resolve_matrix_columns(row, columns)
            if "input" in found and "output" in found:
                header_i, idx = i, found
                break
        if header_i is None:
            continue

        for row in rows[header_i + 1:]:
            if len(row) <= max(idx.values()):
                continue
            _record_matrix_row(models, row[0], row, idx)
    return models


def parse_matrix_markdown(md: str, columns: dict) -> dict:
    """Parse Markdown pipe-delimited pricing tables, skipping Fast mode / Batch / example sections."""
    models: dict = {}
    headers = None
    idx: dict[str, int] = {}
    cur_heading = ""
    for line in md.splitlines():
        s = line.strip()
        if re.match(r"^#{1,4}\s+", s):
            cur_heading = s
            headers = None
            idx = {}
            continue
        if not s.startswith("|"):
            headers = None
            idx = {}
            continue
        if _is_skipped_matrix_heading(cur_heading):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.fullmatch(r":?-+:?", c) for c in cells):
            continue
        if headers is None:
            found = _resolve_matrix_columns(cells, columns)
            if "input" in found and "output" in found:
                headers = cells
                idx = found
            continue
        if len(cells) >= len(headers):
            _record_matrix_row(models, cells[0], cells, idx)
    return models


def parse_json_api(text: str, cfg: dict) -> dict:
    """Provider JSON catalogues (e.g. OpenRouter /api/v1/models)."""
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
            if value < 0:
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
    looks_markdoc = "{% table %}" in text

    if shape == "sections":
        if looks_markdoc:
            models = parse_sections_markdoc(text, cfg.get("tier", "Standard"))
        elif looks_html:
            models = parse_sections_html(_feed(text), cfg.get("tier", "Standard"))
        else:
            models = parse_sections_markdown(text, cfg.get("tier", "Standard"))
    elif shape == "matrix":
        if looks_html:
            models = parse_matrix_html(_feed(text), cfg.get("columns", {}), cfg.get("tier"))
        else:
            models = parse_matrix_markdown(text, cfg.get("columns", {}))
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
        except Exception as exc:
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

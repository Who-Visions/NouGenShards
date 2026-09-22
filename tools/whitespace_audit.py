"""Negative-space audit for NouGen web UIs: measure whitespace instead of eyeballing it.

Merges the concepts Dave fed in on 9/13/2026: the Wix / Mailchimp / Elementor white-space guides and the sources they
cite (NN/g, W3C WCAG supplemental whitespace pattern, Smashing on cognitive load, Mailchimp Gestalt); the
consistent_whitespace idea (one spacing system, enforced by a lint; AGPL, idea only); demojify-sanitize (strip emoji
clutter and redundant spaces from AI text; Apache-2.0, idea only). The free fleet distilled 12 sharded sources into
measurable principles (WhoVisions Photographer fleet/analysis/whitespace_principles.json).

  python whitespace_audit.py css web/src/styles.css      static: spacing on the token scale, font families, line-height
  python whitespace_audit.py probe                       print a devtools snippet that measures a live page
  python whitespace_audit.py dom metrics.json            score the numbers that snippet returned
  python whitespace_audit.py text "<AI text>"            demojify: strip pictographs, collapse runs of spaces

Each check prints PASS / WARN / FAIL with the measured number and its threshold; exit code 1 on any FAIL (CI gate).
Deterministic: pure functions of the input.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HAIRLINE_PX = 2            # 0-2 px are borders and hairlines, not spacing
MAX_FONT_FAMILIES = 3      # display + body + UI/mono
MIN_BODY_LEADING = 1.4     # body text line-height (WCAG 1.4.12 overrides use 1.5)
CHROME_MAX = 0.35          # share of the viewport taken by bars around the content
MAX_VISIBLE_CONTROLS = 12  # visible toolbar controls before they read as clutter
MIN_SECTION_GAP = 16       # px between sibling sections (macro space, proximity grouping)
MIN_TARGET = 24            # px, WCAG 2.5.8 minimum target size

SPACING_RE = re.compile(r"(margin(?:-[a-z]+)?|padding(?:-[a-z]+)?|gap|row-gap|column-gap)\s*:\s*([^;}]+)")
RAW_PX_RE = re.compile(r"(?<![\w.-])(\d*\.?\d+)px")
# Emoji + pictographs, as separate non-adjacent alternatives (not one mixed
# character class) so no range's endpoints can be misread as overlapping.
# Keeps the UI stars U+2605/2606, arrows and letters of every script.
PICTO = re.compile(
    "[\U0001F000-\U0001FAFF]"      # mahjong/dominoes through extended-A pictographs
    "|[☀-☄]|[☇-⛿]"  # misc symbols, minus the kept UI stars 2605/2606
    "|[✀-➿]"              # dingbats
    "|[⭐⭕]"               # star, heavy circle
    "|[︎️‍]"         # variation selectors, ZWJ
    "|[\U000E0020-\U000E007F]"      # tag characters (emoji flag sequences)
)


def _res(level: str, name: str, detail: str) -> dict:
    return {"level": level, "check": name, "detail": detail}


def audit_css(css: str) -> list[dict]:
    out = []
    decls = SPACING_RE.findall(css)
    raw = [(p, v.strip()) for p, v in decls if any(float(n) > HAIRLINE_PX for n in RAW_PX_RE.findall(v))]
    out.append(_res("FAIL" if raw else "PASS", "spacing on the token scale",
                    f"{len(raw)} of {len(decls)} spacing declarations use raw px above {HAIRLINE_PX}px" + (f": {raw[:4]}" if raw else "")))
    fams = {f.strip().strip("'\"").split(",")[0].strip().lower() for f in re.findall(r"font-family\s*:\s*([^;]+);", css)}
    fams = {f for f in fams if f and not f.startswith("var(") and f not in ("inherit", "initial")}
    out.append(_res("PASS" if len(fams) <= MAX_FONT_FAMILIES else "WARN", "font families",
                    f"{len(fams)} literal families ({', '.join(sorted(fams)[:6]) or 'all via tokens'}); limit {MAX_FONT_FAMILIES}"))
    lh = [float(x) for x in re.findall(r"line-height\s*:\s*(\d*\.?\d+)\s*[;}]", css)]
    low = [x for x in lh if 0.5 < x < MIN_BODY_LEADING]
    out.append(_res("WARN" if low else "PASS", "unitless line-height",
                    f"{len(low)} of {len(lh)} below {MIN_BODY_LEADING} (fine for controls and labels, not body text)"))
    return out


def audit_dom(m: dict) -> list[dict]:
    out = []
    vh = m.get("viewportH") or 1
    chrome = (m.get("chromeTop", 0) + m.get("chromeBottom", 0)) / vh
    out.append(_res("PASS" if chrome <= CHROME_MAX else "FAIL", "chrome share (macro space)",
                    f"{chrome:.0%} of the viewport is chrome; limit {CHROME_MAX:.0%}; content gets {1 - chrome:.0%}"))
    hh = m.get("headerH")
    if hh is not None:
        out.append(_res("PASS" if hh <= 72 else "WARN", "header height", f"{hh}px (one row is about 56-64px)"))
    n = m.get("visibleControls", 0)
    out.append(_res("PASS" if n <= MAX_VISIBLE_CONTROLS else "WARN", "visible toolbar controls (cognitive load)",
                    f"{n} in the header; limit {MAX_VISIBLE_CONTROLS}; fold the rest into a drawer"))
    gaps = m.get("sectionGaps", [])
    tight = [g for g in gaps if g < MIN_SECTION_GAP]
    out.append(_res("PASS" if not tight else "WARN", "gap between sibling sections",
                    f"{len(tight)} of {len(gaps)} gaps under {MIN_SECTION_GAP}px"))
    small = m.get("smallTargets", 0)
    out.append(_res("PASS" if not small else "WARN", "target size (WCAG 2.5.8)", f"{small} visible controls under {MIN_TARGET}x{MIN_TARGET}px"))
    top = m.get("primaryActionTop")
    if top is not None:
        out.append(_res("PASS" if top < vh else "FAIL", "primary action above the fold", f"at {top}px, viewport {vh}px"))
    return out


def sanitize_text(s: str) -> tuple[str, dict]:
    """Strip pictographs/emoji (with ZWJ, variation selectors, tag characters), collapse runs of spaces and blank
    lines, trim. Letters of every script and UI symbols such as the star and arrows are kept."""
    s = unicodedata.normalize("NFC", s)
    n = len(PICTO.findall(s))
    t = PICTO.sub("", s)
    t = re.sub(r"[ \t ]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t, {"emoji_removed": n, "bytes_saved": len(s.encode()) - len(t.encode())}


DOM_PROBE = r"""(() => {
  const vh = innerHeight, q = s => document.querySelector(s), R = e => e ? e.getBoundingClientRect() : null;
  const cr = R(q('main, .scroller, [role=main]')); const hr = R(q('header'));
  const vis = e => { const r = R(e); return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < vh; };
  const ctrls = q('header') ? [...q('header').querySelectorAll('button, a[href], input, select, summary')].filter(vis) : [];
  const secs = [...document.querySelectorAll('section, aside > *')].filter(vis).map(R).sort((a, b) => a.top - b.top);
  const gaps = secs.slice(1).map((r, i) => Math.round(r.top - secs[i].bottom)).filter(g => g >= 0);
  const small = [...document.querySelectorAll('button, a[href], input, select, summary')].filter(vis)
    .filter(e => { const r = R(e); return r.width < 24 || r.height < 24; }).length;
  const p = q('[data-primary], .btn-gold');
  return JSON.stringify({ viewportH: vh, chromeTop: cr ? Math.round(cr.top) : 0, chromeBottom: cr ? Math.round(vh - cr.bottom) : 0,
    headerH: hr ? Math.round(hr.height) : null, visibleControls: ctrls.length, sectionGaps: gaps, smallTargets: small,
    primaryActionTop: p ? Math.round(R(p).top) : null });
})()"""


def main(argv=None) -> int:
    a = argv if argv is not None else sys.argv[1:]
    if not a or a[0] not in ("css", "dom", "text", "probe"):
        print(__doc__)
        return 2
    if a[0] == "probe":
        print(DOM_PROBE)
        return 0
    if a[0] == "text":
        t, st = sanitize_text(" ".join(a[1:]))
        print(json.dumps({"text": t, **st}, ensure_ascii=False))
        return 0
    res = audit_css(open(a[1], encoding="utf-8").read()) if a[0] == "css" else audit_dom(json.load(open(a[1], encoding="utf-8")))
    for r in res:
        print(f"{r['level']:4s}  {r['check']:42s} {r['detail']}")
    return 1 if any(r["level"] == "FAIL" for r in res) else 0


if __name__ == "__main__":
    sys.exit(main())

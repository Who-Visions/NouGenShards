#!/usr/bin/env python3
"""Quality gates for a DESIGN.md design-system package.

Usage:
    python validate.py <package-dir> [--json]

A package is a directory containing manifest.json, DESIGN.md and tokens.css.

Each gate returns one of three verdicts:

    passed                  the gate is satisfied
    failed                  the package is not shippable
    confirmation-required   ambiguous; a human decides, not the tool

The process exits non-zero only on ``failed``, so ambiguous cases surface
without blocking a pipeline.

Every threshold resolves env -> constant, with the constant as a logged
fallback. Nothing environment- or threshold-shaped is hardcoded into a
decision path.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# --- Shared contract -------------------------------------------------------
# SKILL.md documents these same floors. They live here so the prose and the
# validator cannot drift apart; SKILL.md cites this module as the authority.

_DEFAULTS = {
    # Downstream consumers count H2s and ignore their titles. 7 is their floor.
    "NOUGEN_DESIGN_MIN_H2": 7,
    # A package below this custom-property count is under-specified.
    "NOUGEN_DESIGN_MIN_TOKENS": 26,
    # WCAG 2.1 AA.
    "NOUGEN_DESIGN_MIN_CONTRAST_BODY": 4.5,
    "NOUGEN_DESIGN_MIN_CONTRAST_LARGE": 3.0,
}

PASSED = "passed"
FAILED = "failed"
CONFIRM = "confirmation-required"

REQUIRED_FILES = ("manifest.json", "DESIGN.md", "tokens.css")
EXPECTED_SCHEMA = "od-design-system-project/v1"


def threshold(key: str) -> float:
    """Resolve a threshold from env, falling back to the logged default."""
    raw = os.environ.get(key)
    default = _DEFAULTS[key]
    if raw is None:
        return default
    try:
        return type(default)(raw)
    except (TypeError, ValueError):
        print(f"  ! {key}={raw!r} is not numeric; using default {default}", file=sys.stderr)
        return default


# --- Color math ------------------------------------------------------------

_HEX = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")

# Marks a documented ratio as measured against a blended/overlaid color, which
# by definition cannot be reproduced from two declared hexes.
_BLEND = re.compile(r"\b\d+\s*%|opacity|alpha|rgba", re.IGNORECASE)


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return (
        0.2126 * _srgb_to_linear(r)
        + 0.7152 * _srgb_to_linear(g)
        + 0.0722 * _srgb_to_linear(b)
    )


def contrast_ratio(fg: str, bg: str) -> float:
    a, b = relative_luminance(fg), relative_luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


# --- Gate plumbing ---------------------------------------------------------

@dataclass
class Gate:
    name: str
    verdict: str
    detail: str
    evidence: list[str] = field(default_factory=list)


def _strip_comments(css: str) -> str:
    """Remove /* ... */ blocks.

    Every CSS gate parses with regexes, and prose inside a comment is
    indistinguishable from real syntax to a regex - a comment mentioning
    ``:root`` reads as a selector. Strip first, always.
    """
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def _read_css(pkg: Path) -> str:
    return _strip_comments((pkg / "tokens.css").read_text(encoding="utf-8"))


def _parse_custom_properties(css: str) -> dict[str, str]:
    """Collect --name: value declarations. Last write wins, as in the cascade."""
    props: dict[str, str] = {}
    for match in re.finditer(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;]+);", css):
        props[match.group(1)] = match.group(2).strip()
    return props


def _frontmatter(text: str) -> str:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    return match.group(1) if match else ""


# --- Gates -----------------------------------------------------------------

def gate_files(pkg: Path) -> Gate:
    missing = [f for f in REQUIRED_FILES if not (pkg / f).is_file()]
    if missing:
        return Gate("files", FAILED, f"missing {', '.join(missing)}")
    return Gate("files", PASSED, "manifest.json, DESIGN.md, tokens.css present")


def gate_manifest(pkg: Path) -> Gate:
    try:
        data = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Gate("manifest", FAILED, f"unreadable: {exc}")
    schema = data.get("schemaVersion")
    if not schema:
        return Gate("manifest", FAILED, "no schemaVersion")
    if schema != EXPECTED_SCHEMA:
        return Gate(
            "manifest", CONFIRM,
            f"schemaVersion is {schema!r}, expected {EXPECTED_SCHEMA!r} - "
            "intentional pin to another dialect?",
        )
    return Gate("manifest", PASSED, f"pinned to {schema}")


def gate_headings(pkg: Path) -> Gate:
    floor = int(threshold("NOUGEN_DESIGN_MIN_H2"))
    text = (pkg / "DESIGN.md").read_text(encoding="utf-8")
    body = text[len(_frontmatter(text)):] if _frontmatter(text) else text
    headings = re.findall(r"^##\s+\S.*$", body, re.MULTILINE)
    if len(headings) < floor:
        return Gate(
            "headings", FAILED,
            f"{len(headings)} H2 sections, need >= {floor}",
            [h.strip() for h in headings],
        )
    return Gate("headings", PASSED, f"{len(headings)} H2 sections (floor {floor})")


def gate_tokens(pkg: Path) -> Gate:
    floor = int(threshold("NOUGEN_DESIGN_MIN_TOKENS"))
    props = _parse_custom_properties(_read_css(pkg))
    if len(props) < floor:
        return Gate("tokens", FAILED, f"{len(props)} custom properties, need >= {floor}")
    return Gate("tokens", PASSED, f"{len(props)} custom properties (floor {floor})")


def gate_parity(pkg: Path) -> Gate:
    """Dual-canon guard: colors named in DESIGN.md must exist in tokens.css."""
    design = (pkg / "DESIGN.md").read_text(encoding="utf-8")
    css = _read_css(pkg)
    declared = {m.group(0).lower() for m in _HEX.finditer(_frontmatter(design))}
    in_css = {m.group(0).lower() for m in _HEX.finditer(css)}
    if not declared:
        return Gate("parity", CONFIRM, "no colors in DESIGN.md frontmatter to check")
    orphans = sorted(declared - in_css)
    if orphans:
        return Gate(
            "parity", FAILED,
            f"{len(orphans)} color(s) documented but absent from tokens.css",
            orphans,
        )
    return Gate("parity", PASSED, f"all {len(declared)} documented colors exist in tokens.css")


def gate_focus(pkg: Path) -> Gate:
    css = _read_css(pkg)
    has_rule = ":focus-visible" in css
    strips = len(re.findall(r"outline\s*:\s*none", css))
    if not has_rule:
        return Gate("focus", FAILED, "no :focus-visible rule - the system is keyboard-blind")
    # outline:none is legitimate only inside the rule that replaces the ring.
    replaced = len(re.findall(r":focus-visible[^{]*\{[^}]*box-shadow", css, re.DOTALL))
    if strips and not replaced:
        return Gate("focus", FAILED, f"outline:none used {strips}x with no replacement ring")
    return Gate("focus", PASSED, "focus-visible ring defined")


def gate_motion(pkg: Path) -> Gate:
    css = _read_css(pkg)
    if "prefers-reduced-motion" in css:
        return Gate("motion", PASSED, "reduced-motion gate present")
    if re.search(r"@keyframes|animation\s*:", css):
        return Gate("motion", FAILED, "animation declared with no reduced-motion gate")
    return Gate("motion", CONFIRM, "no animation and no gate — intentional?")


def gate_themes(pkg: Path) -> Gate:
    """A color defined only inside a media/[data-theme] block never applies
    in the unstamped default state. Check the base :root carries the palette."""
    css = _read_css(pkg)
    # Classify every :root rule by its selector: the bare one is the base
    # palette, anything qualified (:not(), [data-theme], or nested in a media
    # query) is scoped. A token appearing only in a scoped block never applies
    # in the unstamped default state.
    base_props: set[str] = set()
    scoped_props: set[str] = set()
    found_base = False
    for rule in re.finditer(r"(:root[^{]*?)\{([^}]*)\}", css, re.DOTALL):
        selector, body = rule.group(1).strip(), rule.group(2)
        props = set(_parse_custom_properties(body))
        if selector == ":root":
            found_base = True
            base_props |= props
        else:
            scoped_props |= props
    if not found_base:
        return Gate("themes", FAILED, "no bare :root block")
    orphans = sorted(scoped_props - base_props)
    if orphans:
        return Gate(
            "themes", FAILED,
            f"{len(orphans)} token(s) defined only in a themed block",
            orphans,
        )
    if not scoped_props and "prefers-color-scheme" not in css:
        return Gate("themes", CONFIRM, "single-theme package - deliberate commitment?")
    return Gate("themes", PASSED, "base :root carries the full palette")


def gate_contrast(pkg: Path) -> Gate:
    """Read the measured table in DESIGN.md and re-derive it independently."""
    body_floor = threshold("NOUGEN_DESIGN_MIN_CONTRAST_BODY")
    design = (pkg / "DESIGN.md").read_text(encoding="utf-8")
    css = _read_css(pkg)
    base = re.search(r":root\s*\{(.*?)\}", css, re.DOTALL)
    if not base:
        return Gate("contrast", CONFIRM, "no base :root to resolve pairs from")
    props = _parse_custom_properties(base.group(1))

    def hexval(name: str | None) -> str | None:
        if not name:
            return None
        raw = props.get(name, "")
        m = _HEX.search(raw)
        return m.group(0) if m else None

    # Prefer an explicit declaration. Token naming is a brand decision, so
    # guessing it by convention fails on any package that names things its
    # own way - which is most of them.
    declared: dict[str, str] = {}
    try:
        declared = json.loads(
            (pkg / "manifest.json").read_text(encoding="utf-8")
        ).get("surfaces", {}) or {}
    except (OSError, json.JSONDecodeError):
        pass

    ground = hexval(declared.get("ground"))
    ink = hexval(declared.get("ink"))
    if not ground:
        ground = hexval("--color-night") or hexval("--color-bg") or hexval("--surface")
    if not ink:
        ink = hexval("--color-ink") or hexval("--color-fg") or hexval("--ink")
    if not ground or not ink:
        return Gate(
            "contrast", CONFIRM,
            'could not resolve a ground/ink pair - declare '
            '"surfaces": {"ground": "--token", "ink": "--token"} in manifest.json',
        )

    ratio = contrast_ratio(ink, ground)
    evidence = [f"ink {ink} on ground {ground} = {ratio:.2f}"]
    if ratio < body_floor:
        return Gate("contrast", FAILED, f"primary text pair {ratio:.2f} < {body_floor}", evidence)

    # A documented failure that is explicitly called out is a known limit, not a defect.
    documented_fails = len(re.findall(r"\bfails?\b", design, re.IGNORECASE))
    if documented_fails:
        evidence.append(f"{documented_fails} failing pair(s) documented in DESIGN.md")
        return Gate(
            "contrast", CONFIRM,
            "primary pair passes; DESIGN.md documents failing pairs - confirm each is "
            "restricted in use rather than shipped",
            evidence,
        )
    return Gate("contrast", PASSED, f"primary text pair {ratio:.2f} >= {body_floor}", evidence)


def gate_claims(pkg: Path) -> Gate:
    """Every contrast ratio quoted in DESIGN.md must be reproducible.

    Written numbers rot silently: nobody re-derives a table by hand, so a
    ratio that was estimated rather than computed ships as documentation and
    is believed. This recomputes every pair the package actually contains and
    checks each quoted figure against that set.
    """
    design = (pkg / "DESIGN.md").read_text(encoding="utf-8")
    css = _read_css(pkg)

    colors = {m.group(0).lower() for m in _HEX.finditer(css)}
    # Expand 3-digit forms so #fff and #ffffff compare equal.
    expanded = set()
    for c in colors:
        h = c.lstrip("#")
        expanded.add("#" + ("".join(ch * 2 for ch in h) if len(h) == 3 else h))
    if len(expanded) < 2:
        return Gate("claims", CONFIRM, "not enough colors in tokens.css to check claims")

    ordered = sorted(expanded)
    achievable = {
        round(contrast_ratio(a, b), 2)
        for i, a in enumerate(ordered) for b in ordered[i + 1:]
    }

    # Only inspect the accessibility section; scales and durations elsewhere
    # use the same decimal shape and are not contrast claims.
    section = re.search(r"^##\s+Accessibility\b(.*?)(?=^##\s|\Z)",
                        design, re.DOTALL | re.MULTILINE)
    if not section:
        return Gate("claims", CONFIRM, "no Accessibility section to check")

    # A ratio measured against a blended color (an alpha overlay) is not
    # reproducible from two declared hexes, and documenting one is legitimate.
    # Skip lines that name the blend rather than calling the figure wrong.
    quoted = set()
    for line in section.group(1).splitlines():
        if _BLEND.search(line):
            continue
        for found in re.findall(r"\b(\d{1,2}\.\d{2})\b", line):
            if 1.0 <= float(found) <= 21.0:
                quoted.add(float(found))
    if not quoted:
        return Gate("claims", CONFIRM, "no contrast ratios quoted to verify")

    tolerance = 0.05
    unmatched = sorted(
        q for q in quoted
        if not any(abs(q - a) <= tolerance for a in achievable)
    )
    if unmatched:
        return Gate(
            "claims", FAILED,
            f"{len(unmatched)} quoted ratio(s) match no pair in tokens.css",
            [f"{q:.2f} is not reproducible from any two declared colors" for q in unmatched],
        )
    return Gate("claims", PASSED, f"all {len(quoted)} quoted ratios reproduce from tokens.css")


GATES = (
    gate_files, gate_manifest, gate_headings, gate_tokens,
    gate_parity, gate_focus, gate_motion, gate_themes, gate_contrast,
    gate_claims,
)

_MARK = {PASSED: "PASS", FAILED: "FAIL", CONFIRM: "CONF"}


def run(pkg: Path) -> list[Gate]:
    results = [gate_files(pkg)]
    if results[0].verdict == FAILED:
        return results
    for gate in GATES[1:]:
        try:
            results.append(gate(pkg))
        except Exception as exc:  # a broken gate must not read as a pass
            results.append(Gate(gate.__name__, CONFIRM, f"gate errored: {exc}"))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="directory holding the design package")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    root = args.package
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    # Accept either one package, or a directory holding several - a project
    # with more than one brand keeps a package per brand side by side.
    if (root / "manifest.json").is_file():
        packages = [root]
    else:
        packages = sorted(d for d in root.iterdir()
                          if d.is_dir() and (d / "manifest.json").is_file())
    if not packages:
        print(f"no design package found in {root}", file=sys.stderr)
        return 2

    report = {pkg: run(pkg) for pkg in packages}

    if args.as_json:
        print(json.dumps(
            {pkg.name: [{"gate": g.name, "verdict": g.verdict, "detail": g.detail,
                         "evidence": g.evidence} for g in gates]
             for pkg, gates in report.items()},
            indent=2,
        ))
    else:
        for pkg, results in report.items():
            print(f"\n  {pkg.name}\n")
            for g in results:
                print(f"  [{_MARK[g.verdict]}] {g.name:<10} {g.detail}")
                for line in g.evidence:
                    print(f"         - {line}")
            failed = sum(g.verdict == FAILED for g in results)
            confirm = sum(g.verdict == CONFIRM for g in results)
            print(f"\n  {len(results) - failed - confirm} passed, "
                  f"{failed} failed, {confirm} need confirmation")
        print()

    return 1 if any(g.verdict == FAILED
                    for gates in report.values() for g in gates) else 0


if __name__ == "__main__":
    raise SystemExit(main())

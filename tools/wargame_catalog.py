"""War-game catalog: validate, render and summarise docs/wargame-catalog/catalog.ndjson.

Rule 0.1 says every mission with 3+ steps or a real failure surface gets a war
game (wargames/<mission>.md) before any code is touched. This catalog is the
fleet-wide answer to "which missions deserve one": grounded candidates found
2026-09-24 across the Who Visions repos, each carrying evidence paths, a first
fork, a priority and an adversarial-verification verdict.

The NDJSON file is the source of truth. The per-repo markdown next to it is
generated from the NDJSON by this tool and is never hand-edited; `render
--check` fails when the markdown has drifted from the data, so CI can gate it.

Usage:
  python tools/wargame_catalog.py validate             # exit 1 on schema errors
  python tools/wargame_catalog.py render               # regenerate the markdown
  python tools/wargame_catalog.py render --check       # exit 1 if markdown is stale
  python tools/wargame_catalog.py stats [--json]       # counts by repo/priority/kind

Stdlib only (Rule 0.2: paths resolve from env, then the repo layout).
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CATALOG_DIR = Path(os.environ.get("NOUGEN_WARGAME_CATALOG_DIR") or (REPO / "docs" / "wargame-catalog"))
CATALOG_FILE = "catalog.ndjson"
RESERVE_FILE = "reserve.ndjson"

ID_RE = re.compile(r"^WG-\d{4}$")
KINDS = ("defend", "elevate")
PRIORITIES = ("P0", "P1", "P2", "P3")
BLAST = ("fleet", "repo", "module")
LIKELIHOOD = ("observed", "likely", "speculative")
EFFORT = ("S", "M", "L")
VERDICTS = ("CONFIRMED", "PLAUSIBLE")
STATUSES = ("open", "gamed", "done", "wontfix")
REQUIRED = (
    "id", "title", "repo", "kind", "priority", "blast_radius", "likelihood",
    "effort", "failure_surface", "first_fork", "evidence", "verdict",
)
OPTIONAL = ("lens", "lens_group", "verdict_note", "source", "status", "wargame", "tags", "families")
TITLE_MAX = 120
# Scenario families from the war-room umbrella issue (NouGenShards#550). The
# names live in families.json next to the catalog so the taxonomy is data.
FAMILIES_FILE = "families.json"
FAMILY_MIN, FAMILY_MAX = 1, 100

# Priority is derived, never hand-assigned, so two people looking at the same
# evidence land on the same number. Blast radius and likelihood carry the
# weight; a CONFIRMED verdict is worth one notch over PLAUSIBLE.
BLAST_SCORE = {"fleet": 3, "repo": 2, "module": 1}
LIKELIHOOD_SCORE = {"observed": 3, "likely": 2, "speculative": 0}
VERDICT_SCORE = {"CONFIRMED": 1, "PLAUSIBLE": 0}


def score(item):
    return (
        BLAST_SCORE.get(item.get("blast_radius"), 0)
        + LIKELIHOOD_SCORE.get(item.get("likelihood"), 0)
        + VERDICT_SCORE.get(item.get("verdict"), 0)
    )


def derive_priority(item):
    s = score(item)
    if s >= 7:
        return "P0"
    if s >= 5:
        return "P1"
    if s >= 3:
        return "P2"
    return "P3"


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "x"


def load_ndjson(path):
    items = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{n}: not JSON ({exc})") from exc
    return items


def validate_items(items):
    """Return a list of human-readable problems; empty means valid."""
    problems = []
    seen_ids = set()
    seen_titles = {}
    for n, it in enumerate(items, 1):
        where = f"line {n} ({it.get('id', '?')})"
        if not isinstance(it, dict):
            problems.append(f"{where}: record is not an object")
            continue
        for f in REQUIRED:
            if f not in it:
                problems.append(f"{where}: missing field {f!r}")
        extra = set(it) - set(REQUIRED) - set(OPTIONAL)
        if extra:
            problems.append(f"{where}: unknown fields {sorted(extra)}")
        iid = it.get("id")
        if not isinstance(iid, str) or not ID_RE.match(iid):
            problems.append(f"{where}: id must match WG-NNNN")
        elif iid in seen_ids:
            problems.append(f"{where}: duplicate id")
        else:
            seen_ids.add(iid)
        title = it.get("title")
        if not isinstance(title, str) or not title.strip():
            problems.append(f"{where}: empty title")
        elif len(title) > TITLE_MAX:
            problems.append(f"{where}: title longer than {TITLE_MAX} chars")
        else:
            key = (it.get("repo"), title.strip().lower())
            if key in seen_titles:
                problems.append(f"{where}: duplicate title within repo (also {seen_titles[key]})")
            seen_titles[key] = iid
        for field, allowed in (
            ("kind", KINDS), ("priority", PRIORITIES), ("blast_radius", BLAST),
            ("likelihood", LIKELIHOOD), ("effort", EFFORT), ("verdict", VERDICTS),
        ):
            if it.get(field) not in allowed:
                problems.append(f"{where}: {field}={it.get(field)!r} not in {allowed}")
        if "status" in it and it["status"] not in STATUSES:
            problems.append(f"{where}: status={it['status']!r} not in {STATUSES}")
        for field in ("repo", "failure_surface", "first_fork"):
            if not isinstance(it.get(field), str) or not it.get(field, "").strip():
                problems.append(f"{where}: {field} must be a non-empty string")
        ev = it.get("evidence")
        if not isinstance(ev, list) or not ev or not all(isinstance(e, str) and e.strip() for e in ev):
            problems.append(f"{where}: evidence must be a non-empty list of paths or ids")
        fams = it.get("families")
        if fams is not None:
            ok = isinstance(fams, list) and all(
                isinstance(f, int) and not isinstance(f, bool) and FAMILY_MIN <= f <= FAMILY_MAX for f in fams
            ) and len(set(fams)) == len(fams)
            if not ok:
                problems.append(f"{where}: families must be a list of unique ints {FAMILY_MIN}..{FAMILY_MAX}")
        if all(it.get(f) in allowed for f, allowed in (("blast_radius", BLAST), ("likelihood", LIKELIHOOD), ("verdict", VERDICTS))):
            want = derive_priority(it)
            if it.get("priority") != want:
                problems.append(f"{where}: priority {it.get('priority')} disagrees with derived {want}")
    return problems


def _by_repo(items):
    out = OrderedDict()
    for it in items:
        out.setdefault(it["repo"], []).append(it)
    for repo in out:
        out[repo].sort(key=lambda it: (PRIORITIES.index(it["priority"]), it["id"]))
    return out


def _md_item(it):
    lines = [
        f"### {it['id']} · {it['priority']} · {it['kind']} · effort {it['effort']}",
        "",
        f"**{it['title']}**",
        "",
        f"- Failure surface: {it['failure_surface']}",
        f"- First fork: {it['first_fork']}",
        "- Evidence: " + ", ".join(f"`{e}`" for e in it["evidence"]),
        f"- Lens: {it.get('lens', '-')} · likelihood {it['likelihood']} · blast {it['blast_radius']} · verdict {it['verdict']} · status {it.get('status', 'open')}",
    ]
    if it.get("verdict_note"):
        lines.append(f"- Verifier note: {it['verdict_note']}")
    if it.get("families"):
        lines.append("- #550 families: " + ", ".join(str(f) for f in it["families"]))
    if it.get("wargame"):
        lines.append(f"- War game: `{it['wargame']}`")
    lines.append("")
    return "\n".join(lines)


def render_repo(repo, items):
    counts = Counter(it["priority"] for it in items)
    kinds = Counter(it["kind"] for it in items)
    head = [
        f"# War-game candidates — {repo}",
        "",
        "Generated from `catalog.ndjson` by `tools/wargame_catalog.py render`; do not hand-edit.",
        "",
        f"{len(items)} candidates · " + " · ".join(f"{p} {counts.get(p, 0)}" for p in PRIORITIES)
        + f" · defend {kinds.get('defend', 0)} · elevate {kinds.get('elevate', 0)}",
        "",
        "| id | P | kind | title |",
        "|---|---|---|---|",
    ]
    for it in items:
        head.append(f"| {it['id']} | {it['priority']} | {it['kind']} | {it['title'].replace('|', '/')} |")
    head.append("")
    head.append("---")
    head.append("")
    body = [_md_item(it) for it in items]
    return "\n".join(head + body)


def load_families():
    path = CATALOG_DIR / FAMILIES_FILE
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in data.get("families", {}).items()}


def family_coverage(items, families):
    """Return (rows, uncovered): rows are (number, name, count) for every
    family in families.json, uncovered lists the numbers no entry maps to."""
    counts = Counter(f for it in items for f in (it.get("families") or []))
    rows = [(n, families[n], counts.get(n, 0)) for n in sorted(families)]
    uncovered = [n for n, _, c in rows if c == 0]
    return rows, uncovered


def render_index(items, reserve_count=0, families=None):
    families = families or {}
    by_repo = _by_repo(items)
    pri = Counter(it["priority"] for it in items)
    kinds = Counter(it["kind"] for it in items)
    like = Counter(it["likelihood"] for it in items)
    verd = Counter(it["verdict"] for it in items)
    status = Counter(it.get("status", "open") for it in items)
    lines = [
        "# NouGen war-game catalog",
        "",
        "Generated index. Source of truth is `catalog.ndjson`; regenerate with",
        "`python tools/wargame_catalog.py render` and gate with `render --check`.",
        "See `README.md` in this directory for doctrine, method and how to claim an entry.",
        "",
        f"**{len(items)} candidates** · " + " · ".join(f"{p} {pri.get(p, 0)}" for p in PRIORITIES),
        "",
        f"kind: defend {kinds.get('defend', 0)} · elevate {kinds.get('elevate', 0)}  ",
        f"likelihood: observed {like.get('observed', 0)} · likely {like.get('likely', 0)} · speculative {like.get('speculative', 0)}  ",
        f"verdict: CONFIRMED {verd.get('CONFIRMED', 0)} · PLAUSIBLE {verd.get('PLAUSIBLE', 0)}  ",
        "status: " + " · ".join(f"{s} {status.get(s, 0)}" for s in STATUSES if status.get(s)) + "  ",
        f"reserve (verified but outside the 1000): {reserve_count}",
        "",
        "## By repo",
        "",
        "| repo | total | P0 | P1 | P2 | P3 | defend | elevate | file |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for repo, its in by_repo.items():
        c = Counter(it["priority"] for it in its)
        k = Counter(it["kind"] for it in its)
        lines.append(
            f"| {repo} | {len(its)} | {c.get('P0', 0)} | {c.get('P1', 0)} | {c.get('P2', 0)} | {c.get('P3', 0)} "
            f"| {k.get('defend', 0)} | {k.get('elevate', 0)} | [{slug(repo)}.md]({slug(repo)}.md) |"
        )
    lines += ["", "## P0 — game these first", ""]
    p0 = [it for it in items if it["priority"] == "P0"]
    p0.sort(key=lambda it: it["id"])
    lines.append("| id | repo | kind | title |")
    lines.append("|---|---|---|---|")
    for it in p0:
        lines.append(f"| {it['id']} | {it['repo']} | {it['kind']} | {it['title'].replace('|', '/')} |")
    lines.append("")
    if families:
        rows, uncovered = family_coverage(items, families)
        mapped = sum(1 for it in items if it.get("families"))
        lines += [
            "## Coverage of the #550 scenario families",
            "",
            f"{mapped} of {len(items)} entries map to at least one of the {len(families)} families in "
            f"`families.json` (NouGenShards#550). {len(uncovered)} families have no catalog entry yet"
            + (": " + ", ".join(str(n) for n in uncovered) if uncovered else "") + ".",
            "",
            "| # | family | entries |",
            "|---|---|---|",
        ]
        for n, name, c in rows:
            lines.append(f"| {n} | {name} | {c} |")
        lines.append("")
    return "\n".join(lines)


def rendered_files(items, reserve_count=0, families=None):
    """Map of filename -> content for everything render writes."""
    out = OrderedDict()
    out["INDEX.md"] = render_index(items, reserve_count, families)
    for repo, its in _by_repo(items).items():
        out[f"{slug(repo)}.md"] = render_repo(repo, its)
    return out


def cmd_validate(args):
    path = CATALOG_DIR / CATALOG_FILE
    if not path.exists():
        print(f"missing {path}")
        return 1
    items = load_ndjson(path)
    problems = validate_items(items)
    if problems:
        for p in problems[:200]:
            print(p)
        if len(problems) > 200:
            print(f"... {len(problems) - 200} more")
        print(f"INVALID: {len(problems)} problem(s) in {len(items)} records")
        return 1
    print(f"OK: {len(items)} records valid")
    return 0


def cmd_render(args):
    path = CATALOG_DIR / CATALOG_FILE
    items = load_ndjson(path)
    problems = validate_items(items)
    if problems:
        print(f"refusing to render an invalid catalog ({len(problems)} problem(s)); run validate")
        return 1
    reserve_path = CATALOG_DIR / RESERVE_FILE
    reserve_count = len(load_ndjson(reserve_path)) if reserve_path.exists() else 0
    files = rendered_files(items, reserve_count, load_families())
    stale = []
    for name, content in files.items():
        target = CATALOG_DIR / name
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current != content:
            stale.append(name)
            if not args.check:
                target.write_text(content, encoding="utf-8")
    if args.check:
        if stale:
            print("STALE: " + ", ".join(stale))
            return 1
        print(f"OK: {len(files)} rendered files are current")
        return 0
    print(f"rendered {len(files)} files ({len(stale)} changed) into {CATALOG_DIR}")
    return 0


def cmd_stats(args):
    items = load_ndjson(CATALOG_DIR / CATALOG_FILE)
    stats = {
        "total": len(items),
        "by_priority": dict(Counter(it["priority"] for it in items)),
        "by_kind": dict(Counter(it["kind"] for it in items)),
        "by_repo": dict(Counter(it["repo"] for it in items)),
        "by_likelihood": dict(Counter(it["likelihood"] for it in items)),
        "by_verdict": dict(Counter(it["verdict"] for it in items)),
        "by_status": dict(Counter(it.get("status", "open") for it in items)),
    }
    families = load_families()
    if families:
        rows, uncovered = family_coverage(items, families)
        stats["families_mapped_entries"] = sum(1 for it in items if it.get("families"))
        stats["families_uncovered"] = uncovered
    if args.json:
        print(json.dumps(stats, indent=2, sort_keys=True))
    else:
        for k, v in stats.items():
            print(f"{k}: {v}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    r = sub.add_parser("render")
    r.add_argument("--check", action="store_true", help="exit 1 if rendered markdown is stale")
    s = sub.add_parser("stats")
    s.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    return {"validate": cmd_validate, "render": cmd_render, "stats": cmd_stats}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

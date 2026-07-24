#!/usr/bin/env python
"""Drill runner -- execute a scored drill and record a structured result.

WHY THIS EXISTS
---------------
`drills/` has held 100 scored drill definitions since 2026-07-06 and
`drill-runs/` was EMPTY. Nothing had ever been measured, so two live claims
about the coding lane had no local evidence either way:

  (a) that Opus 5 performs BETTER at medium/low reasoning effort than at
      high/max, and
  (b) that dense, instruction-heavy skill files DEGRADE its instruction-
      following versus a small fresh prompt.

Both are expensive if true (the playbook defaults to effort HIGH and the owner
maintains 20+ dense writing skills) and neither is settled by argument. This
runner is the smallest honest instrument that could ever settle them.

WHAT IT DOES NOT DO
-------------------
It does not run an A/B. One run is a data point, not evidence. See
`docs/drill-ab-protocol.md` for what a valid comparison actually requires --
above all that reasoning effort is a SESSION-level setting, so the arms must be
separate sessions over the same drill set, never varied mid-run.

THE HEADLINE METRIC: NUDGES
---------------------------
`nudges` = how many "keep going" prods the operator had to send before the task
was GENUINELY complete (not before the agent claimed completion). That is the
specific regression the third-party review alleges, and it is the sharpest
falsifiable signal available: it is an integer, the operator observes it
directly, and it does not depend on trusting the agent's self-report.

It is also the easiest number in this file to corrupt. An automated executor
runs one function to completion with nobody to nudge, so it would emit
`nudges: 0` forever -- a stream of fake evidence "disproving" the claim. Every
record therefore carries `nudge_source`, and only `operator_observed` counts:

    operator_observed      -- a human/Coach ran an agent and counted. VALID.
    not_applicable_auto    -- structurally zero, an artifact of the harness.
                              NOT evidence about any model. Excluded from any
                              aggregate by `--valid-nudges-only`.

Rule 0.2: drill dir, runs dir, recall limit, and top-N all resolve
env -> CLI -> logged constant fallback.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import socket
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

SCHEMA_VERSION = 1


def _env_path(name: str, fallback: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    return Path(raw) if raw else fallback


def _env_int(name: str, fallback: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or fallback)
    except (TypeError, ValueError):
        return fallback


DRILL_DIR = _env_path("NOUGEN_DRILL_DIR", REPO_ROOT / "drills")
RUNS_DIR = _env_path("NOUGEN_DRILL_RUNS_DIR", REPO_ROOT / "drill-runs")
RECALL_LIMIT = _env_int("NOUGEN_DRILL_RECALL_LIMIT", 5)

# ---------------------------------------------------------------------------
# Drill parsing -- the definitions are the source of truth, not a copy of them.
# ---------------------------------------------------------------------------
_HEADER_RE = re.compile(r"^###\s+([A-Z]+-\d+):\s*(.+?)\s*$", re.MULTILINE)
_FIELD_RE = re.compile(r"^-\s+\*\*(\w[\w ]*)\*\*:\s*(.+?)\s*$", re.MULTILINE)


def parse_drills(drill_dir: Path = DRILL_DIR) -> Dict[str, dict]:
    """Parse every `### <CAT>-<NN>: <name>` block out of drills/*.md."""
    drills: Dict[str, dict] = {}
    for path in sorted(drill_dir.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        headers = list(_HEADER_RE.finditer(text))
        for i, hit in enumerate(headers):
            end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
            body = text[hit.end():end]
            fields = {k.strip().lower(): v.strip() for k, v in _FIELD_RE.findall(body)}
            drill_id = hit.group(1)
            drills[drill_id] = {
                "id": drill_id,
                "name": hit.group(2),
                "category": drill_id.split("-")[0],
                "file": str(path.relative_to(REPO_ROOT)),
                "trains": fields.get("trains", ""),
                "input": fields.get("input", ""),
                "task": fields.get("task", ""),
                "expect": fields.get("expect", ""),
                "fail_signals": fields.get("fail signals", ""),
            }
    return drills


# ---------------------------------------------------------------------------
# Executors
#
# Only RECALL is mechanically executable today: it queries the live vault and
# the pass condition ("correct shard handle in top-N") is checkable without a
# judge. Every other category asks an AGENT for prose, a diff, or a critique,
# and its Expect line is judged, not computed -- so those record as `manual`
# runs that carry the prompt and take operator-supplied scoring.
# ---------------------------------------------------------------------------
AUTO_CATEGORIES = {"RECALL"}


def _run_recall(drill: dict, expect_match: Optional[str], limit: int) -> dict:
    """Execute a RECALL drill against the live vault. Read-only."""
    from nougen_shards import core

    query = drill["input"]
    m = re.search(r"query\s*'([^']+)'", query) or re.search(r"query\s*\"([^\"]+)\"", query)
    if m:
        query = m.group(1)

    started = time.perf_counter()
    try:
        results = core.retrieve(query, limit=limit) or []
        error = None
    except Exception as exc:  # noqa: BLE001 - a crashed drill is a recorded FAIL
        results, error = [], f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started

    handles, evidence = [], []
    for rank, shard in enumerate(results, 1):
        title = str(shard.get("title") or "")
        handle = f"id={shard.get('id')} db={shard.get('_db_index')}"
        handles.append({
            "rank": rank,
            "handle": handle,
            "title": title[:120],
            "provenance_tier": shard.get("_provenance_tier"),
        })

    passed: Optional[bool] = None
    method = "unscored (no --expect-match supplied)"
    if error:
        passed, method = False, "executor raised"
    elif expect_match:
        pat = re.compile(expect_match, re.IGNORECASE)
        method = f"regex {expect_match!r} over title+content of top-{limit}"
        for rank, shard in enumerate(results, 1):
            blob = f"{shard.get('title') or ''}\n{shard.get('content') or ''}"
            hit = pat.search(blob)
            if hit:
                passed = True
                evidence.append({
                    "rank": rank,
                    "handle": f"id={shard.get('id')} db={shard.get('_db_index')}",
                    "title": str(shard.get("title") or "")[:120],
                    "matched": hit.group(0)[:80],
                })
        if passed is None:
            passed = False

    vault = core.vault_report()
    return {
        "executor": "recall_auto",
        "query_used": query,
        "wall_clock_s": round(elapsed, 4),
        "result_count": len(results),
        "handles": handles,
        "passed": passed,
        "scoring_method": method,
        "evidence": evidence,
        "error": error,
        "substrate": {
            "vault_dir": vault["vault_dir"],
            "vault_source": vault["source"],
            "db_count": vault["db_count"],
            "shard_count": vault["shard_count"],
        },
    }


def _run_manual(drill: dict) -> dict:
    """Record a drill that needs an agent + judge. Emits the prompt to hand over."""
    return {
        "executor": "manual",
        "wall_clock_s": None,
        "passed": None,
        "scoring_method": "judge required (Expect line is prose, not computable)",
        "evidence": [],
        "error": None,
        "agent_prompt": (
            f"{drill['task']}\n\nInput: {drill['input']}\n"
            f"Expected output shape: {drill['expect']}"
        ),
    }


# ---------------------------------------------------------------------------
# Token metering
# ---------------------------------------------------------------------------
def _token_usage() -> dict:
    """Probed, not assumed (Rule 0.2). No local session meter exists today."""
    try:
        from nougen_shards import billing  # noqa: F401
        available = hasattr(billing, "log_usage")
    except Exception:  # noqa: BLE001
        available = False
    return {
        "tokens": None,
        "available": False,
        "reason": (
            "no session-level token meter in this repo; billing.log_usage is a "
            "remote usage SINK (it records what a caller already spent), not a "
            "counter this process can read"
            if available else "billing module not importable"
        ),
        "hook": "set NOUGEN_DRILL_TOKENS_JSON to a file the caller writes per run",
    }


def _external_tokens() -> Optional[dict]:
    raw = os.environ.get("NOUGEN_DRILL_TOKENS_JSON", "").strip()
    if not raw:
        return None
    try:
        return json.loads(Path(raw).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------
def _render_markdown(rec: dict) -> str:
    d, m, arm = rec["drill"], rec["metrics"], rec["arm"]
    lines = [
        f"# Drill run {rec['run_id']} — {d['id']}: {d['name']}",
        "",
        f"- **When**: {rec['timestamp']}",
        f"- **Drill**: `{d['id']}` ({d['category']}) — {d['file']}",
        f"- **Task**: {d['task']}",
        f"- **Expect**: {d['expect']}",
        f"- **Executor**: `{rec['result']['executor']}`",
        f"- **Result**: **{rec['scoring']['verdict']}** — {rec['scoring']['method']}",
        f"- **Wall clock**: {m['wall_clock_s']}s",
        f"- **Nudges**: {m['nudges']} (source: `{m['nudge_source']}`)",
        f"- **Tokens**: {m['tokens'] if m['tokens'] is not None else 'not captured'}"
        f" — {m['tokens_note']}",
        "",
        "## Arm (the A/B dimensions this run occupies)",
        f"- agent: `{arm['agent']}` | model: `{arm['model']}`",
        f"- reasoning_effort: `{arm['reasoning_effort']}` | "
        f"skill_profile: `{arm['skill_profile']}`",
        "",
        "## Evidence",
    ]
    for ev in rec["scoring"]["evidence"] or []:
        lines.append(f"- rank {ev.get('rank')} — {ev.get('handle')} — "
                     f"{ev.get('title')} — matched `{ev.get('matched')}`")
    if not rec["scoring"]["evidence"]:
        lines.append("- (none recorded)")
    lines += ["", "## Caveats"]
    lines += [f"- {c}" for c in rec["caveats"]]
    return "\n".join(lines) + "\n"


def record(rec: dict, runs_dir: Path = RUNS_DIR) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{rec['timestamp'][:10]}-{rec['drill']['id']}-{rec['arm']['agent']}-{rec['run_id']}"
    (runs_dir / f"{stem}.json").write_text(
        json.dumps(rec, indent=2, default=str), encoding="utf-8")
    md = runs_dir / f"{stem}.md"
    md.write_text(_render_markdown(rec), encoding="utf-8")
    return md


def run_drill(drill: dict, *, agent: str, model: str, effort: str, skill_profile: str,
              nudges: Optional[int], nudge_source: str, expect_match: Optional[str],
              limit: int, notes: str) -> dict:
    if drill["category"] in AUTO_CATEGORIES:
        result = _run_recall(drill, expect_match, limit)
    else:
        result = _run_manual(drill)

    caveats: List[str] = [
        "A SINGLE drill run is scaffolding, not evidence. It cannot support or "
        "refute any claim about reasoning effort or skill density.",
    ]

    # Nudge honesty gate -- the whole point of the metric.
    if result["executor"] != "manual" and nudge_source != "operator_observed":
        nudges, nudge_source = 0, "not_applicable_auto"
        caveats.append(
            "nudges=0 here is STRUCTURAL: an automated executor runs to "
            "completion with nobody to nudge. This is NOT evidence about any "
            "model's completion behavior and must be excluded from aggregates.")
    elif nudges is None:
        nudges, nudge_source = -1, "unrecorded"
        caveats.append("nudges unrecorded — operator did not supply a count.")
    else:
        caveats.append(
            "nudges is operator-observed: count prods sent before the task was "
            "GENUINELY complete, not before the agent claimed completion.")

    if result["passed"] is None:
        caveats.append("Unscored: this drill's Expect line needs a judge.")
    if effort == "unrecorded" or skill_profile == "unrecorded":
        caveats.append(
            "Arm incompletely labelled — an unlabelled run cannot join an A/B.")

    tok = _external_tokens()
    tok_meta = _token_usage()

    verdict = {True: "PASS", False: "FAIL", None: "UNSCORED"}[result["passed"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": uuid.uuid4().hex[:8],
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "drill": drill,
        "arm": {
            "agent": agent, "model": model,
            "reasoning_effort": effort, "skill_profile": skill_profile,
        },
        "metrics": {
            "wall_clock_s": result["wall_clock_s"],
            "nudges": nudges,
            "nudge_source": nudge_source,
            "tokens": tok,
            "tokens_note": tok_meta["reason"] if tok is None else "supplied by caller",
        },
        "scoring": {
            "verdict": verdict,
            "passed": result["passed"],
            "method": result["scoring_method"],
            "evidence": result["evidence"],
            "fail_signals_watched": drill["fail_signals"],
        },
        "result": result,
        "environment": {
            "host": socket.gethostname(),
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "notes": notes,
        "caveats": caveats,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run a NouGen drill and record the result.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="enumerate parsed drills")
    p_list.add_argument("--category", default=None)

    p_run = sub.add_parser("run", help="execute one drill and write drill-runs/")
    p_run.add_argument("--drill", required=True, help="drill id, e.g. RECALL-01")
    p_run.add_argument("--agent", default=os.environ.get("NOUGEN_AGENT", "unrecorded"))
    p_run.add_argument("--model", default=os.environ.get("NOUGEN_DRILL_MODEL", "unrecorded"))
    p_run.add_argument("--effort", default=os.environ.get("NOUGEN_DRILL_EFFORT", "unrecorded"),
                       help="SESSION-level reasoning effort this run was executed under")
    p_run.add_argument("--skill-profile", default=os.environ.get(
        "NOUGEN_DRILL_SKILL_PROFILE", "unrecorded"),
        help="dense | fresh | unrecorded — the skill-density arm")
    p_run.add_argument("--nudges", type=int, default=None,
                       help="operator-observed 'keep going' prods before GENUINE completion")
    p_run.add_argument("--nudge-source", default="unrecorded",
                       choices=["operator_observed", "unrecorded"])
    p_run.add_argument("--expect-match", default=None,
                       help="regex that must appear in a top-N result for a PASS")
    p_run.add_argument("--limit", type=int, default=RECALL_LIMIT)
    p_run.add_argument("--notes", default="")

    args = ap.parse_args(argv)
    drills = parse_drills()

    if args.cmd == "list":
        for did, d in sorted(drills.items()):
            if args.category and d["category"] != args.category.upper():
                continue
            auto = "auto" if d["category"] in AUTO_CATEGORIES else "manual"
            print(f"{did:<14} [{auto:<6}] {d['name']}")
        print(f"\n{len(drills)} drills parsed from {DRILL_DIR}")
        return 0

    drill = drills.get(args.drill.upper())
    if not drill:
        print(f"unknown drill {args.drill!r}; try `list`", file=sys.stderr)
        return 2

    rec = run_drill(
        drill, agent=args.agent, model=args.model, effort=args.effort,
        skill_profile=args.skill_profile, nudges=args.nudges,
        nudge_source=args.nudge_source, expect_match=args.expect_match,
        limit=args.limit, notes=args.notes)
    path = record(rec)
    print(f"{rec['scoring']['verdict']}  {drill['id']}  -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

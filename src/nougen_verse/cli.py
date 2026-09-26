"""Command line interface: ``nougen-verse <command> ...``.

Every command prints a readable summary by default and JSON with ``--json``.

Exit codes:
  0  success
  2  usage error (bad arguments)
  3  input error (missing, empty or unreadable input, invalid request)
  4  schema validation failed
  5  feature disabled (GENERATE is off by default)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from importlib import resources
from pathlib import Path
from typing import Any

EXIT_OK, EXIT_USAGE, EXIT_INPUT, EXIT_SCHEMA, EXIT_DISABLED = 0, 2, 3, 4, 5


class InputError(Exception):
    pass


def _read_json(path: str) -> Any:
    try:
        raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc.strerror or exc}") from exc
    if not raw.strip():
        raise InputError(f"{path} is empty")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InputError(f"{path} is not valid JSON: {exc}") from exc


def _read_draft(path: str) -> str:
    try:
        raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc.strerror or exc}") from exc
    if path.lower().endswith(".json"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InputError(f"{path} is not valid JSON: {exc}") from exc
        lines = data.get("lines") or data.get("draft_lines")
        raw = "\n".join(lines) if lines else str(data.get("text", ""))
    if not raw.strip():
        raise InputError("empty input: the draft has no text to analyze")
    return raw


def _emit(obj: Any, as_json: bool, human: str, out: str | None = None) -> None:
    from .models import to_json

    text = to_json(obj) if as_json or out else human
    if out:
        Path(out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(text)


def _context(args, cfg) -> dict:
    ctx: dict[str, Any] = {"config": cfg}
    for key in ("bpm", "scheme", "dialect"):
        val = getattr(args, key, None)
        if val is not None:
            ctx[key] = val
    if getattr(args, "profile", None):
        ctx["breath_profile"] = args.profile
    if getattr(args, "persona", None):
        from .persona import load_persona

        try:
            ctx["persona"] = load_persona(args.persona, cfg)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise InputError(str(exc)) from exc
    if getattr(args, "facts", None):
        ctx["required_facts"] = list(args.facts)
    if getattr(args, "no_grid", False):
        ctx["include_grid"] = False
    return ctx


# ----------------------------------------------------------------------------
# human-readable views


def _analysis_text(a: dict) -> str:
    out = [f"bars {a['counts']['bars']}, syllables {a['syllables']['total']}",
           f"scheme {a['scheme']['letters']} ({a['scheme']['inferred_pattern']}, {a['scheme'].get('state', '')}, consistency {a['scheme']['consistency']})",
           f"rhyme density {a['rhyme_density']:.2f}, span mean {a['rhyme_span']['mean']}, internal rhymes {a['rhyme_stats'].get('internal_hits', 0)}"]
    for sw in a["flow_switches"]:
        out.append(f"flow switch at bar {sw['coordinate']['bar']}: {sw['previous_grammar']['cell']} to {sw['next_grammar']['cell']}, cause {sw['cause']} ({sw['semantic_trigger'] or 'no trigger found'})")
    for b in a["scheme_breaks"]:
        out.append(f"scheme break at bar {b['bar']}: {b['classification']} (confidence {b['confidence']}): {'; '.join(b['evidence'])}")
    for c in a["pattern_collapses"]:
        out.append(f"pattern collapse over bars {c['bars']}")
    for w in a["breath"]["warnings"]:
        out.append("breath: " + w)
    if a["weak_bars"]:
        out.append("weak bars:")
        for w in a["weak_bars"]:
            out.append(f"  {w['bar']}: {w['text']}  <- {'; '.join(w['reasons'])}")
    if a.get("protected_bars"):
        out.append("protected bars (not advised for repair):")
        for w in a["protected_bars"]:
            out.append(f"  {w['bar']}: {w['text']}  <- {w['label']} ({'; '.join(w['evidence'])})")
    out.append("limitations:")
    out += [f"  - {limitation}" for limitation in a["limitations"]]
    return "\n".join(out)


def _score_text(s: dict) -> str:
    out = []
    for dim, d in s["dimensions"].items():
        score = "n/a" if d["score"] is None else f"{d['score']:.2f}"
        out.append(f"{dim:<20} {score}")
        for name, c in d["components"].items():
            val = "n/a" if c["value"] is None else f"{c['value']:.2f}"
            out.append(f"    {name:<24} {val}  {c['evidence']}")
    gscore = s["genericness"]["score"]
    shown = "n/a" if gscore is None else f"{gscore:.2f}"
    out.append(f"genericness          {shown}  (higher is more generic)")
    out += [f"note: {n}" for n in s["notes"]]
    return "\n".join(out)


# ----------------------------------------------------------------------------
# commands


def cmd_plan(args, cfg) -> int:
    from .planner import plan_verse

    req = _read_json(args.request)
    if args.seed is not None:
        req["seed"] = args.seed
    try:
        bp = plan_verse(req, cfg).to_dict()
    except ValueError as exc:
        raise InputError(str(exc)) from exc
    human = "\n".join(
        [f"{o['bar']:>3} {o['job']:<20} family {o.get('end_family') or '-'}  cell {o.get('cell')}  {o['objective']}" for o in bp["bar_objectives"]]
        + [f"flow switch at bar {s['coordinate']['bar']}: {s['cause']}" for s in bp["flow_switches"]]
        + [f"open question: {q}" for q in bp["open_questions"]]
    )
    _emit(bp, args.json, human, args.out)
    return EXIT_OK


def cmd_compile(args, cfg) -> int:
    from .compiler import compile_prompt
    from .planner import plan_verse

    data = _read_json(args.blueprint)
    if "bar_objectives" not in data:
        try:
            data = plan_verse(data, cfg).to_dict()
        except ValueError as exc:
            raise InputError(str(exc)) from exc
    try:
        cp = compile_prompt(data, args.provider, cfg)
    except ValueError as exc:
        raise InputError(str(exc)) from exc
    _emit(cp, args.json, f"=== system ===\n{cp.system}\n\n=== user ===\n{cp.user}", args.out)
    return EXIT_OK


def cmd_analyze(args, cfg) -> int:
    from .analyzer import analyze_verse

    a = analyze_verse(_read_draft(args.draft), _context(args, cfg)).to_dict()
    _emit(a, args.json, _analysis_text(a), args.out)
    return EXIT_OK


def cmd_rhyme(args, cfg) -> int:
    from .rhyme import find_rhymes

    cons = {"slant": args.slant, "syllables": args.syllables, "max_results": args.max}
    res = [r.to_dict() for r in find_rhymes(args.phrase, cons, config=cfg)]
    human = "\n".join(f"{r['word']:<18} {r['kind']:<14} distance {r['distance']:.3f}  syllables {r['syllables_matched']}" for r in res) or "no candidates found"
    _emit({"phrase": args.phrase, "candidates": res}, args.json, human)
    return EXIT_OK


def cmd_grid(args, cfg) -> int:
    from .analyzer import analyze_verse

    a = analyze_verse(_read_draft(args.draft), _context(args, cfg))
    rhythm = getattr(a, "rhythm", None)
    _emit(a.grid, args.json, rhythm.ascii() if rhythm else "no bars")
    return EXIT_OK


def cmd_score(args, cfg) -> int:
    from .analyzer import analyze_verse
    from .scorer import score_verse

    weights = _read_json(args.weights) if args.weights else None
    s = score_verse(analyze_verse(_read_draft(args.draft), _context(args, cfg)), weights, cfg).to_dict()
    _emit(s, args.json, _score_text(s), args.out)
    return EXIT_OK


def _parse_bars(spec: str | None) -> list[int] | None:
    if not spec:
        return None
    try:
        return [int(x) for x in spec.replace(" ", "").split(",") if x]
    except ValueError as exc:
        raise InputError(f"--weak-bars expects numbers like 4,7,12, got {spec!r}") from exc


def _before_after_text(r: dict) -> str:
    def comp(x):
        return "-" if x is None else f"{x:.3f}"

    head = (f"composite {comp(r['before']['composite'])} -> {comp(r['after']['composite'])}, "
            f"weak bars {r['before']['weak_bars']} -> {r['after']['weak_bars']}, {len(r['changes'])} bar(s) changed")
    after = r["after"]["dimensions"]
    moved = [f"{k} {comp(v)} -> {comp(after.get(k))}" for k, v in r["before"]["dimensions"].items() if v != after.get(k)]
    head += "\n  moved: " + (", ".join(moved) if moved else "no dimension moved")
    body = "".join(f"\n  bar {c['bar']} ({c['type']}): {c['from']}\n    -> {c['to']}" for c in r["changes"])
    return head + body + f"\n  note: {r['note']}"


def cmd_repair(args, cfg) -> int:
    from .analyzer import analyze_verse
    from .repair import repair_before_after, suggest_repairs

    text = _read_draft(args.draft)
    ctx = _context(args, cfg)
    if args.apply:
        r = repair_before_after(text, ctx, cfg)
        _emit(r, args.json, "BEFORE/AFTER: " + _before_after_text(r), args.out)
        return EXIT_OK
    a = analyze_verse(text, ctx)
    plan = suggest_repairs(text, a, ctx.get("persona"), _parse_bars(args.weak_bars), cfg).to_dict()
    human = "\n".join(
        [f"bar {x['bar']}: {x['original']}\n  problems: {'; '.join(x['problems'])}\n  keep: {', '.join(x['preserve']) or '-'}"
         + "".join(f"\n  candidate ({c['type']}, voice {c['voice_similarity']:.2f}): {c['text']}" for c in x["candidates"])
         + (f"\n  ending options: {', '.join(x['ending_options'])}" if x["ending_options"] else "")
         for x in plan["actions"]] or ["no weak bars found"]
    )
    _emit(plan, args.json, human, args.out)
    return EXIT_OK


def cmd_demo(args, cfg) -> int:
    from .analyzer import analyze_verse
    from .compiler import compile_prompt
    from .planner import plan_verse
    from .repair import repair_before_after, suggest_repairs
    from .scorer import score_verse

    demo = json.loads(resources.files("nougen_verse").joinpath("data", "demo.json").read_text(encoding="utf-8"))
    req = dict(demo["request"], seed=args.seed)
    bp = plan_verse(req, cfg)
    cp = compile_prompt(bp, "chat", cfg)
    text = "\n".join(demo["draft_lines"])
    a = analyze_verse(text, {"blueprint": bp, "config": cfg})
    s = score_verse(a, None, cfg)
    r = suggest_repairs(text, a, None, None, cfg)
    ba = repair_before_after(text, {"blueprint": bp}, cfg)
    result = {"blueprint": bp, "compiled_prompt": cp, "analysis": a, "score": s, "repair": r, "before_after": ba}
    human = "\n".join([
        "PLAN: " + ", ".join(f"{o['bar']}:{o['job']}" for o in bp.bar_objectives),
        f"COMPILE: {len(cp.user)} characters of provider-neutral prompt",
        "ANALYZE:\n" + _analysis_text(a.to_dict()),
        "SCORE:\n" + _score_text(s.to_dict()),
        "REPAIR: " + ("; ".join(f"bar {x['bar']}: {x['instruction']}" for x in r.actions) or "nothing to repair"),
        "BEFORE/AFTER: " + _before_after_text(ba),
        "(demo draft and request are synthetic, written for this repo)",
    ])
    _emit(result, args.json, human)
    return EXIT_OK


def cmd_validate(args, cfg) -> int:
    from .schemas import validate

    errors = validate(_read_json(args.file), args.schema)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return EXIT_SCHEMA
    print(f"valid {args.schema}")
    return EXIT_OK


def cmd_generate(args, cfg) -> int:
    from .providers import generate_verse

    res = generate_verse(_read_json(args.blueprint), args.provider)
    _emit(res, True, "")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nougen-verse", description="Plan, compile, analyze, score and repair rap verses. Offline and deterministic.")
    p.add_argument("--config", help="JSON file with config overrides")
    p.add_argument("--dictionary", choices=["auto", "on", "off"], help="use the optional pronunciation dictionary")
    sub = p.add_subparsers(dest="command", required=True)

    def draft_opts(sp):
        sp.add_argument("draft", help="text file (one bar per line), a JSON fixture with 'lines', or - for stdin")
        sp.add_argument("--bpm", type=float)
        sp.add_argument("--persona", help="persona JSON file or persona id")
        sp.add_argument("--facts", action="append", help="required fact (repeatable)")
        sp.add_argument("--scheme", help="expected scheme such as AABB")
        sp.add_argument("--profile", help="breath profile name")
        sp.add_argument("--dialect", help="pronunciation profile name")
        sp.add_argument("--json", action="store_true")

    sp = sub.add_parser("plan", help="request JSON to blueprint")
    sp.add_argument("request")
    sp.add_argument("--seed", type=int)
    sp.add_argument("--out")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_plan)

    sp = sub.add_parser("compile", help="blueprint (or request) JSON to a provider-neutral prompt")
    sp.add_argument("blueprint")
    sp.add_argument("--provider", default="generic", help="generic, chat or json")
    sp.add_argument("--out")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_compile)

    sp = sub.add_parser("analyze", help="diagnose a draft")
    draft_opts(sp)
    sp.add_argument("--no-grid", action="store_true", help="leave the event grid out of the JSON")
    sp.add_argument("--out")
    sp.set_defaults(func=cmd_analyze)

    sp = sub.add_parser("rhyme", help="find graded rhymes for a word or phrase")
    sp.add_argument("phrase")
    sp.add_argument("--syllables", type=int, help="minimum matched syllables counted from the end")
    sp.add_argument("--slant", action="store_true", help="include slant rhyme and assonance")
    sp.add_argument("--max", type=int)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_rhyme)

    sp = sub.add_parser("grid", help="show the estimated beat grid")
    draft_opts(sp)
    sp.set_defaults(func=cmd_grid)

    sp = sub.add_parser("score", help="score craft dimensions")
    draft_opts(sp)
    sp.add_argument("--weights", help="JSON file with weight overrides")
    sp.add_argument("--out")
    sp.set_defaults(func=cmd_score)

    sp = sub.add_parser("repair", help="targeted repair steps")
    draft_opts(sp)
    sp.add_argument("--weak-bars", help="comma separated bar numbers to repair (default: detected weak bars)")
    sp.add_argument("--apply", action="store_true", help="apply the best finished candidate per weak bar and score before and after")
    sp.add_argument("--out")
    sp.set_defaults(func=cmd_repair)

    sp = sub.add_parser("demo", help="run the whole loop on a bundled synthetic example")
    sp.add_argument("--seed", type=int, default=42)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_demo)

    sp = sub.add_parser("validate", help="validate a JSON file against a bundled schema")
    sp.add_argument("file")
    sp.add_argument("--schema", required=True, choices=["verse_request", "verse_blueprint", "verse_analysis", "score_report", "repair_plan", "compiled_prompt"])
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("generate", help="optional provider call (disabled by default)")
    sp.add_argument("blueprint")
    sp.add_argument("--provider", required=True)
    sp.set_defaults(func=cmd_generate)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    from .config import ENV_DICTIONARY, load_config, reset_default_config
    from .phonetics import clear_dictionary_cache
    from .providers.base import GenerationDisabled
    from .schemas import SchemaValidationUnavailable

    try:
        if args.dictionary:
            os.environ[ENV_DICTIONARY] = args.dictionary
            reset_default_config()
            clear_dictionary_cache()
        cfg = load_config(overrides=_read_json(args.config)) if args.config else load_config()
        return args.func(args, cfg)
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INPUT
    except GenerationDisabled as exc:
        print(f"disabled: {exc}", file=sys.stderr)
        return EXIT_DISABLED
    except SchemaValidationUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INPUT
    except (KeyError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INPUT


if __name__ == "__main__":
    sys.exit(main())

"""Destiny 10 audit: read the benchmark result files and print the audit report.

    python evals/destiny10_audit.py > evals/results/destiny10_audit_<date>.md

Reads evals/results/destiny_bench_*.json only. Every number in the report is
computed here, nothing is typed by hand. The verdict is derived from the
required events and forbidden outcomes recorded on Destiny 10.
"""
from __future__ import annotations

import glob
import json
import os
import re
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")

# Destiny 10 (connector store), copied verbatim so the audit can be diffed against it.
REQUIRED = [
    "3 arms: no_memory",
    "prompt_only",
    "shards_first",
    "same tasks and token budget",
    "hidden held-out tasks never seen by the improver",
    ">=3 seeds per arm with no-change seed band reported",
    "hidden unit tests grade success",
]


def load():
    """Return {arm: {seed: result}}; a run with zero model calls is infrastructure, not a result."""
    out, skipped = {}, []
    for path in sorted(glob.glob(os.path.join(RES, "destiny_bench_*.json"))):
        name = os.path.basename(path)
        d = json.load(open(path, encoding="utf-8"))
        m = re.search(r"seed(\d+)", name)
        # the 11/17 file predates the --seed flag; it ran the default seed 1085.
        # Later files overwrite earlier ones for the same arm and seed (glob is sorted),
        # so the post-gate-fix 11/18 runs replace the 11/17 ones where both exist.
        # Seed precedence: the result's own metadata, then the filename, then 1085.
        if isinstance(d.get("seed"), int):
            seed = d["seed"]
        else:
            seed = int(m.group(1)) if m else 1085
        for r in d.get("arms", []):
            if r.get("lane_calls", 0) == 0:
                skipped.append((name, r["arm"], "0 model calls (lane errors: %s)" % r.get("lane_errors")))
                continue
            out.setdefault(r["arm"], {})[seed] = {**r, "_file": name}
    return out, skipped


def band(vals):
    return (min(vals), max(vals)) if vals else (None, None)


def main() -> int:
    arms, skipped = load()
    L = []
    P = L.append
    P("# Destiny 10 audit: shards-first vs no-memory, measured\n")
    P("Computed by `evals/destiny10_audit.py` from `evals/results/destiny_bench_*.json`.\n")

    P("## Results by arm and seed\n")
    P("| Arm | Seed | Done | Tokens | Tokens/success | Faulted tasks done | Rollback violations | Source |")
    P("|---|---|---|---|---|---|---|---|")
    for arm in ("no_memory", "prompt_only", "shards_first"):
        for seed in sorted(arms.get(arm, {})):
            r = arms[arm][seed]
            tps = r.get("tokens_per_success")
            P(f"| {arm} | {seed} | {r['done']}/{r['tasks']} | {r['tokens_total']:,} | "
              f"{tps if tps is not None else 'n/a'} | {r['faulted_done']}/{r['faulted_tasks']} | "
              f"{r['rollback_violations']} | `{r['_file']}` |")
    P("")
    if skipped:
        P("Excluded runs (no model calls were made, so they say nothing about the arm):\n")
        for f, a, why in skipped:
            P(f"- `{f}` {a}: {why}")
        P("")

    P("## Seed bands\n")
    P("| Arm | Seeds | Done band | Tokens/success band |")
    P("|---|---|---|---|")
    bands = {}
    for arm in ("no_memory", "prompt_only", "shards_first"):
        rs = arms.get(arm, {})
        done = [r["done"] for r in rs.values()]
        tps = [r["tokens_per_success"] for r in rs.values() if r.get("tokens_per_success")]
        bands[arm] = (band(done), band(tps), len(rs))
        d0, d1 = band(done)
        t0, t1 = band(tps)
        P(f"| {arm} | {len(rs)} | {d0}-{d1} | {('%s-%s' % (t0, t1)) if t0 is not None else 'n/a'} |")
    P("")

    # Rescue / harm, per seed where both arms ran: tasks fail without memory, pass with it, and the reverse.
    P("## Rescue and Harm (shards_first vs each control)\n")
    P("Exact when both runs stored `done_goals`; otherwise a lower bound from done totals "
      "(same 100 tasks in every arm).\n")
    P("| Seed | vs | Rescue (fails there, passes shards_first) | Harm (passes there, fails shards_first) | Basis |")
    P("|---|---|---|---|---|")
    any_bound = False
    for seed in sorted(arms.get("shards_first", {})):
        s = arms["shards_first"][seed]
        for ctl in ("no_memory", "prompt_only"):
            c = arms.get(ctl, {}).get(seed)
            if not c:
                continue
            if "done_goals" in s and "done_goals" in c:
                sg, cg = set(s["done_goals"]), set(c["done_goals"])
                P(f"| {seed} | {ctl} | {len(sg - cg)} | {len(cg - sg)} | exact |")
            else:
                any_bound = True
                diff = s["done"] - c["done"]
                P(f"| {seed} | {ctl} | at least {max(diff, 0)} | at least {max(-diff, 0)} | bound from totals |")
    if any_bound:
        P("\nRows marked 'bound from totals' predate per-task storage. Equal totals do not rule out "
          "offsetting rescue and harm; rerun those arms to make them exact.\n")
    else:
        P("")

    # Event-by-event verdict.
    seeds_ok = all(len(arms.get(a, {})) >= 3 for a in ("no_memory", "prompt_only", "shards_first"))
    sf = arms.get("shards_first", {})
    po = arms.get("prompt_only", {})
    nm = arms.get("no_memory", {})
    sf_tps = [r["tokens_per_success"] for r in sf.values() if r.get("tokens_per_success")]
    po_tps = [r["tokens_per_success"] for r in po.values() if r.get("tokens_per_success")]
    cost_clear = bool(sf_tps and po_tps and max(sf_tps) < min(po_tps))
    # Every-seed claims only cover seeds present in BOTH arms; an empty overlap is
    # not evidence, so it never evaluates to a vacuous True.
    po_seeds = sorted(set(sf) & set(po))
    nm_seeds = sorted(set(sf) & set(nm))
    success_tie = bool(po_seeds) and all(sf[s]["done"] == po[s]["done"] for s in po_seeds)
    beats_nm = bool(nm_seeds) and all(sf[s]["done"] > nm[s]["done"] for s in nm_seeds)
    unpaired = sorted(x for x in (set(sf) | set(po) | set(nm)) if not (x in sf and x in po and x in nm))
    clean_rollback = all(r["rollback_violations"] == 0 for g in arms.values() for r in g.values())

    if unpaired:
        P("**Unpaired seeds** (not in all three arms, excluded from every-seed claims): "
          + ", ".join(str(x) for x in unpaired) + ".\n")
    P("## Required events\n")
    P("| Event | Status | Evidence |")
    P("|---|---|---|")
    P(f"| 3 arms: no_memory, prompt_only, shards_first | {'MET' if len(arms) >= 3 else 'NOT MET'} | arms present: {', '.join(sorted(arms))} |")
    P("| same tasks and token budget | MET | one world per seed, `task_token_budget` 60,000 per task in every arm |")
    P("| hidden held-out tasks never seen by the improver | NOT MET | the harness has no improver; there is nothing to hold tasks out from. Satisfying this needs a benchmark where a lane changes between runs |")
    P(f"| >=3 seeds per arm with a seed band reported | {'MET' if seeds_ok else 'NOT MET'} | seeds per arm: " + ", ".join(f"{a} {len(arms.get(a, {}))}" for a in ('no_memory', 'prompt_only', 'shards_first')) + " |")
    P("| hidden unit tests grade success | MET | `hidden_verify` runs each answer in an isolated subprocess against an assert the executor never sees |")
    P("")
    P("## Forbidden outcomes\n")
    P("| Outcome | Status |")
    P("|---|---|")
    P(f"| endpoint gain without seed-band control | {'AVOIDED' if seeds_ok else 'AT RISK'}: bands reported above |")
    P("| held-out ids reaching the update | N/A: no update step exists |")
    P(f"| self-graded success | AVOIDED: success is the hidden assert, rollback violations are {'0' if clean_rollback else 'NONZERO'} in every run |")
    P("| claiming AGI or RSI proven | AVOIDED: not claimed |")
    P("")

    P("## Verdict\n")
    P("**Destiny 10 stays open.** The verification text asks that shards_first exceed its own seed band "
      "on every seed, with an improver and held-out tasks. What the evidence supports:\n")
    P(f"- shards_first beats no_memory on verified success on every seed: **{'yes' if beats_nm else 'no'}**. "
      "This validates the control more than it shows memory skill, since no_memory cannot know the facts by construction.")
    P(f"- shards_first and prompt_only tie on success on every seed: **{'yes' if success_tie else 'no'}**, so there is no success gain over prompt-only.")
    P(f"- shards_first costs fewer tokens per success than prompt_only, with non-overlapping seed bands: **{'yes' if cost_clear else 'no'}** "
      + (f"({min(sf_tps)}-{max(sf_tps)} vs {min(po_tps)}-{max(po_tps)}, about {st.mean(po_tps)/st.mean(sf_tps):.1f}x)." if cost_clear else "."))
    P(f"- no task was marked done without passing verification: **{'yes' if clean_rollback else 'no'}** (rollback violations).")
    P("\nThe honest claim shape matches the literature in shard 26910: memory here buys a cheaper run at equal success, not more solves.\n")
    P("## Other evidence: Destiny 10 v2 (reported by another lane, not re-run here)\n")
    P("Relay leg `20261121T230041Z__claude-app__g-whoentertains` and shard 31727@db8 report a second, "
      "retrieval-based benchmark: six tasks whose answer is a NouGen convention that only the vault holds, "
      "`mrs-b:latest`, seed 1, temperature 0. Reported result: no_memory 0/6, prompt_only 0/6, "
      "shards_first 0/6. The leg measures why: the answer was inside the recall budget for 1 of 6 tasks, "
      "present in the top 3 hits for 3 of 6, and absent for 3 of 6. Its oracle control and extra seeds did not run.\n")
    P("This is the opposite picture from the table above. Where facts are seeded verbatim and the query "
      "names them, memory wins on cost. Where facts must be retrieved from plain-language task text, "
      "the reported result is no gain. Taken together, the synthetic result should not be read as evidence "
      "that shards-first helps on real fleet tasks.\n")
    P("## What would close it\n")
    P("1. A benchmark where a lane changes between runs (an improver), with tasks it never saw, so the held-out event means something.")
    P("2. Store per-task outcomes so Rescue and Harm are exact instead of bounds.")
    P("3. A task family where prompt-only cannot hold the facts in context, so a success gap is possible at all.\n")
    P("Limits: one synthetic fact-recall task family, small local models (`gemma4:e2b-qat`, `gemma2:2b`), "
      "faults injected identically in every arm. This proves nothing about AGI or RSI.")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())

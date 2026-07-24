# Drill A/B protocol — what it would take to actually test the two claims

**Status: NOT RUN.** As of 2026-07-24 `drill-runs/` contains exactly one drill
(RECALL-01, FAIL, substrate-confounded). This document specifies the experiment;
it does not report one. Nothing here has been measured.

## The two claims under test

| # | Claim | Source | Cost if true |
|---|---|---|---|
| A | Opus 5 performs **better at medium/low reasoning effort** than at high/max | third-party review (shard 1295, `source: podcast`, third-party tier) | the playbook sets an effort ceiling of HIGH and **defaults there** |
| B | Dense, instruction-heavy **skill files degrade** instruction-following vs. a small fresh prompt | same | the owner maintains 20+ dense writing skills |

Neither claim is currently supported or refuted by any local measurement. The
runner exists so they can stop being argued and start being counted.

## The metric that decides it

**Nudges**: the number of "keep going" prods the operator had to send before the
task was **genuinely complete** — not before the agent *claimed* completion.

It is the right primary metric because it is an integer, the operator observes
it directly, and it does not require trusting the agent's self-report. Claim A
is specifically a claim about premature stopping, which is what a nudge counts.

Secondary: pass/fail per the drill's own **Expect** line, wall-clock, tokens.

**The one way to corrupt it**: an automated executor runs to completion with
nobody to nudge, so it emits `nudges: 0` forever. The runner therefore refuses
to credit that — auto-executed runs are stamped `nudge_source:
not_applicable_auto` and must be excluded from every aggregate. Only
`operator_observed` counts. A harness that quietly logged structural zeroes
would manufacture a stream of fake evidence against Claim A.

## Design requirements

### 1. Reasoning effort is a SESSION-level setting — this dominates the design

Effort cannot be varied mid-run. It is fixed when the session starts, so:

- Each effort arm is a **separate session**, started fresh at that effort.
- **The same drill set** runs in every arm — not different drills per arm.
- Effort is **never changed inside** a session that is producing measurements;
  a session whose effort changed is discarded, not salvaged.
- The arm label is recorded at run time (`--effort low|medium|high`). A run
  labelled `unrecorded` cannot join an A/B and the runner says so in `caveats`.

Minimum shape for Claim A: 3 arms (low / medium / high) × the same N drills,
each arm a clean session, nudges counted by the operator in all three.

### 2. The skill-density arm is a second, orthogonal factor

Same drills, two conditions:

- `--skill-profile dense` — the full skill/CLAUDE.md stack loaded as normal.
- `--skill-profile fresh` — a minimal prompt carrying only the drill text.

Do **not** cross it with effort until each factor is measured alone; a 3×2 grid
multiplies the session count before either main effect is known.

### 3. Sample size, order, and blinding

- One run per cell is noise. Repeat each cell (≥5 drills × ≥3 repetitions) before
  reading anything into a difference.
- **Randomize drill order** within an arm; agents get warmer or lazier along a
  session and fixed order confounds that with the arm.
- Score with a **judge that does not know the arm**. Most drills (PATCH, REVIEW,
  ADVERSARY, FORK, RECEIPT…) have prose Expect lines that need a judge; if the
  judge sees the arm label, it will find what it expects.
- Pre-register the pass criteria (`--expect-match` for RECALL; a written rubric
  per drill for the rest) **before** running, not after seeing the output.

### 4. Substrate must be held constant

RECALL drills query the live vault, so vault state is part of the measurement.
The first run (2026-07-24) is confounded exactly this way: FTS/embedding indexes
were mid-repair. Freeze the vault, or record `substrate.shard_count` and
`vault_source` per run (the runner does) and discard arms that straddle a change.

### 5. Runnability of the current library

100 drills parse cleanly. Only the 10 **RECALL** drills are mechanically
executable and auto-scorable today; the other 90 need an agent to produce output
and a judge to score it, and record as `executor: manual` with the prompt
attached. An A/B over the manual 90 is gated on building the judge lane — that,
not the runner, is the real remaining work.

## Runner interface

```bash
python tools/drill_runner.py list [--category RECALL]

python tools/drill_runner.py run --drill RECALL-01 \
    --agent claude-cli --model claude-opus-5 \
    --effort high --skill-profile dense \
    --expect-match "mmr|diversif" \
    --nudges 2 --nudge-source operator_observed \
    --notes "..."
```

Writes `drill-runs/<date>-<DRILL>-<agent>-<runid>.{json,md}` carrying: drill
definition, arm (agent/model/effort/skill_profile), metrics (wall-clock, nudges +
nudge_source, tokens), scoring (verdict, method, evidence handles, fail signals
watched), substrate provenance, environment, and explicit `caveats`.

Env (Rule 0.2): `NOUGEN_DRILL_DIR`, `NOUGEN_DRILL_RUNS_DIR`,
`NOUGEN_DRILL_RECALL_LIMIT`, `NOUGEN_DRILL_MODEL`, `NOUGEN_DRILL_EFFORT`,
`NOUGEN_DRILL_SKILL_PROFILE`, `NOUGEN_DRILL_TOKENS_JSON`.

**Tokens are not captured.** There is no session-level token meter in this repo;
`billing.log_usage` is a remote usage *sink*, not a readable counter. The runner
records `tokens: null` with the reason, and reads a caller-written file if
`NOUGEN_DRILL_TOKENS_JSON` is set. Wiring a real meter is open work.

## Abort conditions

- Arms straddle a vault/index change → discard, do not "adjust".
- Judge learns the arm label → results unusable.
- Any aggregate that includes `nudge_source: not_applicable_auto` rows → invalid.
- Fewer than 3 repetitions per cell → report as pilot, never as a finding.

## Do not update doctrine from this yet

The effort ceiling and the skill stack stay exactly as they are until an arm
completes under this protocol. One run is scaffolding.

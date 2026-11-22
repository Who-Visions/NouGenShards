# Destiny 10 audit: shards-first vs no-memory, measured

Computed by `evals/destiny10_audit.py` from `evals/results/destiny_bench_*.json`.

## Results by arm and seed

| Arm | Seed | Done | Tokens | Tokens/success | Faulted tasks done | Rollback violations | Source |
|---|---|---|---|---|---|---|---|
| no_memory | 1085 | 0/100 | 304,328 | n/a | 0/30 | 0 | `destiny_bench_20261117.json` |
| no_memory | 1086 | 0/100 | 320,495 | n/a | 0/30 | 0 | `destiny_bench_nomem_seed1086.json` |
| no_memory | 1087 | 0/100 | 315,929 | n/a | 0/30 | 0 | `destiny_bench_nomem_seed1087.json` |
| prompt_only | 1085 | 100/100 | 172,875 | 1729 | 21/21 | 0 | `destiny_bench_20261118_seed1085.json` |
| prompt_only | 1086 | 100/100 | 173,158 | 1732 | 21/21 | 0 | `destiny_bench_20261118_seed1086.json` |
| prompt_only | 1087 | 100/100 | 173,245 | 1732 | 21/21 | 0 | `destiny_bench_20261118_seed1087.json` |
| shards_first | 1085 | 100/100 | 33,725 | 337 | 21/21 | 0 | `destiny_bench_20261118_seed1085.json` |
| shards_first | 1086 | 100/100 | 34,296 | 343 | 21/21 | 0 | `destiny_bench_20261118_seed1086.json` |
| shards_first | 1087 | 100/100 | 33,917 | 339 | 21/21 | 0 | `destiny_bench_20261118_seed1087.json` |

## Seed bands

| Arm | Seeds | Done band | Tokens/success band |
|---|---|---|---|
| no_memory | 3 | 0-0 | n/a |
| prompt_only | 3 | 100-100 | 1729-1732 |
| shards_first | 3 | 100-100 | 337-343 |

## Rescue and Harm (per task count, shards_first vs each control)

Counts are derived from done totals because both controls and shards_first run the same 100 tasks.

| Seed | vs | Rescue (fails there, passes shards_first) | Harm (passes there, fails shards_first) |
|---|---|---|---|
| 1085 | no_memory | at least 100 | at least 0 |
| 1085 | prompt_only | at least 0 | at least 0 |
| 1086 | no_memory | at least 100 | at least 0 |
| 1086 | prompt_only | at least 0 | at least 0 |
| 1087 | no_memory | at least 100 | at least 0 |
| 1087 | prompt_only | at least 0 | at least 0 |

Per-task outcomes were not stored, so these are lower bounds from totals. Equal totals do not rule out offsetting rescue and harm.

## Required events

| Event | Status | Evidence |
|---|---|---|
| 3 arms: no_memory, prompt_only, shards_first | MET | arms present: no_memory, prompt_only, shards_first |
| same tasks and token budget | MET | one world per seed, `task_token_budget` 60,000 per task in every arm |
| hidden held-out tasks never seen by the improver | NOT MET | the harness has no improver; there is nothing to hold tasks out from. Satisfying this needs a benchmark where a lane changes between runs |
| >=3 seeds per arm with a seed band reported | MET | seeds per arm: no_memory 3, prompt_only 3, shards_first 3 |
| hidden unit tests grade success | MET | `hidden_verify` runs each answer in an isolated subprocess against an assert the executor never sees |

## Forbidden outcomes

| Outcome | Status |
|---|---|
| endpoint gain without seed-band control | AVOIDED: bands reported above |
| held-out ids reaching the update | N/A: no update step exists |
| self-graded success | AVOIDED: success is the hidden assert, rollback violations are 0 in every run |
| claiming AGI or RSI proven | AVOIDED: not claimed |

## Verdict

**Destiny 10 stays open.** The verification text asks that shards_first exceed its own seed band on every seed, with an improver and held-out tasks. What the evidence supports:

- shards_first beats no_memory on verified success on every seed: **yes**. This validates the control more than it shows memory skill, since no_memory cannot know the facts by construction.
- shards_first and prompt_only tie on success on every seed: **yes**, so there is no success gain over prompt-only.
- shards_first costs fewer tokens per success than prompt_only, with non-overlapping seed bands: **yes** (337-343 vs 1729-1732, about 5.1x).
- no task was marked done without passing verification: **yes** (rollback violations).

The honest claim shape matches the literature in shard 26910: memory here buys a cheaper run at equal success, not more solves.

## Other evidence: Destiny 10 v2 (reported by another lane, not re-run here)

Relay leg `20261121T230041Z__claude-app__g-whoentertains` and shard 31727@db8 report a second, retrieval-based benchmark: six tasks whose answer is a NouGen convention that only the vault holds, `mrs-b:latest`, seed 1, temperature 0. Reported result: no_memory 0/6, prompt_only 0/6, shards_first 0/6. The leg measures why: the answer was inside the recall budget for 1 of 6 tasks, present in the top 3 hits for 3 of 6, and absent for 3 of 6. Its oracle control and extra seeds did not run.

This is the opposite picture from the table above. Where facts are seeded verbatim and the query names them, memory wins on cost. Where facts must be retrieved from plain-language task text, the reported result is no gain. Taken together, the synthetic result should not be read as evidence that shards-first helps on real fleet tasks.

## What would close it

1. A benchmark where a lane changes between runs (an improver), with tasks it never saw, so the held-out event means something.
2. Store per-task outcomes so Rescue and Harm are exact instead of bounds.
3. A task family where prompt-only cannot hold the facts in context, so a success gap is possible at all.

Limits: one synthetic fact-recall task family, small local models (`gemma4:e2b-qat`, `gemma2:2b`), faults injected identically in every arm. This proves nothing about AGI or RSI.

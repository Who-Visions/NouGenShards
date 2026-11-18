# Destiny task reconciler benchmark — 2026-11-17

Run: `python evals/destiny_bench.py --n 100` against PR #1096 head a9115c2
(`destiny_task_reconciler.py`). Started 10:03 AM EST, finished 11:23 AM EST Tue 11/17
(15:03Z–16:23Z). Local lanes only: `gemma4:e2b-qat` primary, `gemma2:2b` alternate, $0.
Single seed (1085). Raw data: `destiny_bench_20261117.json`, stderr: `.log`.

World: 25 config facts for project Kestrel plus 75 distractor facts (Osprey/Heron/Plover).
100 tasks = 25 facts x 4 transforms; each must emit `answer()` that passes a hidden assert.
Faults injected identically in every arm: route timeout on every 5th task's first call,
a worker crash (lease expiry + re-claim) on 10 tasks.

| Arm | Done | First-attempt | Tokens | Tokens/success | Recovery (faulted done/faulted) | Lost to faults | Rollback violations | Wall |
|---|---|---|---|---|---|---|---|---|
| no_memory | 0/100 | 0 | 304,328 | — | 0/30 | 0 | 0 | 70 min |
| prompt_only | 96/100 | 96 | 166,249 | 1,732 | 21/21 | 0 | 0 | 3.7 min |
| shards_first | 96/100 | 96 | 32,634 | 340 | 21/21 | 0 | 0 | 5.8 min |

Readings:
- shards_first matches prompt_only on verified success and spends 5.1x fewer tokens
  (bounded recall puts only the relevant facts in the prompt instead of all 100).
- no_memory cannot know the facts: 96 tasks exhausted 3 attempts across strategies and
  ended `failed`, none were falsely marked done — 0 rollback violations means no evidence
  shard and no relay leg was ever written for a task that did not pass verification.
- Every injected crash and timeout was recovered in both memory arms (lease fencing +
  re-claim); no task was lost or double-completed.
- The 4 tasks not done in each arm are all "token budget in thousands": the safety gate's
  `\btoken\b` pattern blocks them before any model call. That is the gate working as
  written, and also a false positive worth narrowing (follow-up, not changed here).

Limits: one seed, one synthetic retrieval-heavy task family, small local models. It shows
the loop's control behaviour (claim, recall, verify, retry, recover, no false completion)
and the cost effect of bounded recall. It proves nothing about AGI or RSI, and does not
satisfy Destiny 10 (needs >=3 seeds per arm with a seed band).

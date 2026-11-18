# Destiny task reconciler benchmark, 3 seeds, 2026-11-18

Run: `python evals/destiny_bench.py --n 100 --arms prompt_only,shards_first --seed <S>` against main
(token gate narrowed in #1096). Seeds 1085, 1086, 1087. Local lanes only (`gemma4:e2b-qat` primary,
`gemma2:2b` alternate), $0. Finished 11:45 AM, 11:55 AM, 12:05 PM EST Wed 11/18.
`no_memory` arm omitted: it was 0/100 on 11/17 and needs no repeat.

| Seed | Arm | Done | Tokens | Tokens/success | Recovery | Rollback violations |
|---|---|---|---|---|---|---|
| 1085 | prompt_only | 100/100 | 172,875 | 1,729 | 100% | 0 |
| 1085 | shards_first | 100/100 | 33,725 | 337 | 100% | 0 |
| 1086 | prompt_only | 100/100 | 173,158 | 1,732 | 100% | 0 |
| 1086 | shards_first | 100/100 | 34,296 | 343 | 100% | 0 |
| 1087 | prompt_only | 100/100 | 173,245 | 1,732 | 100% | 0 |
| 1087 | shards_first | 100/100 | 33,917 | 339 | 100% | 0 |

Readings:
- The 11/17 result of 96/100 was the safety gate's `\btoken\b` false positive; with the narrowed
  pattern both arms complete every task on all three seeds.
- shards_first uses about 5.1x fewer tokens than prompt_only (339 vs 1,731 tokens/success on average)
  at equal success, stable across seeds (spread under 2%).
- No task was lost or double-completed, and no evidence shard or relay leg was written for an
  unverified task.

Claim limits: one reconciler loop on small local models, one fact-recall task family, 3 seeds.
This shows nothing about general capability. Raw data: `destiny_bench_20261118_seed*.json`/`.log`.

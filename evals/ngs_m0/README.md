# NGS M0: eval harness and baselines on the current stack

Spec: `docs/memory-engine/SPEC.md` section 9 (benchmarks) and milestone M0 (PR #1199).
This is the baseline every engine branch is compared with. It runs the CURRENT Python/SQLite
recall (`core.retrieve`); it contains no engine code and no C.

## Run

The label files (`labeled_v*.json`, `paraphrases_v*.json`) are derived from private shards and are
**not committed** (public repo, `.gitignore`d). Generate them locally from a vault snapshot; the committed
baseline JSON carries their sha256 (`labels_sha256`) so a run can be tied to an exact set. `paraphrases_v1.json`
is the hand-written paraphrase list used by `build_labeled_v2.py`; it is also kept local.

```bash
python evals/ngs_m0/build_labeled_set.py          # reads ~/.nougen/replica/shards, writes labeled_v1.json
python evals/ngs_m0/run_baseline.py --out evals/ngs_m0/baseline_fast_local_<date>.json
python evals/ngs_m0/run_baseline.py --mode hybrid # full stack; loads embedding caches, run when swap is quiet
```

Both read a read-only SNAPSHOT (the Docker replica), never the live vault, so a run cannot
touch the running node. Labels record the snapshot stamp and a sha256 of the item list.

## Baseline (fast_local, 2026-11-23, code b6d265af, snapshot 2026-11-18T16:31:16Z)

| metric | value |
|---|---|
| answerable / no-answer queries | 59 / 10 |
| Recall@1 / @5 / @10 | 0.119 / 1.000 / 1.000 |
| MRR | 0.554 |
| nDCG@10 | 0.670 |
| latency p50 / p95 / p99 | 0.45 s / 0.97 s / 1.06 s |
| no-answer false-answer rate | 1.00 (no abstain path exists) |

Raw: `baseline_fast_local_20261123.json`. Mode `fast_local` is keyword/FTS only (`core.FAST_LOCAL`),
so it is the keyword lane, not the hybrid stack the spec's targets compare against.

## v2: hand-written paraphrases (same gold, less lexical overlap)

`paraphrases_v1.json` holds one hand-written question per gold shard; `build_labeled_v2.py` merges
them into `labeled_v2.json`. Same snapshot, same gold, same no-answer items, so v1 vs v2 isolates
lexical overlap. fast_local on v2 (2026-11-23, code b6d265af): Recall@1 0.000, @5 0.169, @10 0.254,
MRR 0.072, nDCG@10 0.115, latency p50 0.57 s / p95 1.20 s / p99 1.25 s
(`baseline_fast_local_v2_20261123.json`). The keyword lane collapses from 1.00 to 0.17 at @5, so v2
leaves room to show a gain. The hybrid stack was not run, so do not read 0.17 as the current stack's
recall. Caveat: the writer had read the gold shards (topical overlap and author knowledge remain); a
second writer who has not seen them is still needed for a clean 200 to 400 pair set.

## What the v1 set can and cannot show

- Labels are derived only from what needs no human or model: `Autonomous Verified Relay: <leg id>`
  shards, query = the shard's own goal sentence with leg ids removed, gold = that shard. The query
  is a trimmed copy of the gold body, so the set is **lexically easy**: Recall@5 is already 1.0 and
  cannot show a +10 pp gain. Recall@1, MRR and nDCG@10 still move, so it works as a regression guard.
- 59 answerable pairs, not the 200 to 400 the spec asks for; the vaults hold only about 55 such
  shards. The spec's set needs independently written queries (human or a separate model). Open.
- No confidence intervals: n is too small. Add cluster bootstrap once the larger set exists.
- Latency is from a shared 16 GB mini with heavy swap and is not the engine-only number.
- The current stack has no abstain path, so the no-answer rate is a baseline, not a pass or fail.
- Not measured here: hybrid (vector + RRF) numbers, throughput, crash, on-disk size, federation.

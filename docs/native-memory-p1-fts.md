# Native Memory Engine — P1: FTS5 benchmark and index tuning

Directive shard 31235@db6, P1 phase. The gap report (§3 P1) found FTS5 had
tuning knobs but no benchmark: no per-lane timings, no index-size tracking,
no trigram-vs-plain comparison, no `EXPLAIN QUERY PLAN` baseline, and the
only recorded FTS/vector split was a two-months-stale comment
(`core.py:1874`, 2026-09-21). This phase builds the benchmark, fixes one
seed corpus, and tunes only by measured delta.

Rule of this phase: **if a change does not improve measured latency and/or
Recall@k on the fixed corpus, it does not ship.** Every experiment below
is recorded, including the ones that did not help.

## 1. Fixed seed corpus — `tools/fts_seed_corpus.json`

One corpus for every before/after comparison, so deltas are real. The audit
and P0 both re-derived corpora per run (P0's capture-latency numbers did not
reproduce the audit's exactly because its bodies were ~1200 chars of filler
— embed time dominates). That failure mode is closed here: the corpus is a
checked-in JSON file, verified by sha256 on load (the bench refuses to run
on a drifted corpus).

| Field | Value |
|---|---|
| Name | `p1-fts-seed-corpus-v1` |
| Seed | `20261116` (`random.Random(20261116)`) |
| Shards | 60 — 6 topics x 10 (relay, tenant, snapshot, embed, journal, gateway) |
| Body chars | 448–518 (mean ~480); titles 20–30 chars, unique |
| Queries | 28 — 12 title (exact title), 12 body (5 content words, title excluded), 4 negative |
| sha256 (shards payload) | `628602e072c11a29…` (full hash in the JSON `meta`) |

Content shape per shard: topic intro + 3 pool sentences + one unique
detail sentence (`Shard <topic>-<j> records the <detail> …`, detail phrase
unique per shard, assigned by maximum bipartite matching so it shares no
word with its own title) + closer. Body queries are the 2 detail words +
`handling checks log` — 5 discriminative words. The generator that produced
the JSON is deterministic (re-running it reproduces the file byte-for-byte)
but is deliberately NOT shipped: the JSON is the artifact of record.

Caveat (read before quoting the tokenizer result): the query set is
whole-word only. It does not measure what the trigram tokenizer is for —
substring / partial-word matching and typo tolerance (Module 1: Metamers).
See §5 for why the default was NOT flipped on this evidence alone.

## 2. The benchmark — `tools/fts_bench.py`

```bash
# Full run: build one scratch vault per tokenizer, time the lanes, audit plans
python3 tools/fts_bench.py --tokenizers trigram,unicode61 --repeats 3 \
    --out report.json [--embed]

# Weight experiment on an existing vault (weights are query-time: no rebuild)
python3 tools/fts_bench.py --query-only <vault-dir> --weights 1.0,1.0 --repeats 3

# Single-purpose runs
python3 tools/fts_bench.py --explain-only <vault-dir>
python3 tools/fts_bench.py --sizes-only <vault-dir>
```

What it measures, per variant:

- **Per-lane timings** (warmup pass, then `--repeats` timed passes):
  `fts_direct` (raw FTS MATCH SQL per DB, AND then OR fallback),
  `keyword` (`core._keyword_retrieve`), `vector`
  (`core._vector_retrieve`, `--embed` only), `hybrid`
  (`core.retrieve`, `--embed` only). Each lane reports p50/p95/mean ms.
- **Quality** per lane and tier (title / body / all): Recall@1/3/5/10,
  MRR, nDCG@10. Negatives are reported (non-empty count), not asserted.
- **Index sizes**: per-DB file bytes, per-table bytes via the `dbstat`
  virtual table (FTS shadow tables only — the `shards` table is tracked
  separately; an earlier cut of this tool mixed them and overstated FTS
  size by exactly the embedding bytes), total bytes, bytes/shard.
- **EXPLAIN QUERY PLAN audit**: the live AND/OR MATCH queries, the LIKE
  fallback, the domain+utility query, the title-nocase lookup, and the
  `file_hash` lookup, with indexes used vs unused.
- **Assertions (CI-gatable)**: exit 1 when the corpus is empty, when any
  measured lane ran zero queries, or when `--min-recall10` is missed.
  No workflow file is added: GitHub Actions minutes for the org are
  exhausted (reset Dec 1) and the Muse GitHub App cannot merge workflow
  files (no `workflows` permission). The documented command above plus
  `tests/test_fts_bench.py` (which runs the CLI end to end) is the gate
  until those two walls move.

Env knobs (Rule 0.2): `NOUGEN_FTS_BENCH_REPEATS`,
`NOUGEN_FTS_TOKENIZER`, `NOUGEN_FTS_BM25_TITLE_WEIGHT`,
`NOUGEN_FTS_BM25_BODY_WEIGHT`. Workers run as subprocesses with the
sandbox proxy variables stripped (bracketed IPv6 `no_proxy` breaks httpx
at gradio import) and a fresh process per variant, so no in-process cache
or pool state leaks between tokenizers.

## 3. Measured results (this Linux VM, 4 CPU, 7.7 GB RAM, no GPU)

Full JSON reports: `~/workspace/nougen-native-memory/baselines/`
(`p1_fts_baseline.json`, `p1_fts_embed.json`). All runs use the fixed
corpus above (60 shards, 24 scored queries x 3 repeats).

### 3.1 Tokenizer comparison — trigram (default) vs unicode61 (plain)

No-embed vaults, weights 5.0/1.0 (the live defaults):

| Metric | trigram | unicode61 | Delta |
|---|---|---|---|
| Vault total | 831,488 B (13,858 B/shard) | 626,688 B (10,445 B/shard) | **−204,800 B (−24.6%)** |
| FTS shadow tables | 393,216 B | 188,416 B | **−204,800 B (−52.1%)** |
| `fts_direct` p50 / p95 | 8.3 / 21.2 ms | 4.8 / 8.9 ms | −3.5 / −12.3 ms |
| `keyword` p50 / p95 | 23.9 / 54.3 ms | 19.1 / 37.0 ms | −4.8 / −17.3 ms |
| Recall@10 (all / title / body) | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 | 0 |
| Recall@1 (all / title / body) | 0.542 / 0.667 / 0.417 | 0.667 / 0.917 / 0.417 | +0.125 / **+0.250** / 0 |
| MRR (all / title / body) | 0.705 / 0.785 / 0.625 | 0.814 / 0.944 / 0.683 | +0.109 / +0.160 / +0.058 |
| Negatives non-empty (`keyword`) | 1/4 (fuzzy lane) | 1/4 (fuzzy lane) | 0 |

The plain tokenizer is smaller, faster, and ranks better on every
whole-word tier. Run-to-run variance on this shared box: a repeat run gave
`fts_direct` trigram p50 9.3 ms and `keyword` 30.3 ms (vs 8.3 / 23.9 ms
above); quality metrics were bit-identical across runs.

### 3.2 Per-lane timings with embeddings (trigram vault, `--embed`)

Fresh re-measurement of the stale 2026-09-21 comment in `core.py:1874`
(keyword-only 0.83 s p50 vs hybrid 2.0 s p50 at production scale). On the
60-shard fixed corpus, local Ollama (`nomic-embed-text`):

| Lane | p50 | p95 | Mean | Recall@10 | MRR | Title R@1 | Body R@1 |
|---|---|---|---|---|---|---|---|
| `fts_direct` | 10.0 ms | 76.1 ms | 31.3 ms | 1.000 | 0.705 | 0.667 | 0.417 |
| `keyword` | 91.8 ms | 175.8 ms | 90.1 ms | 1.000 | 0.705 | 0.667 | 0.417 |
| `vector` | 17.2 ms | 80.3 ms | 38.6 ms | 1.000 | 0.802 | 0.917 | 0.417 |
| `hybrid` (`retrieve`) | 273.3 ms | 368.2 ms | 263.8 ms | 1.000 | 0.775 | **1.000** | 0.500 |

Query-embedding cost (Ollama, warm): p50 87.8 ms — it dominates the
vector lane's own 17.2 ms. Hybrid is the best lane on the title tier
(R@1 1.000) and the only lane above 0.5 on body R@1.

Two findings, both measured, neither changed in this phase:

1. **The keyword lane costs ~4x more once embeddings exist** (p50
   23.9 ms no-embed → 91.8 ms with embeddings, same corpus and queries).
   Cause: the FTS SQL selects `s.embedding` for every candidate row, so
   each hit pulls a ~3 KB BLOB even when no query embedding was supplied
   (the bench calls `_keyword_retrieve` with `query_embedding=None`).
   Follow-up for P2: fetch the embedding column only when a query
   embedding is present (or defer it to the rows that survive ranking).
2. **The keyword lane's ranking is identical to raw FTS** on this corpus
   (same Recall@k / MRR to 4 decimals in every run). The ~15–20 ms gap
   between `fts_direct` and `keyword` p50 is fan-out + row processing +
   per-DB history logging, not the index.

Comparison with P0's locked baseline (idle box, 36 shards):
hybrid p50 386.2 / p95 468.8 ms, keyword-only 47.1 / 86.7 ms. The P1
hybrid numbers (273.3 / 368.2 ms on 60 shards) are in the same band —
no regression, and no claim of an improvement either: different corpus,
different shard count.

### 3.3 BM25 weight experiments — no change shipped

Weights are query-time, so each variant ran on the same vaults
(`--query-only`, 3 repeats). Recall@10 stayed 1.000 in every cell; only
the ordering inside the top 10 moved.

| Weights (title/body) | trigram MRR | trigram title R@1 / body R@1 | unicode61 MRR | unicode61 title R@1 / body R@1 |
|---|---|---|---|---|
| **5.0 / 1.0 (default)** | **0.705** | 0.667 / 0.417 | **0.814** | 0.917 / 0.417 |
| 1.0 / 1.0 | 0.745 | 0.500 / 0.750 | 0.856 | 0.667 / 0.833 |
| 10.0 / 1.0 | 0.709 | 0.667 / 0.417 | 0.814 | 0.917 / 0.417 |
| 5.0 / 2.0 | 0.695 | 0.500 / 0.583 | 0.804 | 0.667 / 0.667 |

No variant beats the default on both tiers. 1.0/1.0 buys body R@1
(+0.33 trigram, +0.42 unicode61) by paying title R@1 (−0.17 / −0.25) —
the known-item tier, the one recall is most often asked to serve — so
its higher all-tier MRR is not a win. 10.0/1.0 is a wash; 5.0/2.0 is
slightly worse overall. **Decision: weights stay 5.0/1.0.** The env knobs
(`NOUGEN_FTS_BM25_TITLE_WEIGHT`, `NOUGEN_FTS_BM25_BODY_WEIGHT`) ship so
future experiments need no code edits.

Note the scale: with the trigram tokenizer, raw bm25 magnitudes are
~1e-6 (the gap report's "trigram-FTS bm25 magnitudes are tiny"), so
weight changes move scores by micro-amounts and reorder only near-ties.
With unicode61 the magnitudes are whole-word BM25 and the weights bite
normally.

## 4. EXPLAIN QUERY PLAN audit (baseline)

Representative DB: `nougen_shards_3.db` (10 rows, the fullest). Plans are
identical for both tokenizers.

| Query | Plan |
|---|---|
| FTS AND MATCH | `SCAN shards_fts VIRTUAL TABLE INDEX 0:M2`; `SEARCH s USING INTEGER PRIMARY KEY (rowid=?)`; `USE TEMP B-TREE FOR ORDER BY` |
| FTS OR MATCH | same as AND |
| LIKE fallback | `SEARCH shards USING INDEX idx_shards_domain_utility (domain_key=?)` |
| domain + utility | `SEARCH shards USING COVERING INDEX idx_shards_domain_utility (domain_key=?)` |
| title nocase | `SEARCH shards USING COVERING INDEX shards_title_nocase (title=?)` |
| `file_hash` lookup | `SEARCH shards USING COVERING INDEX sqlite_autoindex_shards_1 (file_hash=?)` |

Indexes used by the audited queries: `idx_shards_domain_utility`,
`shards_title_nocase`, `sqlite_autoindex_shards_1` (UNIQUE `file_hash`),
plus the FTS virtual-table index. **Unused by the audited queries:
`idx_semantic_domain_subject`** (on `semantic_knowledge`). That is a
narrow claim — the audit's six queries never touch `semantic_knowledge`,
so the index may still serve its own module's queries. Do not drop it on
this evidence; the follow-up is to audit the `semantic_knowledge` query
shapes before calling it dead. No index is added or removed in this phase:
every b-tree index in the schema is used by at least one audited query,
and the FTS plans show the virtual-table index doing the work (the
`USE TEMP B-TREE FOR ORDER BY` is inherent to bm25 ranking, not a
missing index).

## 5. Tuning decisions (measured delta only)

| Change | Measured delta | Decision |
|---|---|---|
| BM25 weights 5.0/1.0 → 1.0/1.0, 10.0/1.0, 5.0/2.0 | No variant wins both tiers (§3.3) | **Keep 5.0/1.0.** Knobs ship behind env flags. |
| Tokenizer trigram → unicode61 | −52% FTS bytes, −24.6% vault, faster, better whole-word ranking (§3.1) | **Keep trigram default.** See below. |
| Add/remove an index | All audited indexes used except `idx_semantic_domain_subject`, which the audit does not cover | **No change.** |
| Scoped update trigger | Already scoped (gap report §1.1); not re-measured as a change | **No change.** |

**Why the tokenizer default does not flip despite unicode61 winning every
measured cell:** the corpus (§1) has no substring or typo queries, and
substring/fuzzy matching is the reason the trigram tokenizer exists
(Module 1: Metamers — the FTS index must answer partial-word and
misspelled queries, which unicode61 cannot). Flipping the default on a
corpus that cannot see trigram's purpose would trade an unmeasured
capability for a measured-but-narrow win. The honest next step is a
substring/typo query tier in the corpus (partial titles, one-typo
queries, prefix searches); if unicode61 still wins there — it cannot win
the substring cells by construction — the trade-off becomes explicit and
the GM can decide with both sides measured. The
`NOUGEN_FTS_TOKENIZER` flag ships so that experiment needs no code edits,
and `init_db` now logs a warning (never silently rebuilds) when the env
disagrees with an existing vault's tokenizer.

## 6. What shipped in this phase

- `tools/fts_bench.py` — the missing FTS benchmark (per-lane timings,
  index sizes, tokenizer comparison, EXPLAIN audit, n>0 / `--min-recall10`
  gate). `tools/fts_seed_corpus.json` — the fixed corpus.
- `tests/test_fts_bench.py` — 9 tests: knob validation, plain-vault
  build, weight effect on bm25 scores, metric math, corpus invariants,
  size tracking, CLI end to end (`--query-only`, `--explain-only`).
- `src/nougen_shards/core.py` — two flagged knobs, defaults unchanged:
  `NOUGEN_FTS_TOKENIZER` (`trigram` | `unicode61`, default `trigram`;
  vault-creation-time choice, mismatch logged) and
  `NOUGEN_FTS_BM25_TITLE_WEIGHT` / `NOUGEN_FTS_BM25_BODY_WEIGHT`
  (defaults 5.0 / 1.0), wired into both `bm25()` call sites in
  `_keyword_retrieve`. No API or tenant-boundary change.

## 7. Linux notes (this lane runs on Linux; Phoebus/Blade own their OS)

- WAL needs POSIX shm/locking on the vault directory: scratch vaults in
  this bench live on a local filesystem (`/tmp` on this VM). Never point
  a real vault at `tmpfs` (not durable across reboot) or at a network
  mount without coherent locking (see P0's durability doc).
- Sandbox quirk (P0's finding, re-confirmed here): the sandbox
  `no_proxy`/`NO_PROXY` contains bracketed IPv6 entries, which makes
  `httpx` raise `InvalidURL` at gradio import and fails test collection.
  Strip the proxy variables before running the suite or the bench
  (the bench strips them for its worker subprocesses itself).
- `dbstat` (used for per-table index sizes) is available in this box's
  SQLite 3.45.1; the tool falls back to file bytes + row counts when it
  is not compiled in, and reports which path it took.
- Vault directories are created `mode=0o700` by the existing vault path;
  scratch vaults in `/tmp` inherit that. No Linux permission change was
  needed for this phase.
- `ruff` is not installed on this box; it was installed `--user` from
  PyPI for this phase (`ruff check` clean on all touched files). The repo
  config is check-only (E4/E7/E9/F); `ruff format` is not enforced
  (untouched files fail it too) and was not applied.

## 8. Follow-ups (not this phase)

1. Substring/typo query tier in the seed corpus, then re-run the
   tokenizer comparison — the decision the default-flip question needs.
2. Keyword-lane embedding-BLOB fetch: `s.embedding` is selected for every
   FTS candidate row even with no query embedding (§3.2, finding 1).
3. Audit the `semantic_knowledge` query shapes before judging
   `idx_semantic_domain_subject` (§4).
4. `lane_health` + eval wiring into CI/schedule remain P0/P6 work; the
   bench's documented command is the P1 gate until the Actions-minutes
   and `workflows`-permission walls move.

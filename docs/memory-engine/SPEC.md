# nmem: a memory-native storage engine (spec, draft 0.1)

Status: draft for review. Owner: WhoArt claude-app. Reviewer: Phoebus, once its benchmarks land.
Date: Sun 2026-11-22. Inputs: gap report 26917@db1, research frontier 32623@db5, Destiny 10 audit 35723@db7.

nmem is a single-file embedded engine in the spirit of SQLite, built around memory instead of
tables. Its primitive is a **fact**: a signed, hash-chained, append-only record that is never
deleted, only invalidated. There is no SQL. The API is `remember`, `recall`, `invalidate`,
`as_of` and `link`.

It ships as one amalgamated C file (`nmem.c`) and one public header (`nmem.h`), with thin
bindings for Python, Bun and Go. It needs no server, no network and no paid service.

---

## 1. Why build it (and why not just keep SQLite)

The gap report (26917@db1) found that the current stack (SQLite WAL + FTS5 + RRF + an
out-of-process embedder) already does hybrid recall. Four things it cannot do cleanly are the
reason for a new engine:

1. **History is not first-class.** Rows are updated in place. "What did we believe on Nov 12"
   is not answerable, and an overwrite destroys evidence.
2. **No integrity story.** Nothing is signed or chained. A copied `.db` file cannot prove it was
   not edited, and replicas cannot prove they agree.
3. **Replication is ad hoc.** Writes route by content hash. There is no journal, no single
   writer per namespace, and no quarantine for bad input.
4. **Recall is assembled, not designed.** Keyword, vector and time live in separate structures,
   fused at query time in Python, with an embedder over HTTP. The measured tail was 29.9 s.

Non-goals: SQL, joins, ad-hoc analytics, a server mode in v1, CRDT merges (32623@db5 move 5),
DiskANN/IVF at vault scale, LLM-driven "memory extraction" at write time (raw verbatim wins).

## 2. Data model

### 2.1 Fact

Every write produces exactly one immutable fact record.

| field | type | notes |
|---|---|---|
| `fact_id` | 32 bytes | BLAKE3 of the canonical encoding of every field below except `sig` |
| `ns` | string ≤ 255 | namespace (tenant/domain). Single authoritative writer per `ns` |
| `kind` | u8 | `EPISODIC`=1, `SEMANTIC`=2, `PROCEDURAL`=3 (§2.3) |
| `writer` | 32 bytes | Ed25519 public key of the writing node. No names, no hostnames |
| `seq` | u64 | gapless per (`writer`, `ns`) |
| `prev` | 32 bytes | `fact_id` of the previous fact by this writer in this `ns` (zero for the first) |
| `t_event` | i64 µs | when the described thing happened (caller-supplied, may be past) |
| `t_record` | i64 µs | when the engine accepted it (engine clock, monotonic per writer) |
| `valid_from` | i64 µs | defaults to `t_event` |
| `title` | utf-8 ≤ 1 KiB | |
| `body` | utf-8 ≤ 1 MiB (configurable) | verbatim, never rewritten |
| `tags` | utf-8 list | |
| `attrs` | CBOR map ≤ 64 KiB | free-form, schema-versioned (§2.5) |
| `schema` | u16 | attrs schema version |
| `sig` | 64 bytes | Ed25519 over `fact_id` |

`fact_id` is content-derived, so two writers storing identical content in the same `ns` with the
same `t_event` produce different ids (writer and seq differ). Dedup is an index, not an identity rule.

### 2.2 Invalidation (bitemporal)

Facts are never deleted or edited. A later fact can end an earlier one's validity:

```
invalidate(old_id, reason)            -> appends an INVALIDATION fact: {target=old_id, valid_to=now}
remember(new, supersedes=old_id)      -> appends new fact AND an INVALIDATION {target=old_id, superseded_by=new_id}
```

The derived view gives every fact a `valid_to` and an optional `superseded_by`. Two time axes are
always available:

- **valid time** (`valid_from`/`valid_to`): what was true in the world.
- **record time** (`t_record`): what the engine knew, and when.

`as_of(t_valid, t_record)` answers "what did we believe at record time X about time Y". The
default recall is `as_of(now, now)`, so invalidated facts drop out but remain readable.

Redaction (legal/privacy) is the single exception to "never removed": `nmem_redact` overwrites a
body with a tombstone and records a REDACTION fact. The chain survives because `fact_id` covers
a BLAKE3 of the body, not the body bytes, so verification still passes with the body gone.

### 2.3 Memory types

Kinds share one log but are separate logical stores with separate default ranking:

- **EPISODIC**: what happened (events, sessions, receipts). Ranked with strong recency.
- **SEMANTIC**: what is true (facts, decisions, canon). Ranked with weak recency, strong salience.
- **PROCEDURAL**: how to do things (recipes, runbooks, skills). Ranked by match and success count.

A recall names the kinds it wants. Default: all three, results labelled by kind.

### 2.4 Links

`link(a, b, rel, weight)` appends a LINK fact. Relations are free strings (`supports`,
`contradicts`, `derived_from`, `about`). Links are facts, so they are signed, chained and
invalidatable. Recall can expand one hop over links (`NMEM_RECALL_EXPAND`).

### 2.5 Schema migration

`attrs` carry a `schema` number. Migrations are registered functions `vN -> vN+1` applied **at
read time** in the decoded view. The log is never rewritten. A compaction may materialize the
newest schema into a derived index, but the log keeps the original bytes.

## 3. On-disk format

One directory per database:

```
mem.nmem/
  HEAD                 current manifest pointer (atomic rename)
  MANIFEST-000123      list of live segments, SSTables, index files, checkpoint
  log/000001.seg       append-only fact log segments (64 MiB default)
  log/000002.seg
  sst/L0-000045.sst    LSM levels (derived, rebuildable from log)
  idx/vec-<model>-<dim>-<ver>.hnsw
  idx/bm25.inv
  idx/time.btree
  ckpt/000123.ckpt     signed checkpoints
  LOCK                 single-process writer lock (advisory + pid)
```

Everything except `log/` and `ckpt/` is **derived** and can be rebuilt from the log
(`nmem_rebuild`). The log is the only source of truth.

### 3.1 Log segment

```
segment header (64 B):  magic "NMEMSEG\0" | u16 format=1 | u16 flags | u64 first_seq
                        | 32 B writer pubkey | u32 header_crc32c
record:                 u32 len | u8 type | payload[len] | u32 crc32c(type||payload)
```

Record types: `FACT`=1, `INVALIDATION`=2, `LINK`=3, `REDACTION`=4, `CHECKPOINT_REF`=5, `PAD`=0.

Payloads use a canonical CBOR encoding (deterministic map order, shortest ints), so `fact_id` is
reproducible on every platform. Writes are `write` + `fdatasync` at commit boundaries.
A torn tail (bad CRC or short record) is truncated on open, never interpreted.

### 3.2 Commit protocol

1. Append records to the active segment buffer.
2. `fdatasync(segment)`.
3. Update the in-memory memtable and indexes.
4. Every N facts or T ms, write a new MANIFEST, `fsync` it and the directory, then rename `HEAD`.

Crash recovery = read HEAD → MANIFEST → replay log from the manifest's `log_seq` to the last
valid record. Derived files newer than the manifest are discarded and rebuilt.

### 3.3 Checkpoints

A checkpoint is a signed statement:
`{ns_heads: {(writer, ns) -> (seq, fact_id)}, merkle_root, t_record, engine_version}` + Ed25519 sig.
The Merkle root covers every fact_id in log order. Checkpoints are written every 10 000 facts or
1 hour, and exported as a small file for **off-node anchoring**. Any store the operator already
has works (a git commit in a private repo, another node, an object bucket). No paid anchoring
service is required or assumed.

## 4. Storage engine: LSM over the log

- **Memtable**: lock-free skiplist keyed by `(ns, kind, fact_id)` plus a secondary time key.
- **Flush**: memtable → L0 SSTable (sorted, block-compressed with zstd, block index, Bloom
  filter on `fact_id`).
- **Compaction**: leveled (L0 → L1 … L6, size ratio 10). Compaction only merges *derived*
  views; it never drops log records. Invalidated facts stay in SSTables, flagged.
- **Concurrency**: many threads and many in-process agents write concurrently through a group
  commit queue (one fsync per batch). Cross-process: one writer process per database (LOCK),
  many reader processes via mmap of immutable files. Multi-node writes go through federation (§7).
- **Single writer per namespace**: a node may append to `ns` only if it holds that namespace's
  write grant (a signed fact by the namespace owner key). Other nodes' facts for `ns` arrive by
  sync and are verified, never authored locally.

## 5. Indexes and recall

### 5.1 Indexes

| index | structure | key |
|---|---|---|
| vector | HNSW (M=16, efC=200, efS adaptive), one file per `(model, dim, version)` | embedding |
| keyword | BM25 inverted index, unicode61 + Porter stemming, plus a trigram side index for substrings | tokens |
| time | B+tree on `t_event` and `t_record` | µs |
| id | SST Bloom + block index | `fact_id` |
| links | adjacency lists | `(fact_id, rel)` |

**Embedding hygiene**: every vector is tagged `(model_id, dim, version)`. An index holds exactly
one tag. A query declares its tag; mismatches are an error, never silently mixed. Re-embedding
writes a new index alongside the old one and switches atomically when complete; NULL coverage is
reported per tag (`nmem_stats`). The engine stores and searches vectors; it does not run models.
Embedding is the caller's job (bindings ship an optional in-process ONNX helper, outside the core).

### 5.2 Fused recall score

For a query `q` over candidates gathered from each arm (top-k per arm, run in parallel under a
deadline):

```
score(f) = w_v·z(cos(q,f)) + w_k·z(bm25(q,f)) + w_t·recency(f) + w_s·salience(f) + w_l·link_boost(f)
```

- `z()` is a per-query z-score over that arm's candidates (32623@db5 move 4: weighted z-score
  fusion beats plain RRF). RRF remains a selectable mode for comparison.
- `recency(f) = exp(-Δt / τ_kind)`, with τ per kind (episodic short, semantic long).
- Missing arms (no embedding, deadline hit) contribute 0 and are reported in the result
  (`arms_complete`). There is never a silent partial result.
- Defaults are weights tuned once on the eval set (§9) and then frozen per release.

### 5.3 Salience

Each fact has a salience `s ∈ [0,1]` kept in a derived side table (not the log):

```
on access (returned AND marked used): s ← s + η·(1 − s)        η = 0.15
decay:                                 s ← s · 2^(−Δt / half_life)  half_life = 30 days (per kind)
```

Decay is computed lazily at read time from `(s, last_touch)`, so idle facts cost nothing.
Access events are batched and written as derived-state, not facts, so reading never grows the log.
`nmem_mark(fact_id, USED|NOT_USED)` lets agents report which recalled facts actually helped.

## 6. Public API (C)

See `nmem.h`. Summary:

```c
nmem_open / nmem_close
nmem_remember(db, &fact_in, &fact_id_out)
nmem_invalidate(db, fact_id, reason)
nmem_link(db, a, b, rel, weight)
nmem_recall(db, &query, &results)        // fused, deadline-bound, kind-filtered
nmem_as_of(db, t_valid, t_record, &query, &results)
nmem_get(db, fact_id, &fact)
nmem_mark(db, fact_id, used)
nmem_checkpoint / nmem_verify / nmem_rebuild / nmem_redact
nmem_sync_export(db, since, &segment) / nmem_sync_import(db, segment, &report)
nmem_stats
```

Errors are integer codes plus `nmem_errmsg(db)`. No function allocates memory the caller must
free with anything other than `nmem_free`. All strings are UTF-8, length-delimited.

## 7. Federation

Nodes exchange **signed log segments**, not rows and not embeddings.

1. Each node advertises its latest checkpoint (`ns_heads`).
2. A peer requests the facts it lacks per `(writer, ns)` from `seq` onward.
3. Import verifies, in order: signature, `prev` chain, gapless `seq`, namespace write grant.
4. Any failure **quarantines** the segment (kept, flagged, never applied) and reports why.
5. Applied facts are replayed in `(writer, ns, seq)` order, so every node converges to the
   same log content. Derived indexes are rebuilt locally; embeddings are recomputed locally or
   shipped as a separate, optional, tagged artifact.

Transport is out of scope for the core: the API produces and consumes segment byte buffers.
The bindings add a file drop and an HTTP push/pull. Conflicts cannot occur because each `ns`
has one writer. Divergent *beliefs* are expressed as facts with `contradicts` links, not merges.

## 8. Testing: crash and torture from day one

Modeled on SQLite's test discipline. The harness lands **before** the indexes:

- **Crash injection**: a VFS shim that can fail or kill at every `write`, `fsync`, `rename`,
  `ftruncate`. For every injection point: reopen, `nmem_verify`, assert no acknowledged fact is
  lost and no unacknowledged fact is half-visible.
- **Power-loss simulation**: drop un-fsynced pages at random (with reordering) and replay.
- **Torn-write and bit-flip**: corrupt random bytes in segments; the engine must detect (CRC,
  hash chain, signature) and refuse, never return wrong data.
- **Concurrency**: N writer threads × M reader threads × compactions; linearizability check on
  remember/recall.
- **Federation fuzz**: reordered, duplicated, truncated and forged segments; expect quarantine.
- **Differential test**: every recall result on a fixed corpus compared against a slow
  brute-force reference implementation.
- **Coverage gate**: 100% branch coverage of the log and commit path; ≥ 90% overall.
- **Platforms**: Windows, macOS (arm64), Linux (x86_64, arm64). CI runs the crash suite nightly.

## 9. Benchmarks it must beat

Baselines are the current stack on the same machine and corpus (measured first, per 26917@db1):
SQLite 3.51.3+ WAL + FTS5 + current Python fusion; and sqlite-vec flat scan for vectors.

Corpus: a fleet export of ≥ 250 000 facts plus a labeled set of 200–400 query/gold pairs built
from relay legs (32623@db5 move 1). Report with cluster bootstrap CIs.

| metric | target (v1.0) | why |
|---|---|---|
| Recall@5 | ≥ current + 10 pp, CI excludes 0 | the point of the engine |
| nDCG@10, MRR | not worse than current | no regression in ranking |
| recall p50 / p95 / p99 (warm, 250k facts) | ≤ 15 ms / 40 ms / 80 ms | current tail is 29.9 s |
| recall p99 with embedder hop excluded | ≤ 25 ms | engine cost only |
| remember throughput, 8 writers, group commit | ≥ 20 000 facts/s | many concurrent agents |
| remember latency p99 (fsync on) | ≤ 5 ms on NVMe | |
| as_of query p95 | ≤ 2× plain recall | history must be cheap |
| open + recover after kill -9 at 250k facts | ≤ 2 s | |
| full rebuild of derived indexes, 250k facts | ≤ 120 s | |
| on-disk size vs current DB | ≤ 1.2× (log + indexes) | |
| crash suite | 0 lost acknowledged facts, 0 wrong reads | correctness gate |
| federation | 2 nodes converge to identical Merkle root after any fuzzed sequence | |

Phoebus's benchmark lane owns the harness and the baseline numbers; nmem milestones are gated on it.

## 10. Milestones

| M | scope | done when |
|---|---|---|
| M0 | Eval harness + baselines on the current stack | labeled set, numbers committed, reproducible |
| M1 | Log + canonical CBOR + BLAKE3 + Ed25519 + crash VFS | crash suite green, verify detects every corruption class |
| M2 | Memtable + SST + manifest + recovery | recover ≤ 2 s; rebuild from log matches byte-for-byte |
| M3 | Time and id indexes; `as_of`; invalidation view | bitemporal tests green |
| M4 | BM25 + HNSW + fused recall + salience | beats Recall@5 baseline with CI |
| M5 | Federation export/import + quarantine + checkpoints | fuzzed 2-node convergence |
| M6 | Amalgamation + bindings (Python, Bun, Go) + docs | one-file build on all 3 OSes |
| M7 | Migration tool from current shard DBs (read-only import, dual-run) | parity report, no data loss |

## 11. File layout (source)

```
nmem/
  include/nmem.h            public API (stable)
  src/                      developed as separate files, amalgamated for release
    log.c  cbor.c  hash.c  sign.c  vfs.c  memtable.c  sst.c  manifest.c
    hnsw.c  bm25.c  timeidx.c  recall.c  salience.c  sync.c  checkpoint.c  migrate.c
  third_party/              vendored, permissive: BLAKE3 (CC0/Apache), Ed25519 ref10 (public domain), zstd (BSD)
  tool/amalgamate.py        -> dist/nmem.c + dist/nmem.h
  test/crash/  test/torture/  test/diff/  test/fed/
  bindings/python/  bindings/bun/  bindings/go/
  bench/                    harness entry points (owned with the benchmark lane)
```

Licence: Apache-2.0 for nmem itself. No identities, hostnames or account names in source or tests;
keys are generated at `nmem_open` with `NMEM_OPEN_CREATE` or supplied by the caller.

## 12. Open questions for review

1. HNSW vs a flat scan: at ≤ 1M facts a SIMD flat scan may meet the latency targets with zero
   build cost (32623@db5 says flat is enough at vault scale). Proposal: ship flat first in M4,
   add HNSW behind the same interface only if p95 misses.
2. Salience as derived state means two nodes can rank the same fact differently. Acceptable?
3. Redaction semantics vs "never deleted": confirm the tombstone-with-hash design.
4. Write grants: who signs the first grant for a namespace (bootstrap key ceremony).

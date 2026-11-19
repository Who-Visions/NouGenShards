# Native Memory Engine — durability contract (P0)

Directive shard 31235@db6, P0 phase. This documents the durability settings
of the vault cluster exactly as they are enforced in code
(`src/nougen_shards/core.py`: `get_vault_journal_mode`,
`get_vault_synchronous_mode`, `get_connection`, `_get_dedup_connection`).
No behaviour was changed to write this down: the defaults below are the
effective behaviour the grid already had; P0 only made them explicit and
tested them (`tests/test_p0_preservation.py`).

## Settings

| Setting | Value | Source |
|---|---|---|
| `journal_mode` | `WAL` (default) | `NOUGEN_VAULT_JOURNAL_MODE` env, else auto-detect (DELETE on object-storage / HF Space mounts) |
| `synchronous` | `FULL` (default) | `NOUGEN_VAULT_SYNCHRONOUS` env (`OFF` / `NORMAL` / `FULL` / `EXTRA`); invalid values log a warning and fall back to `FULL` |
| `wal_autocheckpoint` | SQLite default (1000 pages) | Not overridden anywhere in the vault path |
| Explicit `wal_checkpoint` | None | Deliberate: no explicit checkpoint call exists in the vault path |

`FULL` + `WAL` means a committed transaction survives a process crash and,
barring OS/filesystem failure, a power loss. `NORMAL` would be faster but
risks losing the last transactions on power loss; `OFF` risks corruption.
The same contract applies to the central dedup index (`dedup_index.db`),
which gets the same two PRAGMAs on every connection.

Scope note: the contract covers the 9-DB vault cluster and the dedup index
only. Sidecar databases owned by other modules (`destiny.py`, `distill.py`,
`graph.py`, `history.py`, etc.) set their own `journal_mode` and are out of
P0 scope; unifying them is later-phase work.

## Checkpoint policy

Checkpoints happen the way SQLite does them by default: automatic
checkpointing at 1000 WAL pages (`wal_autocheckpoint`) plus the passive
checkpoint that runs when the last connection to a database closes. There
is no scheduled or periodic explicit checkpoint in the vault path, and no
checkpoint-on-write hook. Rationale (P0): on a live grid an aggressive
checkpoint schedule can stall readers, and no measurement justifies one.
A measured checkpoint policy — e.g. an explicit checkpoint after bulk
ingest or on idle — is P1 work, to be driven by numbers, not by hunch.

## Linux notes (this lane runs on Linux; Phoebus/Blade lanes own their OS)

- WAL needs POSIX shared-memory (`-shm`) and coherent file locking on the
  vault directory. Correct on local Linux filesystems (ext4, xfs, btrfs).
- Network mounts without coherent locking (NFS without a working lock
  manager, FUSE object-storage mounts) must NOT use WAL — that is why the
  journal mode auto-detects `DELETE` for known object-storage environments.
  Forcing WAL there causes corruption and spurious quarantines.
- A vault directory on `tmpfs` is fast but not durable across reboot; never
  point `NOUGEN_VAULT_DIR` at `tmpfs` for a real vault. Scratch vaults in
  `/tmp` are fine precisely because they are disposable.
- The `lane_health()` sensor opens each DB read-only (`mode=ro` URI) and
  uses `PRAGMA quick_check` (not full `integrity_check`) so a health probe
  never creates `-wal`/`-shm` files, never takes a write lock, and stays
  cheap on a multi-GB grid. It never raises: a broken DB reports degraded.
- Sandbox quirk found while baselining on this Linux VM: the sandbox's
  `no_proxy`/`NO_PROXY` contains bracketed IPv6 entries (`[::1]`,
  `[fd8b:...]`), which makes `httpx` raise `InvalidURL: Invalid port: ':1]'`
  at `gradio` import time and fails collection of ~28 test files. Unset
  the proxy variables (`http_proxy`, `https_proxy`, `HTTP_PROXY`,
  `HTTPS_PROXY`, `ALL_PROXY`, `all_proxy`, `no_proxy`, `NO_PROXY`) before
  running the suite on this box. This is an environment quirk, not a repo
  bug; the full-suite baseline below was recorded with those variables
  stripped.

## P0 baseline (recorded 2026-11-16, this Linux VM, local Ollama)

Audit baselines reproduced on scratch vaults (see the gap report §2 for the
audit numbers and `~/workspace/nougen-native-memory/baselines/` for the
artifacts). Later phases measure against these, not against the audit's
numbers alone.

| Metric | Audit (b6c5af2) | P0 repro (this lane) |
|---|---|---|
| Capture mean / p50 / p95 | 298.5 / 295.9 / 492.3 ms | 760.4 / 744.9 / 1005.2 ms (idle box) * |
| Embed misses at capture | 0 | 0 |
| Embedding coverage | 36/36 (0% NULL) | 36/36 (0% NULL) |
| Hybrid retrieve p50 / p95 | 567.7 / 3637.5 ms | 386.2 / 468.8 ms (idle box; 505.3 / 1904.0 ms under suite contention) |
| Keyword-only retrieve p50 / p95 | 72.4 / 188.8 ms | 47.1 / 86.7 ms (idle box; 92.5 / 105.6 ms under contention) |
| Hybrid top-3 hit rate | 9/9 | 10/10 |
| Body-tier Recall@10 / MRR / nDCG@10 | 0.533 / 0.165 / 0.252 | 0.400 / 0.142 / 0.202 |
| Title-tier Recall@10 / MRR / nDCG@10 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 |
| Eval latency p50 / p95 | 512.5 / 3411.3 ms | 391.2 / 3408.7 ms |
| Negatives returning results | 10/10 | 10/10 |
| Eval sweep threshold (final_score) | t=0.0415, recall 0.767, fp 0.000 | t=0.0435, recall 0.683, fp 0.000 |

\* Capture latency is the one number that did NOT reproduce: ~2.5x slower
than the audit even on an idle box (760.4 ms mean; 1035.9 ms while the full
suite ran concurrently). The remaining difference is the corpus: the P0
repro bodies are ~1200 chars of repetitive filler vs the audit's shorter
bodies, so each capture pays a longer Ollama embed call, and the audit's
exact seed corpus was not preserved — only its numbers were. Capture
latency is therefore dominated by embed time, not by the storage path, and
the P0 number is recorded as measured on this corpus, not as a regression.
The same corpus difference explains the lower body-tier recall
(near-duplicate candidates compete harder — the audit's own §2.4 caveat).
All other numbers reproduce within the expected range for a different
synthetic corpus. Later phases should fix one seed corpus and re-baseline
capture latency on it before judging any capture change.

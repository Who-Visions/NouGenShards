# NGS 50K scorecard, main engine (meta-app M1 entry)

## After the write-path elevation (2026-11-24, 5:40 PM EST, same box)

| Phase | Before | After | vs Phoebus entry |
|---|---|---|---|
| A bulk ingest (NO_SYNC, flush/1000) | 1,027/s | **5,736/s** (5.6x) | 4,146/s |
| B batched ingest (remember_many x100) | 1,026/s | **5,175/s** (5.0x) | |
| C durable singles, 1 thread | 846/s, p50 1.11 ms | **2,575/s, p50 0.36 ms** | |
| D group commit, 8 threads | 773/s | **7,950/s** (10.3x) | 6,192/s |
| E random get | 1.36M/s | 1.39M/s | 249K/s |
| G verify | 742/s | **1,089/s** (1.5x) | ~740/s |
| H reopen | 0.231 s | 0.200 s, 407 B/fact | |

What changed: signing reuses the expanded key and public key instead of re-deriving both per fact,
the base point is multiplied with a 64x16 constant-time comb (64 additions, no doublings), inversion
uses the 11-multiply addition chain, the signature is computed outside the writer mutex, appends
enter the log in reservation order, durable writers share one fdatasync per group, and a batch is
one pwrite per segment. Durability contract unchanged: a durable call returns only after an
fdatasync covering its bytes. Sign 145 us, verify ~1.0 ms on this box.

## Before (2026-11-24, 4:55 PM EST)

Run 2026-11-24, 4:55 PM EST, cloud Linux box: 4 vCPU Intel Xeon @ 2.30 GHz, GCC 13.3 `-O2`,
`src/nougenshards.c` (`ngs_libversion()` = 0.3.1-draft), 50,000 facts with ~200-byte bodies.
Reproduce from `engine/ngs`: `make bench` (`BENCH_N=` to change the size).

| Phase | Work | Result |
|---|---|---|
| A bulk ingest | 50,000 `ngs_remember`, `NGS_WRITE_NO_SYNC`, `ngs_flush` every 1,000 | 48.68 s, 1,027 facts/s |
| B batched ingest | 50,000 via `ngs_remember_many`, 100 per durable batch | 48.73 s, 1,026 facts/s |
| C durable singles | 2,000 `ngs_remember`, each fdatasync'd, 1 thread | 846 facts/s, p50 1.11 ms, p99 2.03 ms |
| D group commit | 8 threads x 250 durable `ngs_remember` | 2.59 s, 773 facts/s |
| E random get | 50,000 `ngs_get` by id | 1,359,602 gets/s, p50 0.7 us, p99 1.4 us |
| F full scan | `ngs_scan` over all 50,000 | under 0.01 s |
| G verify | `ngs_verify`: every Ed25519 signature and the hash chain | 67.35 s, 742 facts/s |
| H reopen | close, `ngs_open`, `ngs_stats` = 50,000 | 0.231 s; 20.3 MB on disk, 407 bytes/fact |

Ends `SCORECARD OK`. Phase H needed `ngs_stats`, which this engine stubbed to MISUSE before this change.

## What the numbers say

- **Reads are 5x faster than the Phoebus entry** (get 1.36M/s vs 249K/s), and disk is 10% smaller.
- **Ingest is 4x slower than the Phoebus entry** (~975 us per fact vs ~240 us). A and B match, so the
  cost is signing (Ed25519 + BLAKE3 + CBOR), not fsync. Next elevation: port Phoebus's faster sign path.
- **Group commit does not batch yet**: 8 threads land at 773/s, slower than 1 thread. The Phoebus
  entry gets 6,192/s. Next elevation: one fdatasync per waiting group.
- **Verify ties** the Phoebus entry (~1.35 ms per signature). M2 candidates stand: batch verify,
  base-point table, signed checkpoints.

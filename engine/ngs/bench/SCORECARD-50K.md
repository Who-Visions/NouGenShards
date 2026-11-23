# NGS 50K scorecard, Phoebus entry

Run 2026-11-23, 6:40 PM EST, on an idle Linux box: 4 vCPU Intel Xeon @ 2.10 GHz, ext4,
GCC 13.3 `-O2`, amalgamation `dist/nougenshards.c` (`ngs_libversion()` = 0.3.1-draft).
50,000 facts with ~200-byte bodies. Reproduce from `engine/ngs`:

```
python3 tool/amalgamate.py
cc -std=c11 -O2 -Idist bench/bench_50k.c dist/nougenshards.c -lpthread -o /tmp/bench_50k
mkdir -p /tmp/ngs-bench && /tmp/bench_50k /tmp/ngs-bench
```

| Phase | Work | Result |
|---|---|---|
| A bulk ingest | 50,000 `ngs_remember`, `NGS_WRITE_NO_SYNC`, `ngs_flush` every 1,000 | 12.06 s, 4,146 facts/s |
| B batched ingest | 50,000 via `ngs_remember_many`, 100 per durable batch | 11.91 s, 4,199 facts/s |
| C durable singles | 2,000 `ngs_remember`, each fdatasync'd, 1 thread | 1,937 facts/s, p50 0.47 ms, p99 1.11 ms |
| D group commit | 8 threads x 250 durable `ngs_remember` | 0.32 s, 6,192 facts/s |
| E random get | 50,000 `ngs_get` by id | 249,357 gets/s, p50 3.7 us, p99 8.8 us |
| F full scan | `ngs_scan` over all 50,000 | 0.14 s, 347,834 facts/s |
| G verify | `ngs_verify`: every Ed25519 signature and the hash chain | 66.34 s, 754 facts/s |
| H reopen | close, `ngs_open`, `ngs_stats` = 50,000 | 0.150 s; 22.8 MB on disk, 455 bytes/fact |

Every phase checks its own result (counts, seq numbers, verify OK) and the run ends `SCORECARD OK`.

## What the numbers say

- **Reads are not the bottleneck.** Get and scan run at 250K to 350K facts/s; reopen of 50K facts
  is 0.15 s because open checks CRC, decode, id and chain but not signatures.
- **Ingest is bound by signing, not fsync.** Bulk ingest with no per-fact sync (A) and durable
  batches of 100 (B) land at the same ~4.2K facts/s, about 240 us per fact, which is the
  from-scratch Ed25519 sign plus BLAKE3 and CBOR. Durable singles (C) at ~1.9K/s show fsync adds
  ~0.25 ms on this disk.
- **Full verify is the slow path:** ~1.3 ms per signature check, 66 s for 50K. Fine for an
  offline audit, too slow to run on every open. Candidates for M2: batch Ed25519 verification,
  a precomputed base-point table, and signed checkpoints so verify can start from the last one.
- An earlier run on the same box while the gate was also running gave the same picture
  (A 4,394/s, G 744/s, D 5,926/s).

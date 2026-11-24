# NGS engine — meta-app entry (M1)

The Linux VM lane's entry in the fleet NGS bake-off: an M1 implementation
of the NouGenShards native engine per `docs/memory-engine/SPEC.md`
(draft 0.3.1, PR #1199) against the verbatim `ngs.h` from commit 685901aa.

## Layout

```
engine/ngs/
  include/ngs.h                    public header, byte-identical to 685901aa
  include/check/ngs_header_check.c the spec's own header gate, verbatim
  src/nougenshards.c               the amalgamation (single file, ~2,950 LOC)
  test/test_m1.c                   unit + behaviour suite (117 checks)
  test/crash_harness.c             crash/tamper harness (29 checks, 6 scenarios)
  test/kat_shim.c                  test-only shim exposing primitives for KATs
  test/header_contract.c           Phoebus's conformance pins, verbatim copy
  Makefile                         make / make check / make test / make crash
```

## M1 scope (what works)

- Signed, hash-chained, append-only log: canonical CBOR facts, BLAKE3
  `fact_id` over the body-hash form (SPEC 13.3), Ed25519 signature over
  the id, CRC32C on the segment header and every record.
- API slice: `ngs_open` / `ngs_close` / `ngs_errmsg` / `ngs_errstr` /
  `ngs_free` / `ngs_node_pubkey` / `ngs_flush` / `ngs_remember` /
  `ngs_remember_many` / `ngs_get` / `ngs_scan` / `ngs_iter_next` /
  `ngs_iter_close` / `ngs_checkpoint` / `ngs_verify`.
- Recovery: torn tail (short/garbage final record) truncated on open;
  CRC-bad complete record is corruption — preserved on disk, sticky,
  reads serve the valid prefix, appends and checkpoint refuse with
  `NGS_CORRUPT`, `ngs_verify` reports `NGS_CORRUPT`. `ngs_verify` also
  re-checks every Ed25519 signature and, given a checkpoint, its
  signature, heads and Merkle root.
- Everything outside the slice returns `NGS_MISUSE`: `ngs_recall`,
  `ngs_as_of`, `ngs_invalidate`, `ngs_link`, `ngs_redact`, `ngs_grant`,
  `ngs_mark`, `ngs_rebuild`, `ngs_heads`, `ngs_sync_export`,
  `ngs_sync_import`, `ngs_stats`. Embeddings are validated (finite,
  dimension bounds) and not indexed (M4); salience is validated and
  dropped (derived state, SPEC 5.3).

## Crypto provenance

No vendored code and no external dependencies. Every primitive is
written from its public specification directly in the amalgamation:

- BLAKE3 — from the BLAKE3 paper/reference algorithm (G, permutation,
  chunk/parent outputs, CV stack).
- SHA-512 — FIPS 180-4.
- Ed25519 — RFC 8032, with ref10-style radix-2^26 field arithmetic;
  the curve constants (d, sqrt(-1), base point) are derived at context
  init by field exponentiation rather than embedded as magic tables.
- CRC32C — Castagnoli, table-driven, runtime-generated table.

Correctness anchors: the test suite carries known-answer vectors
(BLAKE3 empty/abc, SHA-512 empty/abc, CRC32C "123456789", RFC 8032
TEST 1) and a chunked-vs-one-shot BLAKE3 agreement check over 100 KB.
During development the C BLAKE3 was additionally cross-validated
against an independently written Python implementation over 17 input
lengths including multi-chunk trees (0 … 100,000 bytes), and the
Ed25519 group law against base-point multiples from the RFC 8032
reference implementation.

## Design decisions worth knowing

- **Writer lock is `flock(2)` on POSIX, not `fcntl` F_SETLK.** POSIX
  fcntl locks are per-process: they do not exclude a second handle
  opened by the same process, which would corrupt the log just as
  surely. flock locks are per open-file-description and exclude both.
- **`ngs_ge_to_cached` normalizes to affine first.** The cached form
  carries no Z; converting a projective point without dividing by Z
  silently corrupts it. (This bug cost real debugging time: it breaks
  every precomputed base-table entry past B itself.)
- **Field multiplication compensates the alternating radix.** Limbs
  are 26/25-bit alternating; odd×odd products land one bit higher and
  are weighted ×2 (the same compensation ref10 applies by doubling
  the odd limbs). A uniform-radix schoolbook is wrong here.
- Segment files are `log/000001.seg`, `log/000002.seg`, …; the node
  key seed lives in `node.key` (0600) beside them.
- A corrupt segment header does not fail `ngs_open`: the valid prefix
  (possibly empty) stays readable, the corruption is sticky, writes
  refuse, and `ngs_verify` reports `NGS_CORRUPT`.

## Write path (group commit)

A write reserves its chain position under the mutex (seq, prev, t_record,
fact id), signs and encodes outside it, then appends in reservation order,
so the log stays gapless and in chain order while signatures are computed
in parallel. Durable writers join `ngs_sync_to`: one caller leads a single
fdatasync covering everything appended so far and the rest wait on it, so
N concurrent durable writers cost about two syncs, not N, with no added
delay for a lone writer (`group_commit_ms` is parsed but no timer is
used). `ngs_remember_many` reserves the whole batch at once and writes it
with one pwrite per segment. A segment is fdatasync'd before rollover, so
NO_SYNC records in it are not stranded. Any failure after a reservation
(I/O, fdatasync, OOM) is sticky until reopen, because later facts already
chain onto the lost one; validation errors stay non-sticky.

## Gates (all green at submission)

- `cc -std=c11 -Wall -Wextra -pedantic -Werror`: clean.
- Spec's `check/ngs_header_check.c`: prints `ok`.
- Phoebus's `header_contract.c`: compiles as C11 and C++11; his
  `tests/test_ngs_conformance.py` passes 3/3 against this tree.
- Amalgamation compiles standalone.
- Unit suite: 133 passed, 0 failed (includes 8-thread group commit across segment rollovers).
- Crash harness: 29 passed, 0 failed — kill-mid-write (176 fsynced
  batches acknowledged by the writer child, all 176 recovered intact
  after SIGKILL), torn tail, mid-record truncation, payload tamper
  (CRC), signature tamper with repaired CRC (Ed25519 catches it),
  header tamper.

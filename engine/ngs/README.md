# NGS M1, Phoebus entry (bake-off)

One of four independent M1 builds against `include/ngs.h`, copied unchanged from PR 1199 head
`685901aa` (draft 0.3.1, sha256 pinned in `check/ngs.h.sha256`). Draft only: nothing here is
merged or deployed. The Phoebus conformance harness (PR 1203) is a separate session; this entry is
scored by another machine.

## Scope (M1)

Signed, hash-chained, append-only fact log: `ngs_open/close`, `ngs_remember`,
`ngs_remember_many` (atomic), `ngs_get`, `ngs_flush`, `ngs_scan`, `ngs_verify` (full log;
checkpoint argument is out of scope), `ngs_stats`, `ngs_node_pubkey`, `ngs_errmsg/errstr`.
Every other function returns `NGS_MISUSE`. `supersedes` on a fact is `NGS_MISUSE` too
(invalidation is M3). No extensions.

## Choices

- **No third-party code.** BLAKE3, SHA-512, Ed25519 and CRC32C are written from their specs in
  `src/crypto.c`. Constants come from `tool/gen_consts.py`, which derives them with exact integer
  math (cube and square roots of primes, curve constants mod 2^255-19), not hand-typed tables.
  Checked by `test/crypto_oracle.py`: Ed25519 against OpenSSL (Python `cryptography`) on random
  keys and messages plus RFC 8032 tests 1-3, SHA-512 against `hashlib`, BLAKE3 against the
  published hashes of "" and "abc" and a recursive Python model of the tree.
  **Limit:** that BLAKE3 model shares the compression-function definition, so BLAKE3 beyond the two
  published vectors is not checked against a fully independent implementation.
- **Record format** (`src/log.c` header comment has the full layout): `u32 len | u8 type | payload |
  u32 crc32c`. The payload is canonical CBOR `[fields, sig, body, batch_rest, synced_upto]`, where
  `fact_id = BLAKE3(fields)` and `sig = Ed25519(fact_id)`. The body is outside the id; its BLAKE3
  is inside, so a future redaction keeps the chain verifiable.
- **Atomic batches.** `batch_rest` counts down inside one write, so a torn batch is dropped whole.
- **Torn tail versus corruption.** `synced_upto` records the offset that was durable when each
  write was issued. Open truncates a bad tail only if no later valid record proves those bytes were
  already durable; otherwise it refuses with `NGS_CORRUPT`. The final record gets one more test
  (`looks_torn`): an interrupted append leaves the file short or leaves zero-filled sectors, and a
  bit flip does neither. A full-length record that fails its CRC with no zero sector is refused,
  not dropped. That case also covers a flipped length field: a short-looking record whose bytes
  form a valid record at the true length is refused.
- **Writer lock:** `flock`, not `fcntl(F_SETLK)` as SPEC 15 lists. fcntl locks belong to the
  process, so a second handle in the same process got the lock too, and closing either descriptor
  dropped it (the POSIX smoke test caught this).
- **Durability:** `F_FULLFSYNC` on macOS, `fdatasync` on Linux. A failed write is truncated
  back off, and a failed fsync makes the handle stop writing.

## Known limits

1. A genuinely torn final write that leaves random garbage (not zeros, and not short) is refused
   rather than truncated: safe, but the store then needs an operator. In return, a bit flip in the
   final record is never silently dropped (4,000 of 4,000 flips refused). A flip inside a
   record that already holds a 512-byte-aligned run of 32 or more zero bytes would still read as
   torn.
2. `plat_win32.c` is not written: the platform layer is POSIX only, built and tested on macOS
   x86_64 (Apple clang 17). Not built with gcc or on Linux yet.
3. One mutex per handle, and one write + fsync per call: no group commit yet (M2).
4. Open checks CRC, decode, id and chain for every record, but not signatures (cost);
   `ngs_verify` checks signatures.

## Gate

`./gate.sh` from this directory: header hash, `check/ngs_header_check.c` (C11, C17, C++11),
every source at `-std=c11` and `-std=c17 -Wall -Wextra -pedantic -Werror`, forbidden-include
grep, amalgamation `dist/nougenshards.c` built alone, crypto oracles, the M1 suite under
ASan + UBSan, and a real-filesystem smoke test against the amalgamation.

Tests (`test/test_ngs.c`, in-memory VFS `test/memvfs.h`):
- API round trips and misuse
- bit flips at random positions, 4,000 trials; any lost acknowledged fact fails the test
- a byte changed under a live handle
- 6 threads writing and reading
- the crash suite: the process is killed at each of the workload's 39 mutating I/O calls, then 20
  power-loss patterns each (780 runs). Unsynced writes persist in any subset (reordering), torn at 512-byte
  sectors, and files whose directory was never synced can vanish. After each, open must succeed,
  verify must pass, every acknowledged fact must be intact, every batch all-or-nothing, and the
  log must accept new writes.

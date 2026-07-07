# War-Game: Ingest Junk Gate (HARDENING invariant 7)

**Author tier:** Fable/Coach. **Executor:** Coach-direct (precision edit).
**Mission:** stop low-signal blobs (lockfiles, base64/hex dumps, minified
JSON/SVG, whole `encoder.json` vocabs) from being sharded as "knowledge" —
they pollute recall and waste embeddings. `capture()` already computes a
`density_score`; the gap is that nothing *acts* on signal quality at write time.

## Threat shape
The pollution class is not prose or source code — it is **long, near-whitespace-free,
alphabet-concentrated payloads**: a single unbroken 50k-char base64 string, a
minified bundle, a hex blob. Real prose/code wraps and carries whitespace and
diverse vocabulary. So the discriminator is structural, not semantic — no LLM
call needed, and false positives on genuine writing are near-zero if tuned to
the *longest whitespace-free run* rather than aggregate ratios.

## Move 1 — Red test
`tests/test_ingest_junk_gate.py`: capture a 50k base64 blob and a lockfile-shaped
dump; assert `capture()` returns False and no shard lands. Capture ordinary prose
and a normal code snippet; assert both DO land.
- **Expected pre-patch:** blob captures land (returns True) → FAILS.
- **Failure signal:** blob already rejected → dedup/density already gates; inspect.
- **Countermove:** if a real code snippet is wrongly rejected, the run-length /
  alphabet thresholds are too tight — loosen via the env knobs, never inline.

## Move 2 — Patch capture()
Add `_looks_like_blob(content)`: fires only when the longest whitespace-free run
exceeds `NOUGEN_JUNK_MAX_TOKEN` (default 2000) AND that run is ≥
`NOUGEN_JUNK_ALPHABET_RATIO` (default 0.95) base64/hex charset. Call it right after
the secret-redaction guard (before dedup/embed/write — cheap, saves work).
Separately, an OFF-by-default density floor: reject when the computed
`density_score < NOUGEN_MIN_DENSITY` (default 0.0 = disabled), so operators can
opt into stricter filtering without silently dropping borderline prose today.
Return False on rejection — same contract as a dedup skip.
- **Expected:** red test green; full suite stays green (303+). Existing captures
  are prose/short → unaffected.
- **Fork:** if a determinism/brain-scan test seeds a long token that trips the
  gate → inspect the seed; if legit, it will have whitespace/diverse alphabet and
  pass. If not, the gate is correct and the seed is junk.

## Move 3 — Verify + land
Full suite; HARDENING invariant 7 → ✅ (write-path lane); commit; shard.
- **Abort:** if any real corpus sample trips the blob gate, widen `NOUGEN_JUNK_*`
  defaults and ship the density floor disabled.

## Ledger
- (variable) One-time junk sweep of the live substrate to purge already-ingested
  blobs? Deferred — read-only audit first (count blob-shaped shards) before any
  delete; live-vault mutation needs GM sign-off.

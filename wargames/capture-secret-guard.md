# War-Game: Structural Secret Guard in capture() (HARDENING invariant 8)

**Author tier:** Fable/Coach. **Executor:** Coach-direct (precision edit, routing rule 5).
**Mission:** secrets must be redacted at EVERY shard write, not just the bulk
brain_scan path. Doctrine (Atibon/Keymaker): shards may reference key *names* +
fingerprints, never plaintext values. `redact_content` already exists and is
well-tested — the defect is that `core.capture()` doesn't call it, so any
MCP `capture_experience`, hook, or fleet write can still land a raw `hf_...`
/ `sk-...` / `AIza...` in the substrate.

## Move 1 — Red test
`tests/test_capture_secret_guard.py`: capture a shard whose content + title
carry live-shaped fake secrets, then read it back via `get_shard_by_id` and
assert the stored row contains `<REDACTED_*>` markers and none of the raw
secret material.
- **Expected pre-patch:** FAILS — raw secret round-trips into the DB.
- **Failure signal:** passes pre-patch → capture already redacts somewhere;
  stand down and just document.
- **Countermove:** if it passes because dedup/embedding swallowed it, inspect
  the stored row directly, not the return value.

## Move 2 — Patch capture()
At the very top of `capture()`, before density scoring, dedup hashing,
embedding, and write, run `redact_content` over `content` and `title`, and
over each tag. Reuse the existing module (Rule 0.2 — no new regex). Wrap in
try/except so a redactor error never blocks capture (fail-OPEN on redaction
availability, but the module is stdlib-`re` only, so failure is near-impossible).
Redact BEFORE hashing so the dedup identity is the clean text — two writes of
the same secret-bearing content dedup identically, and the hash never encodes
a secret.
- **Expected:** red test green; full suite stays green (297+). Existing bulk
  importer still redacts (double-redaction is idempotent — markers contain no
  secret-shaped substrings).
- **Failure signal:** brain_scan tests regress (double-redact changes counts).
- **Fork:** if `secrets_redacted` counting in importer breaks → importer counts
  by comparing pre/post; since capture now also redacts, importer's own
  pre-redaction still fires first and its count is unchanged. If a determinism
  test regresses → redaction is deterministic, so suspect the test seeds a
  secret-shaped string incidentally; inspect and adjust the seed, not the guard.

## Move 3 — Verify + land
Full suite; update HARDENING invariant 8 → ✅ (agent lane); commit; capture
milestone shard.
- **Abort:** if double-redaction proves non-idempotent on any real corpus
  sample, gate the capture-level redaction behind a flag and ship red test as
  documentation only.

## Ledger
- (variable) Should capture log a structural marker when it redacts (for the
  fingerprint ledger)? Deferred — Atibon vault owns fingerprinting; capture
  just must not store plaintext. GM input welcome.

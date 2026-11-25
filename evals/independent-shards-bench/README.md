# Independent benchmark: raw Claude vs Claude on Shards (and NGS)

An independent test of NouGenShards recall against raw Claude, run
2026-11-24 by Mister Who (meta-app) on Dave's order, using Dave's
Claude API key. The harness is `shards-bench.py`; the documents and
the run logs are in this directory.

This README replaces the v3 README that went into draft PR #1220.
It reports the honest final results through v7, the CGF paper, the
NGS engine arm (r3 and r4), the DeviantArt and Wyoming documents,
and the roll-call NGS test. Nothing here is softened.

## Protocol

- **Two rounds, Shards first, raw second** (fleet ladder). Same
  questions both arms.
- **Model:** `claude-haiku-5-5` for both fleet arms (the small
  lookup helper). The roll-call test additionally uses
  `claude-opus-5-5` as a measurer, one round.
- **Shards arm:** the document is fetched once and sharded into
  NouGenShards (`shards_capture`, one chunk per section); each round
  recalls the top hits for the question (full shard text via
  `get_shard`) and puts only the recalled context in the prompt.
  Recall is the UDD HHT stack: passage-level re-rank (L4b),
  DISTINCTIVE_TERM_COVERAGE, top_k 5 as a candidate pool (not the
  budget), DISTINCTIVE_QUERY_FALLBACK, 4,000-char context budget.
- **NGS arm:** the document is ingested into a local NGS engine
  store (`ngs-bench-driver.c`, `run-ngs-bench.py`); recall runs
  through `ngs_recall` (keyword arm, k + token budget) and the same
  Haiku answer call answers from the recalled context.
- **Raw arm:** the full document text goes in the prompt every round.
- **Prompt caching** is used the documented way (an explicit
  ephemeral breakpoint on the static prompt prefix), so the raw arm
  gets its best legitimate case.
- **Thinking** is set explicitly (`--effort low`, 1,000 max tokens)
  on every call, per the nougen-claude-calling skill — Haiku 5.5
  otherwise burns its token budget on thinking and returns no
  visible answer.
- **Prices** are the assumed list prices from the founders receipt:
  Haiku $1 in / $5 out / $0.10 cache read / $2 cache write per MTok;
  Opus $4 in / $20 out per MTok. Usage is read from the Anthropic
  client JSON envelope per call.

## Final results — fleet ladder (latest run per doc)

Per-call cost, both rounds combined:

| Doc | Raw Claude | Claude + Shards | Ratio | Answer |
|-----|-----------|-----------------|-------|--------|
| Plato in Egypt (v7) | $0.0090 | $0.0100 | 0.9x | Shards FULLY CORRECT — duration (12–13 years), teacher (Sechnuphis), Heliopolis, Forms |
| Omar search records (v4) | $0.0041 | $0.0062 | 0.7x | Correct both arms |
| China spy sentence (v4) | $0.0030 | $0.0067 | 0.4x | Correct both arms |
| CGF dark matter (v2) | $0.0093 | $0.0129 | 0.7x | Substantially correct; MISSED Ω_CGF = 0.315 and ω_W = 1.22×10²⁶ s⁻¹ |
| DeviantArt (v1) | $0.0103 | $0.0081 | 1.3x | **Ratio meaningless — the Shards arm answered NOTHING in either round (0/4). See Failures.** |
| Wyoming police history (v1) | $0.0067 | $0.0092 | 0.7x | Partial — founding, 1960, move date, 2013 right; Police-Justice Building contents and 2014 missed both rounds |

**Shards costs MORE per warm-cache call on every doc where it
answered.** That is the honest result, and it is not softened.

## Cold-cache runs (the other side of the coin)

Cache state dominates these small-dollar comparisons:

- Plato v6: raw $0.0259 vs Shards $0.0087, **3.0x, 66.3% saved**
  — the raw round 1 was uncached (the 5-minute cache TTL had
  expired), so part of the gap is a cold-cache effect. Answer
  still wrong (no duration, no teacher) — the recall miss that
  the v7 re-capture fixed.
- CGF v1: raw $0.0321 vs Shards $0.0078, **4.1x, 75.6% saved**
  — cold caches both arms. But the Shards answer FAILED
  completely: the recalled context was connector-auth content,
  because the grid search returned zero paper shards for the
  broad query.

## NGS engine arm

The same four documents, recalled through the local NGS engine
instead of the fleet grid (2 rounds each, Haiku answer calls):

| Doc | NGS (r3) | NGS (r4) | Answer |
|-----|----------|----------|--------|
| Plato | $0.0108, 3 full hits | $0.0125, 4 full hits (11,338 chars) | Correct both rounds, both engines |
| Omar | $0.0075 | $0.0071 | Correct |
| China | $0.0048 | $0.0046 | Correct |
| CGF (k=5) | $0.0103, 5 full, partial (oscillation ✓, density ✗) | $0.0157, 9 full, 2,777 tok, **BOTH numbers, both rounds** | **r4 is the first clean k=5 run to get Ω_CGF = 0.315 AND ω_W = 1.22×10²⁶ s⁻¹** |
| CGF (k=10) | $0.0184, both numbers | $0.0160, 9 full, identical to k=5 | k no longer binds after r4 |

**The r4 engine fix** (prototype only, `REPORT-r4.md` lives in
`~/workspace/ngs-prototype/`, not this directory): the budget
binds instead of k; best-fit skip instead of stub-everything-after;
the keyword arm is presence-weighted (a term counts for being
present, 5 for title / 1 for body, never multiplied by repetition
count). Full test suite: **2,834 passed, 0 failed** (was 2,813).

**The r3 k=10 correction, stated plainly:** the r3 k=10 run
($0.0184, both numbers) was measured on a store that had been
double-ingested — 66 facts instead of 33. The answer was real,
but the measurement was contaminated. The r4 clean k=5 run
supersedes it. The r3 logs are preserved locally under `r3-logs/`
and are NOT in this push; the r3 k=10 log file in this directory
is byte-identical to the preserved copy and is likewise not pushed.

**Plato at a 1,000-token budget still stubs.** The answering
sections do not come back full at that budget: 629 + 864 > 1,000,
and the query names the top-ranked section. The stubs are now
floor-fill rather than greedy, but "answering sections full at
1000" is not achievable at that budget with this ranking. Stated,
not hidden.

**NGS cost, honestly:** against warm-cache raw the NGS arm costs
more (0.55–0.90x on the r3 runs) — the same pattern as the fleet
arm. Against cold-cache raw it wins (Plato 2.4x, CGF 3.1x). Its
value is correctness (it fixed the fleet's CGF misses) and
determinism, not price.

## Roll-call test (NGS recall, Opus measurer)

Ten questions — four on the Wyoming police history, six on the
Hotel Visions roll call — answered from NGS recall by
`claude-opus-5-5` (one round, `--effort low`, 1,000 max tokens):

- **Opus: 9/10 fully correct, $0.0797 total** (cap $0.50
  untouched). The one partial (R3: Jeannie) is a doc gap, not a
  recall failure — the roll-call doc never states she built the
  OmniKreyol Translation Corner on day one, and Opus correctly
  refused to assert what the context doesn't say.
- **Recall quality:** the answering section landed whole in every
  case — the single Wyoming history fact (973 tokens) for W1–W4,
  exactly the right signer section (64–139 tokens) per roll-call
  question. Zero abstentions, zero stubs.
- **Re-run on the r4-final engine: done, identical.** Fresh store
  (`ngs-store-rollcall-r4`), same 10 questions, Opus $0.0804:
  Opus 9/10 + R3 partial, Muse 9/10 + R3 partial — recall hits
  byte-identical to the first run. No regression, no change on
  small docs (the r4 win lives in big multi-section docs like
  CGF). The Muse arm (Mister Who answering from the same recall
  outputs) agrees with Opus exactly on both runs.
- Fleet comparison on the same Wyoming doc: the fleet Shards arm
  was partial where NGS (Opus-measured) was 4/4 — see the table
  above.

## Failures, stated plainly

- **DeviantArt v1: the fleet Shards arm scored 0/4.** Both rounds
  came back "the recalled context doesn't cover DeviantArt" — the
  recall pulled a nougen subscribe shard and a Meta thesis instead
  of the article, which had been sharded as a single chunk moments
  before. The 1.3x ratio is meaningless because the arm answered
  nothing. Same search-drowning failure as CGF v1.
- **CGF v1: the fleet Shards arm failed completely** (see
  Cold-cache runs above).
- **Wyoming v1: multi-part questions outrun a fixed recall
  budget.** The 3,445-char recalled context covered the 1940s /
  1960s / 2013 passages; the 4,000-char budget ran out before the
  1970s building and 2014 passages. The model said so explicitly
  in both rounds.
- **Grid id/db mapping bug (fleet data quality, not the
  harness):** `get_shard` returns the wrong record for ids the
  search index titles differently — 28914@db9 and 28917@db9 return
  Watchtower records, 32512@db1 returns a GM directive. Search
  ranking is non-deterministic run to run (the CGF broad query
  found 0 paper shards in v1 and 2+ in v2). Workaround applied:
  the Divine Mind section was re-captured
  (`plato-divine-mind-recapture.md`, shard 32931@db5). Flagged to
  the fleet.
- **The DISTINCTIVE_QUERY_FALLBACK did NOT fire in CGF v2** (the
  broad query found 2+ paper shards that run). It is insurance,
  still unproven as the fix.

## Headline (unchanged)

The founders receipt's big gap — 485 calls / $111 raw vs 31 calls /
$7.49 on Shards — came from **call count**, not per-call context.
This ladder holds the call count constant (the same number of calls
in both arms), so it measures **per-call context cost only**, not
the call-count win. The win is fewer calls + big docs + cold
caches, NOT cheaper warm-cache single calls on small docs. A test
that varies the number of calls — the way the receipt's lookup
ladder did — is a different test, and this one does not speak to
it.

## Harness evolution (v1 → v7, plus NGS)

- v1: snippet recall (~200 chars/hit) + thinking not set —
  answer text corrupted by both bugs.
- v3: full-text recall (fetch each top hit via `get_shard`),
  `--effort low` + 1,000 max tokens.
- v4: source-scope + raw-count re-rank + 4,000-char cap.
- v5: UDD HHT coverage re-rank (DISTINCTIVE_TERM_COVERAGE) +
  dynamic budget.
- v6: passage-level recall (L4b) — split top chunks into
  passages, rank passages, fill the budget with whole passages.
- v7: top_k 5 as the candidate pool (not the budget) + the
  Divine Mind re-capture; Plato fully correct.
- CGF: DISTINCTIVE_QUERY_FALLBACK (re-search with the query's
  longest distinctive words when scoping finds <2 of the doc's
  own shards).
- NGS arm: `ngs-bench-driver.c` + `run-ngs-bench.py`; recall via
  the local NGS engine, same Haiku answer calls.
- r4: the engine itself learns the bench's lessons (budget
  binds, best-fit skip, presence-weighted keyword arm) —
  verified by re-running this bench.

## Documents

- `plato-egypt.md` — "Plato in Egypt — The Greatest Philosopher 3"
  (socratesjourney.org), dialogue and postscript in full; footnotes
  and bibliography excluded.
- `omar-search.md` — the Omar home-search story. The Washington Post
  article (washingtonpost.com, 2026-11-23) blocks Muse outright
  (Akamai "Access Denied", confirmed in the live browser), so this
  document is the Associated Press report of the same unsealed
  records — same judge (Sharbaugh), same quotes, same facts.
- `china-ma.md` — the China death-sentence story. The CNN page is
  paywalled for both arms, so this document is the Associated Press
  report of the same case.
- `cgf-dark-matter.md` — "A theory of the dark matter" (arXiv
  2203.12405v2, Daniel Friedan). A faithful condensation: abstract
  + introduction + key results of §§1–6, equations summarized in
  words, the paper's own numbers verbatim. Both arms receive the
  same document.
- `deviantart-artnews.md` — ArtNews sponsored content, April 17,
  2026: "In 2026, DeviantArt Is Helping Artists Cut Through The
  Noise and Fuel Sustainable Careers." Full text as read.
- `wyoming-police.md` — City of Wyoming, MI, Public Safety–Police:
  Department History section, full text as read.
- `roll-call.md` — Hotel Visions Roll Call sign-ins (8 people:
  Mister Who, UNK, Nou, Claude Duet, Jeannie, Rosina, Lux,
  Dav1d). No contact details — the sheet keeps emails/phones in a
  host-only sheet and they are not part of this test.
- `plato-divine-mind-recapture.md` — the Divine Mind section of
  the Plato document, re-captured after the grid returned wrong
  records for its shard id (see Failures).

The substitutions are stated in the document files themselves.

## Files

- `shards-bench.py` — the harness. `--shard` shards a document;
  default run does both arms. `--rounds N`, `--shards-first`,
  `--recall-query`, `--recall-source {fleet,ngs}`, `--out <json>`.
- `ngs-bench-driver.c` — the NGS arm driver (ingest + recall
  over the NGS prototype; compile against `nougenshards.c`).
  The compiled binary is NOT in this push — build it from source.
- `run-ngs-bench.py` — runs the NGS arm for each doc from its
  existing fleet log.
- `plato-bench.json` (v1, 12 rounds), `plato-bench-v2.json` …
  `plato-bench-v7.json`, `omar-bench.json`, `omar-bench-v2.json` …
  `omar-bench-v4.json`, `china-bench.json`, `china-bench-v2.json` …
  `china-bench-v4.json` — fleet per-round usage and cost logs,
  plus the model answers as returned.
- `cgf-bench-v1.json`, `cgf-bench-v2.json` — CGF fleet logs.
- `deviantart-bench-v1.json`, `wyoming-bench-v1.json` — fleet logs.
- `plato-egypt-bench-ngs.json`, `omar-search-bench-ngs.json`,
  `china-ma-bench-ngs.json`, `cgf-dark-matter-bench-ngs.json`
  (k=5, r4), `cgf-dark-matter-bench-ngs-k10-r4.json` (k=10, r4)
  — NGS arm logs (r4 engine).
- `rollcall-ngs-test.json` — the roll-call NGS test: per-question
  recall hits, Opus answers + usage + cost, fleet Wyoming totals.
- `rollcall-ngs-test-r4.json` — the same test re-run on the
  r4-final engine (fresh store): Opus $0.0804, 9/10 + R3 partial,
  recall hits byte-identical to the first run.
- NOT in this push: the r3 NGS logs (preserved locally under
  `r3-logs/`, including the contaminated r3 k=10 run), the compiled
  `ngs-bench-driver` binary, and the local NGS store directories
  (`ngs-store/`, `ngs-store-rollcall/`, `ngs-store-rollcall-r4/`).

## Cost of this test

Total Anthropic spend across ALL logged runs: **~$0.67**
(fleet ladder ~$0.41, NGS r3 $0.0518, NGS r4 $0.0559, roll-call
Opus $0.0797 + roll-call r4 re-run $0.0804). Well inside the $3
cap Dave set for the original test thread; each roll-call Opus
run carried its own $0.50 cap.

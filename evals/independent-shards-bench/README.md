# Independent benchmark: raw Claude vs Claude on Shards

An independent test of NouGenShards recall against raw Claude, run
2026-11-24 by Mister Who (meta-app) on Dave's order, using Dave's
Claude API key. The harness is `shards-bench.py`; the documents and
the run logs are in this directory.

## Protocol

- **Two rounds, Shards first, raw second.** Same questions both arms.
- **Model:** `claude-haiku-5-5` for both arms (the small lookup helper).
- **Shards arm:** the document is fetched once and sharded into
  NouGenShards (`shards_capture`, one chunk per section); each round
  recalls the top 5 hits for the question (full shard text via
  `get_shard`) and puts only the recalled context in the prompt.
- **Raw arm:** the full document text goes in the prompt every round.
- **Prompt caching** is used the documented way (an explicit ephemeral
  breakpoint on the static prompt prefix), so the raw arm gets its
  best legitimate case.
- **Thinking** is set explicitly (`--effort low`, 1,000 max tokens)
  on every call, per the nougen-claude-calling skill — Haiku 5.5
  otherwise burns its token budget on thinking and returns no
  visible answer.
- **Prices** are the assumed list prices from the founders receipt:
  Haiku $1 in / $5 out / $0.10 cache read / $2 cache write per MTok.
  Usage is read from the Anthropic client JSON envelope per call.

## Results — v3 (fixed harness), 2 rounds, Shards first

Per-call cost (both rounds combined):

| Doc | Raw Claude | Claude + Shards | Ratio | Saved |
|-----|-----------|-----------------|-------|-------|
| Plato in Egypt | $0.0076 | $0.0127 | 0.6x | −66.4% |
| Omar search records | $0.0039 | $0.0120 | 0.3x | −204.1% |
| China spy sentence | $0.0027 | $0.0114 | 0.2x | −316.7% |

**Shards costs MORE per call on these docs.** That is the honest
result of this test, and it is not softened.

**Answer quality (v3):** the Shards arm answered correctly on the
Omar and China questions. On Plato it got the Forms ideas right but
missed the duration (12–13 years) and the teacher (Sechnuphis),
because the top-5 recall did not include the chunk holding them —
a recall-precision miss, stated plainly. The raw arm answered all
three questions correctly.

## Why Shards cost more here

- Full-text recall of the top 5 hits pulls 2,376–2,858 tokens of
  context, versus 858–1,480 tokens for the raw documents. The
  recalled set includes noise shards — the NouGen News pointer
  shards and the fleet's own cost-test shards for the same stories —
  which add context without adding answerable facts.
- The model writes longer answers from messier context (570–748
  output tokens on the Shards arm vs 250–653 on the raw arm), and
  output tokens are the expensive ones ($5/MTok).
- The raw arm's round 1 was also warm — its prompt was already
  cached from the earlier runs — which flattered raw.

## What this test does NOT measure

The founders receipt's big gap — 485 calls / $111 raw vs 31 calls /
$7.49 on Shards — came from **call count**, not per-call context.
This ladder holds the call count constant (the same number of calls
in both arms), so it measures **per-call context cost only**, not
the call-count win. A test that varies the number of calls — the
way the receipt's lookup ladder did — is a different test, and this
one does not speak to it.

## Earlier runs (v1, 12 rounds, raw first)

Plato, 12 rounds: raw $0.0558 vs Shards $0.0275 (2.0x, 50.7%
saved). Those numbers are reported for completeness, but the v1
answer text was corrupted by two harness bugs: the recall fed the
model search snippets (~200 chars each) instead of full shard text,
and thinking was not set explicitly, so Haiku 5.5 burned its
400-token budget on thinking and returned no visible answer on
many rounds. The v3 fixes address both. The v2 run (2 rounds,
Shards first, snippet recall, 400 max tokens) sits between the two
and has the same recall flaw: Plato 1.4x, Omar 1.2x, China 0.9x.

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

Both substitutions are stated in the document files themselves.

## Files

- `shards-bench.py` — the harness. `--shard` shards a document;
  default run does both arms. `--rounds N`, `--shards-first`,
  `--recall-query`, `--out <json>`.
- `plato-bench.json` (v1, 12 rounds), `plato-bench-v2.json`,
  `plato-bench-v3.json`, `omar-bench.json`, `omar-bench-v2.json`,
  `china-bench.json`, `china-bench-v2.json` — per-round usage and
  cost logs, plus the model answers as returned.

## Cost of this test

Total Anthropic spend across all runs (v1 + v2 + v3, three docs):
under $0.25. Well inside the $3 cap Dave set for the test thread.

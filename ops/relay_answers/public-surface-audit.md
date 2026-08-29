# Public Surface Audit — Who-Visions org

**Lane:** whoart / claude-cli · **Captured:** 2026-08-28 · **Method:** `gh repo list` + `gh api repos/{}/readme`
**Answers relay leg:** `20260828T233308Z__chatgpt-app__g-whoentertains` (Update READMEs across all public NouGen repositories)

This is the *measured* starting state, not a plan. Nine public repos; one (`cursor`) is a fork of
an unrelated upstream editor and is out of scope for NouGen documentation.

## Measured state (8 in-scope repos)

| Repo | README bytes | Description | Homepage | Topics | License | Last push |
|---|---:|---|---|---:|---|---|
| NouGenShards | 9,761 | ✅ full | ✅ HF Space | 10 | NOASSERTION | 2026-08-29 |
| nougen-relay | 15,472 | ❌ none | ❌ | 0 | NOASSERTION | 2026-08-28 |
| Kaedra | 16,746 | ❌ none | ❌ | 0 | ❌ none | 2026-08-05 |
| Visions-ai | 11,009 | ❌ none | ❌ | 0 | ❌ none | 2026-08-02 |
| antigravity-local-worker-docs | 4,047 | ✅ full | ❌ | 0 | ❌ none | 2026-06-04 |
| unk-app-ai | 5,170 | ❌ none | ❌ | 0 | ❌ none | 2026-01-18 |
| Yuki-Ai | 2,433 | ❌ none | ❌ | 0 | ❌ none | 2026-01-05 |
| Nyx-Playground | **18** | ❌ none | ❌ | 0 | ❌ none | 2025-11-19 |

## Findings, ranked

1. **`Nyx-Playground` has an 18-byte README.** That is a title line and nothing else. A public
   repo with no README is a worse public surface than a stale one — there is nothing to drift
   *from*. Either write one or make the repo private.
2. **6 of 8 repos carry no license at all**, and the two that do resolve to `NOASSERTION`
   (GitHub could not match the file to an SPDX identifier). For a project whose pitch is
   "local-first, yours" this is the single highest-cost public-surface defect: without a license,
   the default is all-rights-reserved and no one may legally use the code. This outranks README
   prose and is not something a docs compiler can fix.
3. **7 of 8 repos have no description and no topics.** The description is the only text most
   people ever read — it is the README of the README. `nougen-relay` has a 15KB README and an
   empty one-line description, which is exactly backwards.
4. **Terminology is unverified across repos.** Nothing yet enforces that `nougen-relay`,
   `NouGenShards`, and this repo use the same words for the same concepts. That is the drift class
   a compiler can own; the three above are not.
5. **Four repos are >6 months stale** (`unk-app-ai`, `Yuki-Ai`, `Nyx-Playground`,
   `antigravity-local-worker-docs`). Staleness of *content* is a different bug from staleness of
   *docs*; decide archive-vs-maintain before spending words on them.

## Sequencing consequence

Findings 1–3 and 5 are **repo metadata and licensing**, not README prose. They are cheap,
deterministic, and independent of the docs compiler. Findings 4 and the README bodies themselves
should wait for the compiler, because hand-editing eight READMEs that a compiler will later
regenerate is wasted work.

**Do metadata first, prose second.** That is the order-of-operations answer the leg asked for.

# Agent CLI changelog: Claude Code 0.2.21 → 2.1.291

Source: [anthropics/claude-code CHANGELOG.md](https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md), fetched 2026-10-06 12:58Z. That covers 413 versions and 7,162 bullets. All 1,069 Added/Changed/Removed bullets were read in full. The 3,693 Fixed bullets were sorted with a regex census into 18 failure classes, and samples of each class were read. Candidates were scored with `nougen_morph.NouGenMorphEngine` at its default acceptance threshold of 0.50.

## Observed evidence

The changelog is the release history of a mature agent harness. Three groups of changes in it apply to NouGen:

- **Scheduling and resume.** Many Fixed bullets cover scheduled tasks that were lost after compaction, or that ran an extra time on resume, respawn or fork (five fixes in 2.1.290 alone). Separately, 43 fixes cover state lost on resume or compaction.
- **Silent failure.** 167 fixes contain the word "silently". The recurring repair is to make a failure name itself: truncated reads report how much went unread, hooks that drop a prompt are reported as failed by name, and a login that wasn't saved stops claiming success.
- **Trust tiers and delegation.** Ten or more versions repeat the rule that repo-local settings can switch things off but can't widen capability. Subagent output now arrives framed as data. Delegation got a concurrency cap and a depth cap of 1.

Fixed-bullet census: permission over- or under-prompting 300, Windows path and shell 296, subagent/teammate 238, state lost or dropped 219, silent failure 167, hang/stuck 148, hooks 146, retry/backoff 95, duplicate run 94, stale state 86.

## Gate results

The engine caps verifiability at the strongest evidence a candidate holds. A changelog that was only read counts as `static` evidence, with a ceiling of 0.6. So a candidate passes only when there's runtime evidence that the gap exists in NouGen. "Held" means below the threshold until a targeted test is written. It doesn't mean rejected.

| Candidate | Score | State | Strongest evidence |
|---|---|---|---|
| announced-truncation-with-offset | 0.757 | **candidate** | runtime: apply_skills returned 92,416 chars this session; the relay hook reports that relay_open truncates |
| skill-context-cost-budget | 0.627 | **candidate** | runtime: apply_skills payload spilled to disk for a single task |
| bounded-watch-and-oneshot-idle-notice | 0.538 | **candidate** | runtime: each prompt injected 15 whoart heartbeats about 19h old |
| lower-tier-narrows-never-widens | 0.379 | held | static |
| end-by-reporting-where-work-lives | 0.377 | held | static |
| shared-retry-budget | 0.339 | held | static: fleet.py:408 retries per prompt, with no ceiling shared across the map |
| ambiguous-outcome-check-before-retry | 0.290 | held | static: 94 duplicate-run fixes |
| actor-id-on-every-event | 0.272 | held | static: connector byline memory |
| delegate-output-framed-as-data | 0.270 | held (already doctrine) | static |
| schedule-survives-compaction-fires-once | 0.267 | held | static |
| fanout-depth-and-concurrency-caps | 0.258 | held (width already capped) | static: coach.py MAX_LANES=6 |
| unattended-prompt-timeout-deny-with-hint | 0.203 | held | static |
| cache-miss-cause-attribution | 0.080 | held | static |

Full scored records: `morph_scored.json` produced by the run (see shard).

## NouGen adaptations (accepted)

1. **Announced truncation.** A reader that cuts content says how many characters went undelivered and accepts an offset or page token to read on. An oversized result is written to a file and returned as a path plus a preview. Targets: `relay_open`, `apply_skills`, and the SessionStart relay hook.
2. **Skill context budget.** `apply_skills` ranks the skills that match a task and caps the total body size it returns (about 20k chars). Skills past the cap come back as names with their token cost and a `load_skill` handle, not inlined.
3. **Event-driven liveness.** A heartbeat writes a status row; it doesn't send an inbox message. The inbox hook drops heartbeats older than one interval. A watch has a deadline and is re-armed explicitly. An idle notice fires once.

## Held for targeted tests (next evidence step)

- **shared-retry-budget:** test that `Fleet.map` on an all-failing route issues at most N requests in total.
- **schedule-survives-compaction-fires-once:** test that nougen_loop/cadence record the fired slot before running, so a restart doesn't repeat it.
- **ambiguous-outcome-check-before-retry:** test that relay_create or shards_capture with a timed-out first attempt produces exactly one record.
- **actor-id-on-every-event:** leg frontmatter gets origin_machine, session_id, parent_session and start_kind (fresh/resume/fork).
- **end-by-reporting-where-work-lives:** close-out legs require a `lives_at` field (commit sha, path or shard id).

## Engine finding (fixed 2026-10-06)

`NouGenMorphEngine.ingest_candidate` checked for brand names with a plain substring match, so the ordinary word "cursor" (a pagination cursor) quarantined a 0.757 candidate. Fixed in PR #741: brands now match whole-word (`\b…\b`), and "cursor" is a brand only as the capitalised product name `Cursor`.

## Implementation status (2026-10-06)

Three accepted candidates and the engine bug were implemented the same day, in two PRs:

| Item | PR | Status |
|---|---|---|
| Engine whole-word brand filter | #741 | merged/open |
| `apply_skills` output cap (skill-context-cost-budget) | #741 | merged/open |
| Fleet shared request budget (shared-retry-budget, promoted by runtime evidence) | #742 | merged/open |
| Inbox stale-heartbeat drain (bounded-watch-and-oneshot-idle-notice) | #742 | merged/open |

`announced-truncation-with-offset` is partly realised by the `apply_skills` cap (it names deferred skills instead of spilling); `relay_open` truncation remains. The other held candidates still await their targeted tests. Related morph records this session: [AI-unlock video](ai-unlock-video-morph.md) and [morluto/rea](rea-morph.md).

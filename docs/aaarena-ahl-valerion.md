# AAArena / Adversarial Heuristic Learning → NouGen (valerion absorb)

Source: arXiv 2610.12341v1, "Can AI Agents Learn Their Way to the Top? Evaluating Heuristic Learning in a
Long-Running Game Agent Competition" (Tsinghua CST, submitted 2026-10-08, preprint, not peer-reviewed).
Full text indexed in the NouGen context store under source `arxiv-2610.12341v1`.

Provenance labels: `paper` = stated in the source. `ours` = mapping to NouGen we propose and have not run.
`assumption` = inference.

## 1. What the paper actually shows (paper)

- **Heuristic learning (HL)**: an AI agent improves a program by editing the code and tools around it, with
  model weights frozen. Reads failures, logs and replays; revises code. (Weng 2026, cited by the paper.)
- **Adversarial Heuristic Learning (AHL)**: HL applied to game policies. Agent reads rules, picks opponents,
  tests revisions, reads replays, edits the executable policy.
- **Two budgets per run**: 128 small-match units (one per opponent tested) and 16 full-pool evaluations.
  Source edits, model calls, tokens and wall-clock have **no** separate limit (Appendix B).
- **Retained-champion scoring**: the reported score is the highest officially evaluated Elo in the run. The
  controller keeps that snapshot, so later revisions can explore without losing a stronger one (§3.3).
- **Workspace**: one persistent session per model-game run, writable workspace, context compaction with the
  agent keeping its own notes to retain experience (B.1).
- **Result**: Opus 5.5 in Claude Code: 6 gold medals (rank 1 on 6 of 12 games). Others: 2–4. No
  configuration topped the other six human ladders. Weaker on games with larger rule descriptions.
- **Ablations (3 games, GLM-5.3, same 128/16 budget)**:
  - Dense replay feedback beats binary win/non-win in all three (Pacman: rank 1 vs rank 11).
  - Opponent selection: agent-chosen beats random and top-four; ladder mixed.
  - Batch size 2–4 opponents per submission was best; 8 spends the small-match budget in fewer, larger requests.
  - Off-policy replays (other players' matches) also improved policies (Pacman 10→1, AntWar 41→19, Miracle 27→15).
- **Cost**: equal interaction budgets, token use varied more than 5× (GPT6-sol 260M total, Qwen 3.8 1,454M).
  Token spend does not track rank. (Appendix D.)
- **Limits the paper names**: game understanding, strategy implementation, long-horizon planning. Gold medal =
  rank 1 under its rating protocol, not a head-to-head win.

## 2. The mechanism, stripped of game-specific wording

The transferable part is a loop, not the games:

1. **Frozen evaluator** with a fixed pool and fixed ratings. The agent cannot edit it.
2. **Two-tier feedback**: cheap, dense, diagnostic signal on a small sample; expensive, scored signal on the
   full pool. Each tier has its own hard budget.
3. **Retained champion**: score is the best validated snapshot, not the last one.
4. **Dense diagnostics beat outcome-only**: keep decision-level evidence (state, action, consequence).
5. **Persistent notes** across context compaction.
6. **Cross-run learning** from others' records (off-policy) works as well as own-run records.

## 3. NouGen parts this maps onto (what already exists)

| AHL piece | NouGen piece on disk | Status |
|---|---|---|
| Frozen evaluator + pool | `NouGen/tools/fleet.py` (`Fleet.map`, `by_vendor`) as the judge; fixed route list in `mcp_config.json` | exists |
| Small-match budget | `NouGen/tools/coach.py` ledger, 60 fleet calls/day, lane cap ≤6 | exists |
| Full-pool budget | none — no per-run cap on expensive evals | **gap** |
| Retained champion | shards `domain_key` living dossier (append-only, never trim) | exists, not wired to a loop |
| Dense feedback | `NouGenMix` `mix_diagnose_live` / probe rows (per-block JSONL) | exists for audio only |
| Notes across compaction | shards capture + `recall_layered` | exists |
| Off-policy replays | `nougentube` ingest + shards recall of other lanes' outputs | partial |
| Work loop | `nougen-loop` (recall → test → scan → commit branch → PR → shard → handoff) | exists, dry-run by default |
| Claim before touching | `relay` / `claim_lane` | exists, must be honoured |

**Concrete candidate targets inside NouGen (ours, not yet chosen):**
- `nougenmix` theory rules (`theory/*.py`): the rules are a policy; a frozen set of reference beats is the pool;
  the audit (`fl_audit_trap_pattern`, `mix_diagnose_live`) is the dense feedback. This is the closest fit.
- `nougen-verse` rap scoring: a policy that scores bars; a frozen judge panel is the pool.
- Fleet routing choices themselves (which lane answers which task class) scored on a held-out prompt set.

## 4. Proposed NouGen AHL loop (ours)

Smallest version that tests the idea without new infrastructure:

1. **Pick one target** with a deterministic evaluator (e.g. the nougenmix audit on a fixed set of reference
   sections). Do not pick one whose score needs a human ear on every run.
2. **Freeze the evaluator** in a file the revising lane cannot edit (pool, ratings, judge prompt, seed).
3. **Two budgets**, set in the run config and logged to `coach_ledger.jsonl`:
   - small: N quick checks on a subset (default 128 units, batch size 4 per the paper's best setting)
   - full: 16 evaluations on the whole set
4. **Dense feedback**: each small check returns the per-item diagnosis, not just pass/fail.
5. **Retain the champion**: write each validated snapshot to a path; the final output is the best scored
   snapshot, not the last edit. Snapshots go through git branch → PR per `nougen-git`.
6. **Notes file** the revising lane must update every step, read back at start of every step.
7. **Judgement calls** (is this revision better?) go to `coach.py ask` majority vote, not one model.
8. **Record cost** per run in tokens and fleet calls. Do not optimise rank alone; the paper shows tokens do
   not track rank.

## 5. What not to copy

- The paper's models run on paid harnesses (Claude Code, Codex). NouGen's rule is free lanes for bulk work
  (Rule 0.3, `save-tokens-route-through-free-lanes`). The revising step is the one place a paid session is
  justified; keep it to that.
- No Claude fan-out on WhoArt. The paper's single-session-per-run shape is fine; a parallel swarm of
  revising agents is not (`no-claude-fanout-on-whoart`).
- Do not treat a gold medal as proof of strength. Our analogue of "rank 1" must be measured against a
  frozen reference, and the reference must not be in the agent's workspace.

## 6. Open questions

- Is the audit score a good enough proxy for "better music"? That needs a human ear check (Dave), not a model.
- Paper: source edits had no budget. For NouGen, a fixed edit count is probably needed to keep cost bounded.
- Preprint, two days old at time of writing. Verify numbers against the final version before quoting outside NouGen.

## Next steps (not done yet)

- Pick the target (proposal: nougenmix theory audit). Needs Dave's call.
- Build the frozen evaluator and run it once with no revisions to get the baseline.
- Shard the result (`shards-memory`, set `NOUGEN_VAULT_DIR` explicitly, verify by recall).
- Relay leg for the handoff (`nougen-relay`).

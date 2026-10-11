# Memento 3 → NouGenShards (valerion absorb)

Source: arXiv 2610.11794v1, "Memento 3: Model-Based Recursive Self-Improvement through Reflective Rulebooks"
(Zhao, Yu, He, Fang, Tutunov, Bou-Ammar, Luo, Wang; UCL, Huawei Noah's Ark, Liverpool). Submitted 2026-10-08.
Preprint, not peer-reviewed. Indexed in the NouGen context store as `arxiv-2610.11794v1`.

Provenance labels: `paper` = stated in the source. `ours` = proposed NouGenShards mapping, not run.
`assumption` = inference.

## 1. What the paper does (paper)

- **Frozen LLM, external memory.** The LLM weights never change. Learning lives in two artefacts:
  - a **rulebook** (natural-language `world_model.md`): revisable hypotheses about how the environment works.
    Unknown parts are left underspecified on purpose.
  - an **executable** compiled from the rulebook (`world_model_engine.py`): predicts the next state and goal completion.
- **Loop**: observation → reflection → rule revision → compilation → verification.
  - A rule-level change is written to the rulebook first, then the code is refined.
  - An implementation-only diagnosis leaves the rulebook alone and changes only the code.
- **Acceptance rule (the part to absorb).** A new executable is accepted only if both hold:
  1. the frozen LLM judges it faithful to the rulebook (semantic check), and
  2. deterministic **cell-exact replay** over the recorded trajectories reproduces every observed transition.
  The paper says acceptance is not based on model confidence, because language-model rankings can drop correct candidates.
- **Population extension**: N rulebook–executable pairs share one interaction history. A planner samples one per
  episode. Any pair whose prediction conflicts with observed data is repaired.
- **Results**:
  - ARC-AGI-3: the single-model agent clears all 25 public games, RHAE 100.0, using 44% of the human action count.
  - Rulebook ablation (3 games, Claude Code): 617 vs 677 actions (−9%), 678 vs 830 agent turns (−18%).
  - Atari Pong: a learned feedback controller wins 21:0 in three episodes with different openings, no LLM calls at run time.

## 2. The paper's own limits (paper)

- Ablation covers three games, and every run cleared every level. It is a cost comparison, not a success-rate test.
- The population result is one game (wa30) at N=2.
- The Pong case study is one learning session.
- The fidelity check is semantic (an LLM judges). Only the replay part is exact.
- The paper calls the population "a computational approximation to the remaining version space, rather than a calibrated Bayesian posterior."

## 3. Mapping onto NouGenShards (what exists)

NouGenShards already has most of the outer discipline. The missing piece is the exact-replay acceptance check.

| Memento 3 piece | NouGenShards piece | Status |
|---|---|---|
| Refuse by default, promote only with proof | `evidence_gate.py`: REFUSES by default, ELIGIBLE needs evidence, rollback path | exists |
| Measured vs reported evidence | `evidence.py`: MEASURED vs REPORTED shard class | exists |
| Rulebook (natural-language hypotheses) | distilled L1 atoms, L2 scenes, L3 persona in `distill.py` (derived sidecar) | exists, but no revision loop against evidence |
| Executable compiled from the rulebook | none: derived layers are text, nothing executes against the shards | **gap** |
| Semantic fidelity check by the LLM | `consolidate.py` decider (model proposes, code verifies) | exists for ADD/SUPERSEDE only |
| Exact replay verifier | none for claims or derived facts | **gap** |
| Rule-level vs implementation-level diagnosis | SUPERSEDE (new shard) vs code fix (PR) are separate paths | conceptually there, not formalised |
| Population of pairs sharing evidence | `dam/` and `league.py` are not this; no multi-candidate store | gap, low priority |

## 4. Proposed NouGenShards mapping (ours, not run)

The narrow version that fits the existing code and tests a single claim:

1. **Replay target**: provenance is already stored. `distill.py` keeps `atoms.shard_key`, `mentions`,
   `edges.shard_key` and `distilled.content_hash` per source shard. Checked in the schema, not yet tested.
2. **Exact replay, only where it is deterministic**. Atom extraction is LLM-driven, so it cannot be re-derived
   exactly; the replay must not pretend otherwise. What can be replayed without a model:
   - staleness: does `distilled.content_hash` still match the source shard? A mismatch means the atoms are stale.
   - referential integrity: does every atom, mention and edge point at a shard_key and entity that exist?
   - scene counts: does `scenes.n_shards` equal the number of distinct shards that mention the entity?
   A mismatch on any of these rejects the derived layer's current state; a model's wording is never checked this way.
3. **Two checks before adoption**, same shape as Memento 3:
   - semantic check by the local model (e2b lane, Rule 0.7), which can only propose or reject;
   - exact replay, which decides.
   An accept needs both; the model alone can never accept.
4. **Route through `evidence_gate.py`**. A candidate that passes both checks gets an ELIGIBLE record with receipts.
   A candidate that fails either check is refused and logged, never dropped silently.
5. **Eval it**, the same way as the consolidation guard: a frozen fixture of claims with known correct derivations,
   split dev/heldout, and report the replay catch rate separately from the semantic check.

## 5. What not to copy

- ARC-AGI-3 and Pong specifics (game-world models). Nothing in NouGenShards is a game environment.
- The paper's runs use paid harnesses (Claude Code). NouGen's Rule 0.3 keeps bulk work on free lanes; the
  semantic check uses the local lane, so this is not a blocker, but the replay check must stay model-free.
- The population extension. Parallel models with shared evidence are a bigger design change than this
  absorb justifies; park it.

## 6. Open questions

- Which derived layer first? The deterministic checks above apply to all layers, so the proposal is to start
  with the scene counts and integrity checks, which need no model at all.
- Does `distill.py` populate these tables in practice, or only define them? The schema is confirmed; the
  row counts on the live vault are not checked yet.
- Preprint, two days old at time of writing. Check the numbers against the final version before quoting.

## Done (2026-10-11)

- Live sidecar checked, read-only: `tools/check_distill_integrity.py` on `~\.nougen\shards
ougen_distill.db`.
  363 distilled shards with status done; 0 stale, 0 orphan, 0 dangling, 0 scene lag.
  Total rows: 376 distilled, 2,316 atoms, 3,702 entities, 4,726 mentions, 2,401 edges, 200 scenes, 1 persona.
- Fault-injection tests: `tests/test_check_distill_integrity.py`, 6 passed. Each check fires on a planted
  fault and stays silent on a clean sidecar. The live zero is trustworthy only because these pass.

## Not done

- No exact-replay for LLM-derived atoms (not possible, see section 4). Only the deterministic checks are built.
- The checker runs on demand. It is not wired into the nightly distill or into `evidence_gate.py` yet.
- Next: wire a stale-count into `evidence_gate.py` so a failing check refuses promotion.
- Shard the result (`shards-memory`, set `NOUGEN_VAULT_DIR` explicitly, verify by recall).

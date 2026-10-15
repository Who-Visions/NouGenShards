# Consolidation guard: frozen evaluator (AHL + MASS absorb)

Sources absorbed (both in `NouGen/docs`, indexed in the NouGen context store):
- `aaarena-ahl-valerion.md`: AAArena / Adversarial Heuristic Learning. Lesson used here: a frozen
  evaluator the revising side cannot edit, dev and heldout split, a gate that reads only heldout.
- `mass-valerion.md`: MASS. Lesson used here: the model proposes, code verifies, guardrails are
  checked in code, not trusted to the model.

## What was built

- `evals/consolidate_v1.jsonl`: 7 facts, 4 dev (C1, C2, C3, C6) and 3 heldout (C4, C5, C7), each with
  an expected final action for four proposal kinds from a scripted decider.
- `tools/eval_consolidate.py`: scores `nougen_shards.consolidate.consolidate` under each proposal.
  The fixture is locked by sha256 (`evals/consolidate_v1.lock.json`).

The four proposal kinds:

| kind | what the scripted model says |
|---|---|
| add | ADD |
| none | NONE |
| supersede_valid | SUPERSEDE of a real neighbour |
| supersede_bogus | SUPERSEDE of id 999 (hallucinated) |

Each check carries a tag. `spec` = the rule is stated in `consolidate.py` or `tests/test_consolidate.py`.
`proposed` = an invariant this eval proposes that the module does not enforce yet.

## Baseline (2026-10-11, fixture sha 74d6838f4643)

| split | checks | spec | proposed |
|---|---|---|---|
| dev | 16 | 13/13 (1.0) | 0/3 |
| heldout | 12 | 10/10 (1.0) | 0/2 |

The 5 proposed failures are real gaps in the store:
- C2 "Likes building automations" with a model NONE: returns NONE, so an unrelated fact is dropped as a duplicate.
- C2 with a model SUPERSEDE of "Likes pizza": returns SUPERSEDE:1, so an unrelated fact retires a live fact.
- C3 "Likes pizza" with a model ADD: returns ADD, so an exact duplicate is stored twice.
- C7 "Owns a red bicycle": the same two gaps as C2.

## Caveats (be honest about these)

- The `spec` labels were written from the module's own docstring and tests, and the code was written to
  satisfy those same rules. A 1.0 on spec is a regression floor, not a proof the rules are right.
- The 5 `proposed` invariants are my reading, not ratified. Turning any of them into a guard in
  `consolidate.py` changes store behaviour and needs an owner decision first.
- The eval measures the verifier only. It does not call a model. The next run (not done) would use
  `ollama_decider` on the local gemma4:e2b-qat lane and report raw vs post-guard accuracy. Per Rule 0.3,
  if Ollama is down that run stops and reports; it does not fall back to a paid route.
- Only 7 facts. Too small for a reliable accuracy; it is enough to show the gaps exist.

## Proposed guards (not implemented; owner call)

1. NONE needs a lexical match to some neighbour above a threshold, else REVIEW.
2. SUPERSEDE needs a lexical match (or a retraction cue) between the new fact and the target, else REVIEW.
3. ADD of a near-identical fact (jaccard >= 0.8 to a neighbour, no retraction cue) becomes NONE.

Each guard should land with its proposed checks moved from `proposed` to `spec`, so the gate stays honest.

## Next steps

- Owner review of the 5 proposed invariants.
- If approved: one guard per branch, PR, merge (memory: always branch, PR, merge; never push to main).
- Run the local-model arm once Ollama is up, and report raw vs post-guard accuracy.

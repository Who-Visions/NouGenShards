# MASS (Multi-Agent Self-Supervision) → NouGen (valerion absorb)

Source: arXiv 2610.12176v1, "Recursive Self-Improvement through Multi-Agent Self-Supervision" (Lee, Xu, Seely,
Lee, Sojoudi, Zaharia, Tang; UC Berkeley and Sakana AI). Submitted 2026-10-08. Preprint, not peer-reviewed.
Full text indexed in the NouGen context store under source `arxiv-2610.12176v1`.
Code: github.com/SakanaAI/mass. Blog: pub.sakana.ai/mass/.

Provenance labels: `paper` = stated in the source. `ours` = proposed NouGen mapping, not run.
`assumption` = inference.

## 1. What the paper shows (paper)

- **Problem**: recursive self-improvement on tasks humans can't reliably grade leaves the model as its own
  optimizer and evaluator. A single instance critiques its own reasoning poorly.
- **Method (MASS)**: one shared base LM plays three roles: agent, self-evaluator, self-optimizer.
  - **Inner loop**: the agent builds a workspace under a *workflow prompt* (a textual multi-agent
    orchestration: roles, instructions, output contracts, call order). The self-evaluator judges the
    workspace. The self-optimizer revises the workflow prompt. This is an evolutionary search.
  - **Structural guardrails** constrain the search. Each workflow has roles with output contracts and an
    orchestrator "hop" sequence.
  - **Outer loop**: SFT on the shared LM, using trajectories from the best workflows. Training tasks are
    ranked by pairwise tournament, scored with Bradley–Terry. The top K−1 trajectories are the training set;
    the Kth is validation. The workflow prompt is removed from the training prompt (the model internalises it).
- **Result**: two MASS cycles on Qwen3.6-27B. 1.2–1.6× higher performance per output token on four open-ended
  public benchmarks (ScienceAgentBench, MLR-Bench, AstaBench, DSBench). Accuracy on the synthetic suite rose
  0.73 → 0.91 → 0.93 across generations.
- **Student result**: SFT on multi-agent traces beat single-agent SFT on 1.4× more training tokens.
- **Evaluation roles** (Table 4): the self-model drives workflow search, teacher ranking and checkpoint
  selection (validation loss). An external panel (GPT-5.5 and Claude Opus 4.8) only reports, and its verdicts
  never feed back into training.

## 2. The paper's own limits (paper, Appendix E/F/J)

- Workflow-information estimates are descriptive text statistics. They are not measurements of execution and
  not a causal test. Agents in one workflow share task text and routing, so they are not independent replications.
- Win rates use two external judges and three seeds, which measures judge variation over the same executions,
  not variation across search runs.
- Edit size has only a weak association with judged quality. Large reversals occur.
- Gains may be partly explained by the optimizer and evaluator improving across generations, not only by the
  workflow mechanism.
- The authors say sharing one model across roles does not by itself imply weight learning, and exporting data
  does not establish that a successor was trained.

## 3. NouGen parts this maps onto (what exists)

| MASS piece | NouGen piece | Status |
|---|---|---|
| Shared base LM in agent/evaluator/optimizer roles | `e2b` (gemma4:e2b-qat) as player, coach (Claude) as reviewer | exists, roles split across two models, not one |
| Workflow prompt (roles, contracts, hops) | skills (`SKILL.md`) and `NouGen/tools/coach.py` call plans | exists as static text, not evolved |
| Output contracts / structured outputs | `format=<schema>` / `response_format json_schema` (Ollama skill) | exists |
| Evolutionary workflow search with guardrails | none | **gap** |
| Pairwise tournament + Bradley–Terry ranking | `coach.py ask` majority vote over ≤6 distinct models | exists as vote; BT ranking is the missing upgrade |
| External judge that never feeds training | coach reviews outputs; no hold-out judge recorded | partial |
| SFT on own best trajectories | none (local e2b is a served model, not trained here) | out of scope for now |
| Frozen evaluator + two budgets | `eval_trap_audit.py` pattern from the AHL absorb | exists for nougenmix audit |

## 4. Proposed NouGen mapping (ours, not run)

Smallest version that tests the paper's core claim (structured multi-role workflows beat one-shot calls at
equal output tokens) without training weights:

1. **Target**: a NouGen task with a deterministic or pairwise-judgeable output. The nougenmix audit (see
   `aaarena-ahl-valerion.md`) or a `coach.py` judgement task both fit.
2. **Workflow prompt** as a versioned file: roles, one output contract per role (JSON schema), and a fixed
   call order. Store it under `skills/` or `fleet/`, not inline.
3. **Evolution**: the coach proposes a new workflow version. The e2b lane executes it. Guardrails: max roles,
   max hops, every role must have a contract, and the output must validate against the schema. A
   version that fails validation is rejected, not repaired silently.
4. **Judging**: pairwise comparisons between workspace outputs from two versions. Rank with Bradley–Terry
   (or a simple Elo) over the comparison set. Use `coach.py ask` with ≤6 distinct models for the votes.
5. **Hold-out judge**: a judge set the optimizer never sees. This is the same frozen-gate idea as the AHL
   absorb. **Caveat**: the paper's external judges are paid models. NouGen's Rule 0.3 says free lanes only,
   so the hold-out judge must be a free route, or Dave authorises a paid judge explicitly for that run.
6. **Budget and cost**: log tokens per version against output quality. Report performance per output token,
   the paper's own metric. Never report rank alone.
7. **Keep the best version**, not the last, as in AHL's retained-champion rule.

## 5. What not to copy

- **Weight SFT on own traces** (the paper's second half). It needs training compute on this box. The local
  GPU is 6141 MiB, and the Rule 0.0.1 relay and Rule 0.5 fleet rules don't cover training. Park it.
- **Paid external judges by default** (Rule 0.3).
- **Parallel swarms of revising agents on WhoArt**. The coach rules cap lanes and forbid Workflow-tool fan-out
  (`no-claude-fanout-on-whoart`, `coach` skill).
- **Single-run claims**. The paper's own variance analysis is weak. Any NouGen claim needs repeated runs
  across seeds, and the judge variation reported separately.

## 6. Open questions

- Does the 1.2–1.6× per-token gain hold on a NouGen task at all, or only on the paper's research benchmarks?
  That needs a baseline with the same token budget first.
- Who labels the first judged pairs? Dave's ear for music, a free-lane vote for text. Same blocker as the
  nougenmix audit labels.
- Preprint, two days old at time of writing. Check the numbers against the final version before quoting them.

## Next steps (not done yet)

- Pick a task with a judgeable output (proposal: the nougenmix audit cases, comparing a single-prompt
  audit against a three-role audit workflow). Needs Dave's call.
- Build the single-prompt baseline and measure tokens per output.
- Shard the result (`shards-memory`, set `NOUGEN_VAULT_DIR` explicitly, verify by recall).
- Relay leg for the handoff (`nougen-relay`).

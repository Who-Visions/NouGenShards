# RACE (When Should Agents Think?) → NouGenShards (valerion absorb)

Source: arXiv 2610.12061v1, "When Should Agents Think? Adaptive Reasoning via Cross-Turn Estimation"
(Cheng, Huang, Song, Tan, Dong, Xie, Wen, Dou; Renmin University, Alibaba Token Hub). Submitted 2026-10-08.
Preprint, not peer-reviewed. Code: github.com/HututuAI/RACE. Indexed as `arxiv-2610.12061v1`.

Provenance labels: `paper` = stated in the source. `ours` = proposed NouGenShards mapping, not run.
`assumption` = inference.

## 1. What the paper does (paper)

- **Problem.** Agents reason before every action. Earlier reasoning often still supports later actions, so
  some reasoning turns are removable. The question is how to find them without generating candidate actions to check.
- **Signal.** After a reasoning turn is removed, the likelihood of the later *reference* actions drops only
  a little if those actions are still recoverable from earlier reasoning. The paper uses that likelihood drop
  as a cheap signal. It needs one likelihood computation per reference action, not a generation.
- **LoGiC** (Likelihood-Guided Progressive Reasoning Cover Detection, Algorithm 1 in App. E). Walk the trajectory
  in order. Remove reasoning turn r_t, recompute the likelihoods of the current and subsequent reference actions in
  the compressed context. Keep the removal only if every affected likelihood drops by less than a threshold ε.
  Retained turns form the *reasoning cover*.
- **Use.** The removal labels feed two training steps: SFT (RACE-SFT) and agentic RL (cover-aware reward/masking).
  The policy learns when to reason and when to act directly.
- **Results** (four agent benchmarks: ScienceWorld, WebShop, AppWorld, DeepSearch; Qwen3.5 backbones):
  - RACE-SFT-RL vs Qwen3.5-9B: reasoning tokens −36.5%, −80.3%, −39.4%, −35.8%, success +54.8, +37.8, +19.0, +5.8 points.
  - SFT only: within 1.88 points of standard SFT, 4.3–20.0% fewer reasoning tokens.
  - SFT+RL: within 1.40 points of SFT+GRPO, 32.3–80.2% fewer reasoning tokens.
  - Removing LoGiC from RL raises reasoning tokens sharply (e.g. AppWorld 1,900 → 8,574).

## 2. The paper's own limits (paper)

- The signal needs likelihoods of the reference actions. The method is only as good as that access.
- The gains come from training (SFT and RL). The prompting-only baselines (Sparse ReAct, ADaPT, DART) are a different comparison.
- Reference actions come from a trajectory. Without a reference, the likelihood signal has nothing to measure.
- Four benchmarks, three model sizes, one family (Qwen3.5). The threshold ε is a fixed hyperparameter; the paper
  does not show how sensitive results are to it in this excerpt.

## 3. Mapping onto NouGenShards (what exists)

| RACE piece | NouGenShards piece | Status |
|---|---|---|
| Reasoning spend per step | `reasoning_governor.py` (advisory), `coach_governor.py` (hard lease) | exists; no per-step necessity test |
| Likelihood of a known answer | `decision/backends/ollama_prob.py`: reads the first-token logprobs of option letters (`num_predict` 1) | **partial**: only single-token option choices; it cannot score a multi-token reference action |
| Constrained JSON loses probabilities | `decision/calibration.py`: "constrained decoding gives no probabilities" | known constraint; use `ollama_prob` path for scored decisions |
| Keep only reasoning that supports later steps | distill/consolidate pipelines reason per item, no cover check | gap |
| Training on removal labels | none, and NouGen does not train its models | out of scope |

## 4. Proposed NouGenShards mapping (ours, not run)

The part that fits without training: a model-free-to-cheap check on whether a reasoning step is needed.

1. **Where it applies.** The e2b judgement calls where reasoning eats the token budget (E-series reasoning channel,
   Rule 0.5.1: `max_tokens` ≥ 1400). Target: `consolidate.py` decisions and `decision/` classifications.
2. **Reference answers.** The eval fixtures (`consolidate_v1.jsonl`, `trap_audit_v1.jsonl`) exist only as
   uncommitted files in the main checkout, not on `main`. Commit them before this step can use them. Reference
   actions must be single-token choices unless sequence scoring is added (see step 3).
3. **Cover test.** For a fixed item, compute the logprob of the reference answer with and without a candidate
   reasoning block. `ollama_prob` cannot do this as-is: it sets `num_predict` to 1 and reads only the first token,
   so a sequence-scoring backend is required first. Drop the block only if the drop is under ε. This is the LoGiC
   step on a single item, not a trajectory.
4. **Measure.** Tokens saved vs decision accuracy on the frozen fixture (dev to tune ε, heldout to gate).
   Report both, the same way as the consolidation eval.
5. **Keep the authority rule.** The cover test can only shorten reasoning. It never decides the answer. A dropped
   block that changes the decision is a failure, counted, and the item goes back to full reasoning.

## 5. What not to copy

- SFT and RL on removal labels. NouGen runs served models and does not train them here.
- Trajectory-level cover over multi-turn agents. NouGenShards does not run long tool-using episodes; the single-item
  version is the honest scope.
- Paid models for the comparison runs (Rule 0.3). The cover test runs on the local lane.

## 6. Open questions

- Does the local Ollama lane return logprobs for the E-series models in practice? Not verified here. `ollama_prob.py`
  reads first-token logprobs only, so the cover test also needs a sequence-scoring backend.
- What ε works on our fixtures? Unknown until the dev sweep runs.
- Preprint, two days old at time of writing. Check the numbers against the final version before quoting them.

## Next steps (not done yet)

- Confirm the logprob path on `gemma4:e2b-qat` with one real item.
- Build the single-item cover test against `consolidate_v1.jsonl` in shadow mode, dev split first.
- Shard the result (`shards-memory`, set `NOUGEN_VAULT_DIR` explicitly, verify by recall).

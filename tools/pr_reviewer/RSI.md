# awesome-rsi (lobehub/awesome-rsi) → NouGen: reversed and leveraged

Fetched 1:28 PM EST Sun 11/15/2026 via `gh api`. The raw README is beside this file.

The list sorts RSI into two levels. **Model-level** RSI updates weights; NouGen fine-tunes nothing, so it is out of scope. **Harness-level** RSI updates prompts, memory, skills and scaffold, and that is exactly NouGen's surface.

## Already built: what the fleet has, and its name in the literature
| NouGen piece | Literature pattern | Entries |
|---|---|---|
| Shards vault + recall packets | Agentic memory / experiential learning | A-MEM, ExpeL, MemoryBank, ReMe, Mnemoverse |
| `skills/` + `evolve_skill` | Skill evolution | SkillOpt, MetaSkill-Evolve, Memento-Skills, Voyager |
| aiwithdav3 checklist vN + lessons | Evolving playbook context | ACE (Agentic Context Engineering), Reflexion |
| aiwithdav3 supervisor on a different lane | Tool-interactive critique / verification | CRITIC, Chain-of-Verification |
| Fleet consensus across vendors | Multi-agent debate / self-consistency | Du et al. multiagent debate, Self-Consistency |
| Relay legs + handoffs | Group experience sharing | Group-Evolving Agents |

## Leveraged this session
- **Holdout adoption gate** in `review.ts score`, landed as commit c31509fd on #1079. It comes from RecurSE (judge validation holdout) and the Safety-in-Self-Evolving-Agents survey, whose finding is that blocking bad state at entry works and repairing descendants afterwards does not.
  - Weights now learn from a train split.
  - A new checklist version is rejected if its weighted precision on held-out findings drops by more than 0.02.
  - Each weight moves at most 0.15 per pass, the RRSI-style regularisation.

## Gaps, ranked by leverage per effort
1. **Self-consistency writer (cheap).** The reviewer drafts with ONE lane. Draft on 3 vendors, then keep only the findings that ≥2 of them raise (Self-Consistency, debate). This cuts dismissed findings directly, which is what the RSI metric measures.
2. **Proposer/solver for the checklist (R-Zero, G-Zero).** Have a lane propose new checklist items from held findings. They enter at weight 0.3 and must survive the holdout gate. Today the checklist can only re-weight; it never grows.
3. **Harness observability → evolution (Agentic Harness Engineering, MemoHarness).** Feed `run.log` lane failures (402s, empty e2b replies) back into the lane order automatically, instead of fixing it by hand.
4. **Skill-level RSI with the same gate (SkillOpt, Meta Context Engineering).** Apply the holdout gate to `evolve_skill`, so a skill rewrite must not regress on recorded task outcomes.
5. **Darwin/Huxley-Gödel archive.** Keep every checklist version, not just the latest, and let an archived branch be resumed when the latest stalls (open-ended archive versus greedy hill-climb).

## Donor repos worth a valerion pass
ACE (`ace-agent/ace`), harness-zero, meta-context-engineering, ReMe (`agentscope-ai/ReMe`), Memento-Skills, OpenEvolve, Darwin Gödel Machine (`jennyzzt/dgm`).

## Out of scope
Model-level RSI (SEAL, SPIN, Self-Rewarding, STaR) needs weight updates. Embodied RSI does not apply to the fleet.

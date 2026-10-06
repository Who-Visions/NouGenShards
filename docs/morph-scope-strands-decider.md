# Strands Decider to NouGen: Pointer-Head System 1 Decision Manifold

Reviewed 2026-10-04.
Donor source: `StrandsAgents/strands-decider-2b` (strands-labs/strands-decider).
Article: https://strandsagents.com/blog/introducing-strands-decider/
Hugging Face: https://huggingface.co/StrandsAgents/strands-decider-2B-hobson-v19

Status: Ingested via `NouGenMorphEngine` (Score: 0.5576, Accepted as Candidate).
No donor code, weights, or external frameworks copied.
Pure architectural distillation into native NouGen routing primitives.

---

## 1. Observed Donor Mechanics

| Donor Mechanism | Donor Implementation | Native NouGen De-Branded Primitive |
| :--- | :--- | :--- |
| **Stripped Generation Head** | Removed causal LM autoregressive output head from Qwen3.5-2B | Eliminate token-by-token generation for routing & policy classification; enforce zero-cost deterministic selection. |
| **Option Pointer Scoring Head** | 1M parameter linear head scoring hidden states at candidate option positions against the `<answer>` token in a single forward pass | Closed-candidate scoring ($k$ options) in single forward evaluation. Prevents syntax hallucinations and JSON schema breaks. |
| **Calibrated Confidence** | Evaluated via Brier score on JevBench to guarantee probability reliability | Calibrated confidence gate ($C \ge \theta$). If below threshold, escalate from System 1 (Local E2B/Decider) to System 2 (Frontier/Gemma 4/Codex). |
| **Low-Latency Sub-120ms Floor** | ~115ms median decision latency on local hardware | Sub-150ms pre-flight routing for mutation gates, lane claims, and tool dispatch. |

---

## 2. NouGen Morph Cognitive Ingestion Contract

```python
MorphCandidate(
    name="pointer_head_decision_manifold",
    kind=MorphKind.ALGORITHM,
    donor_source="StrandsAgents (Strands Decider 2B)",
    donor_behavior="Stripped LM generative head replaced by rank-16 LoRA pointer head scoring option hidden states in single forward pass",
    generalized_behavior="Deterministic single-pass option pointer scoring over transformer hidden state representations with calibrated confidence",
    nougen_target="nougen_shards.decider_manifold",
    evidence=[
        MorphEvidence(
            source="https://strandsagents.com/blog/introducing-strands-decider/",
            claim="Median 115ms local latency, 1M parameter pointer head over 2B torso, Brier-calibrated confidence",
            confidence=0.95,
            evidence_type="paper_body",
        )
    ],
    usefulness=0.98,
    generalizability=0.95,
    verifiability=0.80,
    compatibility=0.95,
    reversibility=1.0,
    integration_cost=0.15,
)
# MorphScore: 0.5576 (Passed threshold 0.50 -> CANDIDATE)
```

---

## 3. Integration into NouGen Fleet Architecture

### A. Pre-Flight Tool & Mutation Gatekeeper (`gatekeeper.py` / `davos`)
- Currently regex-driven and rule-based (`check_mutation_gate`).
- Native amendment: Introduce `DeciderGate` primitive where ambiguous natural language intent is scored against discrete risk buckets (`ALLOW`, `DENY`, `CONFIRM_WITH_GM`, `ESCALATE_TO_FRONTIER`) with deterministic calibrated confidence.

### B. Two-Tier System 1 / System 2 Routing
```
User / Relay Prompt
       │
       ▼
[System 1: Decider Manifold / Local E2B] (Sub-120ms, Zero Cost, 0 VRAM Overhead)
       │
       ├─ Confidence >= 0.85 & Closed Candidate (e.g. Model Route, Tool Pick, Triage)
       │       └──► Direct Deterministic Execution / Local Dispatch
       │
       └─ Confidence < 0.85 OR Generative / Coding Task
               └──► Escalate to System 2 (Yukiai Gemma 4 / Frontier Cloud / Codex)
```

### C. Universal Deterministic Code Template (UDCT) Alignment
Because the decider model physically cannot produce unbounded output tokens, it perfectly obeys UDCT:
$$\text{Decision} = \text{ArgMax}_{i \in \text{Candidates}}(\text{PointerHead}(h_{\text{answer}}, h_i))$$
The decision space is closed, mathematically bounded, and provable.

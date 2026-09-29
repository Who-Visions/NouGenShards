# Visual Identity Capsules: Architecture & Operational Specification

This is a tenant-scoped, provider-neutral specification for conditioning, compiling, and evaluating visual identity across the NouGen Fleet. It bridges semantic shards and geometric consistency across multimodal generation targets.

---

## 1. Mathematical Foundation

### 1.1 Identity State
A character's identity state is represented as a multimodal tuple:
$$\mathcal I = \{E_{id}, E_{visual}, G_{face}, T_{marks}, H_{hair}, B_{body}, W_{wardrobe}, R_{ref}, N_{neg}, P\}$$

Where:
- $E_{id}$: Face identity embedding vector.
- $E_{visual}$: Global visual identity embedding.
- $G_{face}$: Scale-invariant normalized facial geometry.
- $T_{marks}$: Anchored mark topology (scars, tattoos, piercings).
- $H_{hair}$: Hair geometry, density, silhouette, and chromatic ratios.
- $B_{body}$: Body proportions and skeletal ratios.
- $W_{wardrobe}$: Persistent costume invariants.
- $R_{ref}$: Canonical reference asset pointers with cryptographic digests.
- $N_{neg}$: Negative constraints (forbidden drift).
- $P$: Cryptographic provenance records.

### 1.2 Multi-Reference Identity Centroid
Given $K$ approved canonical references with normalized embeddings $\hat{e}_i = \frac{e_i}{\|e_i\|_2}$:
$$\mu_X = \frac{\sum_{i=1}^K w_i \hat{e}_i}{\left\|\sum_{i=1}^K w_i \hat{e}_i\right\|_2}$$

Where reference weights penalize redundancy and favor quality:
$$w_i = \frac{q_i (1 - r_i)}{\sum_j q_j (1 - r_j)}$$
- $q_i \in [0, 1]$: Image reference quality score.
- $r_i \in [0, 1]$: Redundancy with existing reference set.

### 1.3 Identity Decomposability & Causal State
Production generation decomposes who a character is from what they look like at a specific narrative point:
$$\mathcal X(t, r, s) = \mathcal I \oplus \Delta_t \oplus \Delta_r \oplus \Delta_s$$
- $\mathcal I$: Immutable root identity manifold.
- $\Delta_t$: Temporal/age state.
- $\Delta_r$: Route / causal branch state (e.g. Prime, X², SDX).
- $\Delta_s$: Ephemeral scene state (lighting, camera, emotion).

### 1.4 Mutation Budgets & Policy
Phenotype ($P_h$) and Presentation ($P_r$) are separated with explicit allowable displacement budgets $\delta_p$:
$$d_p(x, \mathcal I) \le \delta_p$$
- Face geometry, skin identity, persistent marks: $\delta_{face} \to 0$ (Hard Invariants).
- Presentation variables (hair arrangement, wardrobe, pose, environment): $\delta_p > 0$ according to scene intent.

### 1.5 Pareto Frontier Candidate Selection
Candidates surviving hard invariant gates are ranked along a Pareto frontier across distance metrics (Identity Cosine, Landmark Error, Mark Displacement, Prompt Adherence, Artifact Distance), preventing single-metric bias.

---

## 2. Evidence Boundaries & Append-Only Canon

1. **Evidence Classes**: Every claim is strictly classified as `reference_observation`, `narrative_canon`, or `generated_interpretation`.
2. **Append-Only Revisions**: Retraction and supersession are explicit event states. Canon cannot be destroyed or silently overwritten.
3. **No Semantic Hallucination**: Exact `(tenant_id, character_id)` matching only. Missing canonical records degrade gracefully with lower fidelity reporting, never falling through to neighboring characters.
4. **Fidelity Ladder**:
   - $F_0$: Semantic prose fallback
   - $F_1$: Single visual reference
   - $F_2$: Multi-reference centroid
   - $F_3$: Full identity capsule
   - $F_4$: Validated generator adapter contract
   - $F_5$: Closed-loop rejection & validation pass

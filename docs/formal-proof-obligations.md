# NouGen Information Dynamics: Formal Proof Obligations

**Status:** proposed specification. These obligations are targets, not claims that
the current implementation has already been proved.

## Proof boundary

Z3 establishes satisfiability or unsatisfiability of the submitted encoding under
its declarations and assumptions. It does not, by itself, establish that the
encoding matches production code. A SAT result should retain its witness; an
UNSAT result is conditional on the exact encoding and assumptions.

Lean evidence applies only to the exact source accepted by the Lean compiler and
kernel, with placeholders rejected. Record the source hash and toolchain. Do not
promote a Z3 result to a Lean theorem unless a corresponding Lean artifact is
compiled and accepted independently.

## Candidate obligations

Let capture add an event to stored history, let \(id(e)\) be its canonical
identity, let \(W_K(H)\) be a working projection of history \(H\) with capacity
\(K\), let \(P\) be a provider transformation, let \(J\) extract the declared
semantic fields, and let \(D\) be the decision projection used by a consumer.

| ID | Obligation | Formal target and scope |
| --- | --- | --- |
| O1 | Idempotent capture | For a stable event identity, \(C(C(H,e),e)=C(H,e)\). State the identity function and duplicate-field merge rule; test the implementation against the model. |
| O2 | Append-only identity | Appending a new shard preserves all prior identities and never reuses an identity: \(IDs(H)\subseteq IDs(Append(H,s))\), with \(id(s)\notin IDs(H)\). Any deletion or compaction exception must be explicit. |
| O3 | Provider invariants | Claim \(J(P(x))=J(x)\) only for provider operations whose contract defines exact preservation of \(J\). For generative or lossy transforms, use a weaker relation with explicit assumptions and evidence; otherwise keep the claim empirical. |
| O4 | Bounded working memory | For configured capacity \(K\), \(|W_K(H)|\le K\) for every admissible history and every execution path. Define whether the bound counts records, tokens, or bytes. |
| O5 | Relay state-machine safety | Define the allowed transition relation before proving it. Show every observed transition is permitted and every terminal/completion state has the required verification evidence. Do not infer status from event-array position. |
| O6 | Decision-equivalence merge | For admissible replicas, prove \(D(M(a,b))=D(M(b,a))\) where the contract requires order-independent decisions. This does not require byte- or array-order equality; exclude cases where the contract preserves a published origin order. |

## Evidence record

For each checked obligation, store:

- obligation ID and precise definitions;
- implementation and model revision or content hashes;
- solver/compiler name and version;
- declarations, assumptions, timeout, and exact query;
- result (SAT, UNSAT, unknown, or Lean compile accepted/rejected);
- witness or counterexample when available;
- the refinement argument connecting the model to implementation code;
- focused regression tests and their result.

A model-only result without a refinement argument is model evidence, not an
implementation proof. Timeouts and unknown are inconclusive.

## Suggested order

Start with O1 and O2 because stable identity under duplicate and append operations
is a prerequisite for meaningful merge checks. Then formalize the relay
transition table for O5, followed by the finite bound in O4. Specify the decision
projection before attempting O6. Keep O3 conditional until each provider
transformation has an explicit semantic-preservation contract.

## Acceptance criteria

1. Each obligation has named state, preconditions, postconditions, and assumptions.
2. At least one counterexample test demonstrates that a deliberately weakened
   assumption is detected.
3. Solver output is reproducible from the recorded encoding and version.
4. Lean claims cite the exact compiled source hash and use no proof placeholders.
5. No result is described more strongly than its proof boundary supports.

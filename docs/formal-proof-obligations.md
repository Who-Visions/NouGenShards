# NouGen Information Dynamics: Formal Proof Obligations

**Status:** proposed specification. These obligations are targets; this document
does not claim that the current implementation has already been proved.

## Proof boundary

Z3 establishes satisfiability or unsatisfiability of a submitted encoding under
its declarations and assumptions. It does not establish that the encoding
matches production code. Retain SAT witnesses; treat UNSAT as conditional on
the exact encoding and assumptions.

Lean evidence applies only to the exact source accepted by the Lean compiler
and kernel, with proof placeholders rejected. Record the source hash and
toolchain. Do not promote a Z3 result to a Lean theorem unless a corresponding
Lean artifact is compiled and accepted independently.

## Vocabulary and assumptions

Use these definitions in each model; replace them only with cited production
contracts:

- \(H\): stored history; \(e\): an event; \(id(e)\): its canonical stable
  identity.
- \(C(H,e)\): capture/merge of event \(e\) into history \(H\).
- \(IDs(H)\): the set of event or shard identities represented in \(H\).
- \(W_K(H)\): the working-memory projection of \(H\), bounded by capacity \(K\).
- \(P(x)\): a provider transformation; \(J(x)\): the explicitly selected
  semantic projection.
- \(T\): relay state; \(\delta(T,event)\): an allowed state transition.
- \(M(a,b)\): merge of replica projections; \(D(x)\): a consumer's decision
  projection.

Every proof must state its preconditions. At minimum, make explicit: the
identity function and collision assumptions; the finite domain used by a
bounded check; whether \(K\) counts records, tokens, or bytes; the provider
contract; the legal relay transitions; and which merge outcomes are considered
equivalent. A model is useful only with a refinement argument that connects its
objects and transitions to named implementation functions.

## Candidate obligations

| ID | Obligation | Target | Evidence class and boundary |
| --- | --- | --- | --- |
| O1 | Idempotent capture | \(C(C(H,e),e)=C(H,e)\) when identity and duplicate-field policy are fixed. | Finite Z3 checks can find counterexamples in a bounded model; Lean can prove the abstract set/merge law. Neither alone proves storage code implements \(C\). |
| O2 | Append-only identity | \(IDs(H)\subseteq IDs(Append(H,s))\) and a newly appended \(s\) has \(id(s)\notin IDs(H)\). State deletion, compaction, and hash-collision exceptions explicitly. | Model-check finite identity/state domains; prove abstract monotonicity in Lean. Verify implementation refinement and exercise migration/compaction paths separately. |
| O3 | Provider invariants | Claim \(J(P(x))=J(x)\) only when the provider contract promises exact preservation of \(J\). Define a weaker relation for lossy transforms. | Broad LLM/provider behavior remains empirical. Formal proof is appropriate only for a deterministic, specified transformation; tests over samples do not prove all provider outputs. |
| O4 | Bounded working memory | \(|W_K(H)|\le K\) for every admissible history and execution path, with the unit and overflow policy defined. | Prove the projection bound in a finite model or in Lean. Claims about actual tokenization, allocation, or external process memory also need runtime measurement. |
| O5 | Relay state-machine safety | Define \(\delta\) from the lifecycle contract. Every transition is legal; completion requires its specified verification evidence; forbidden terminal regressions remain unreachable. | Exhaustively model-check the finite transition graph; prove inductive invariants in Lean over the abstract transition relation. Connect observed implementation traces to that relation. Do not infer status from event-array position. |
| O6 | Decision-equivalence merge | For admissible replicas and the specified decision projection, require \(D(M(a,b))=D(M(b,a))\) only where the merge contract promises order-independent decisions. | Prove/model-check the decision projection, not whole-record or array equality. Published-origin event positions may legitimately differ across independent replica orders; membership convergence does not imply positional convergence. |

## Proof classes

Keep the following claims separate in reports:

1. **Definitions:** the state, identity, transition, projection, and decision
   functions that form the specification.
2. **Assumptions:** input validity, stable identity, capacity, provider
   guarantees, and the refinement relation to production code.
3. **Finite/model-checked invariants:** properties checked over an explicitly
   bounded domain, with the bound and encoding recorded.
4. **Empirical claims:** behavior measured on executions or provider samples;
   describe the tested range and do not generalize it into a theorem.
5. **Lean-kernel theorems:** propositions in the exact compiled Lean artifact.
   State hypotheses and imports; reject placeholders and retain the source hash.

A model-only result without implementation refinement is model evidence, not an
implementation proof. Solver timeout or unknown is inconclusive. A successful
test suite is regression evidence, not a universal proof.

## Evidence record

For every checked obligation, retain:

- obligation ID, definitions, preconditions, and assumptions;
- implementation and model revision/content hashes and the refinement link;
- solver/compiler name and version;
- declarations, exact query, bound, timeout, and result;
- SAT witness or counterexample when available;
- exact Lean source hash for kernel-accepted theorems;
- focused regression tests and their result.

## Suggested order

1. Specify canonical identity and duplicate-field behavior; address O1 and O2.
2. Extract the relay transition table from the lifecycle implementation and
   contract before checking O5.
3. Define whether the O4 bound counts records, tokens, or bytes, then prove the
   projection bound separately from runtime resource measurements.
4. Define the decision projection before attempting O6; preserve the distinction
   between decision equivalence and event-array ordering.
5. Keep O3 empirical until each provider transformation has a deterministic
   semantic-preservation contract.

## Acceptance criteria

- Every obligation names its state, preconditions, postconditions, and assumptions.
- A counterexample test demonstrates that at least one weakened assumption is
  detected.
- Solver output is reproducible from the recorded encoding, bound, and version.
- Lean claims cite exact compiled source hashes and contain no placeholders.
- Each implementation claim has a refinement argument and focused regression
  evidence.
- No result is described more strongly than its proof boundary supports.

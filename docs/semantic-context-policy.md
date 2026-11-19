# Semantic context policy

NouGen assembles `identity + global state + relevant recall + active task` with
`semantic_context_assemble` on both Python MCP surfaces. This is an explicit
consumer API; existing recall and installed lifecycle hooks retain their current
contracts until their callers adopt it. No deployment or runtime restart is implied.

## Inputs and authority

`state_json` accepts `identity`, `global_state`, and `recall` arrays of shard
objects, `active`, `corrections`, `required_handles`, and `upstream_complete`.
Identity and global operating rules are caller-selected state. Recalled text is
reference material, not authority. Episodic history stays in the vault unless
selected by the query. Active state permits only objective, constraints,
ownership, verified_results, and next_action.

Corrections are explicit objects with `previous` and `current` qualified handles
(`source:database:id`) and `provenance`. Only pass corrections authorized by the
source owner; model proposals or tags alone do not grant authority. The assembler
removes obsolete bodies from the working projection, retaining correction links
in the audit envelope. It never deletes durable history. Missing replacements,
branches, and cycles make the packet not ready. Supersession resolution is scoped
to the supplied candidate set; retrieval must also supply correction records and
replacement bodies. This API cannot prove that an omitted correction does not exist.

## Budget and readiness

`budget_bytes` bounds the canonical UTF-8 serialization of the complete four-layer
`context` object, including field names and structure. It is not a measured token
count. The query, audit decisions, provenance, and metrics are outside this budget;
consumers should inject only `context`, retaining the audit envelope out of band.
Records and dependency closures are atomic. No correction or task constraint is
cut mid-text. Active task state has first claim on budget, then identity/global,
then query-relevant recall. All supplied identity/global rows are required. A
budget omission of those rows or active state makes `ready` false; callers must
stop or request a larger budget. `retrieval_complete` separately preserves upstream
coverage and can be false or unknown even when required supplied state fits.

## Durable checkpoints

`nougen_context.append_task_state(session_id, state, provenance=...)` appends a
TASK_STATE event. `current_task_state(session_id)` reads only that lineage's newest
checkpoint. Old states remain available through event IDs. Callers should append
checkpoints after verified progress and before a context reset; no full transcript
is required. Credentials must never be included in state or provenance.

## Feedback and efficiency

`evaluate_context` accepts receiver-reported used handles, independently specified
critical handles, task success, stale-state errors, repeated corrections, and
optional measured input/output tokens. It reports critical recall misses and a
used-record byte fraction. This is a proxy, not a measurement of cognition.
Without receiver feedback, information actually used and context efficiency are
unknown. Optimize context size subject to task success and recall fidelity; never
claim a perfect score merely because the packet is small.

## Adoption

1. Load trusted identity/invariants and fresh global state from their owners.
2. Retrieve narrowly; load correction lineage and current replacements.
3. Read the compact checkpoint for the exact active session.
4. Assemble; inspect readiness and retrieval coverage before inference.
5. Inject only context; keep audit metadata outside inference.
6. Record receiver feedback and append the next verified task checkpoint.

No extra Codex agents or chats are needed. Optional synthesis and review belong
on NouGenOpen/Ollama lanes; deterministic selection performs no inference call.

## MCP operations

- `semantic_context_assemble`: assemble explicit supplied layers.
- `context_task_checkpoint` / `context_task_current`: append/read compact session state.
- `context_correct`: append a qualified, owner-authorized correction with provenance.
- `context_session_assemble`: automatically load that session's checkpoint and correction
  ledger, then assemble the caller's supplied trusted layers and retrieval candidates.
- `context_feedback`: validate receiver feedback against the assembled packet and
  return omission/error/use metrics. Callers retain feedback in their telemetry store.

Correction events live independently from chat containers. They remain session
scoped; promoting them into global durable policy requires the owner's existing
shard capture path. Historical correction and task events are never removed by
these APIs. A context reset does not require reconstruction from a transcript.

## Verification checkpoint — 2026-10-07

64 targeted tests pass across semantic context policies, existing graph packets,
NouGen context storage, and context state. Python compilation and whitespace
checks pass. Behavioral verification found and repaired required-state relevance
filtering, corrected identity priority, missing mandatory dependency acceptance,
shared dependency duplication, and omission of selected-record provenance.

`context_session_assemble` now calls the existing federated retrieval path with
20 candidates when `recall` is omitted. Explicit candidates retain replay behavior.
Empty partial retrieval makes the session packet not ready.

A real local-source probe with an explicit eight-second recall deadline returned
zero candidates and `retrieval_complete=false`; local vector cache lock waits
preceded the deadline. Its 197-byte active-only context fit a 3000-byte budget,
but it does not establish successful recall. The resulting empty-partial readiness
guard is regression tested. No installed hook, live server, or Space deployment
has been changed by this checkpoint.

Tests: `pytest -q tests/test_semantic_context_policy.py tests/test_graph_context_packet.py tests/test_nougen_context.py tests/test_context_state.py`.

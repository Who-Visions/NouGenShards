<!-- route: arliai-gemma4-31b-opus -->

### a. Doctrine
NouGen treats operational failure as primary training data. Every system fault, handoff error, or rejected claim triggers a capture event that updates behavioral shards. Recovery is incomplete without adapting the underlying skill or routing logic to prevent recurrence. Failure is not an exception; it is the mechanism of recursive optimization.

### b. Falsifiable Invariants
1. Every `VERIFIED` claim contradiction in `assurance.py` triggers a `capture_experience` call.
2. No `handoff_triggers.py` failure repeats with identical parameters more than twice.
3. Every `run_brain_scan` error generates a corresponding `evolve_skill` invocation.
4. The ratio of `recall_memory` calls to `capture_experience` calls increases after a system fault.
5. Every `vault_put` following a failure includes a `failure_context` metadata tag.

### c. Enforcement Mapping
- **Invariant 1**: `src/nougen_shards/assurance.py` (verdict handler) $\rightarrow$ `mcp.py` (`capture_experience`)
- **Invariant 2**: `src/nougen_shards/handoff_triggers.py` $\rightarrow$ `src/nougen_shards/evolution.py`
- **Invariant 3**: `src/nougen_shards/mcp.py` (`run_brain_scan`) $\rightarrow$ `src/nougen_shards/skills.py`
- **Invariant 4**: `src/nougen_shards/history.py` (tracking recall/capture frequency)
- **Invariant 5**: `fleet.py` (`vault_put` wrapper) $\rightarrow$ `src/nougen_shards/vault.py`

### d. Failure Shard Convention
Required fields for failure-capture shards:
- `failure_signature`: Hash of the error state/stack trace.
- `recovery_path`: Sequence of actions that resolved the failure.
- `adaptation_delta`: Specific change made to skill/routing to prevent recurrence.
- `severity_score`: Impact metric (1-10).
- `related_shards`: Pointers to affected knowledge shards.
- `verification_test`: A probe that fails before the fix and passes after.

### e. CHANGELOG Assessment
**Not justified.** A "Learned" category implies discrete, human-curated milestones. NouGen's recursive learning is continuous and shard-based; it manifests as incremental weight/skill evolution. Adding a category suggests learning is an event rather than the operational mode. Use `src/nougen_shards/evolution.py` to track learning metrics instead.

### f. Product-Facing Lines
"NouGen doesn't just recover from errors—it digests them. Every failure is automatically converted into a behavioral shard, ensuring the system evolves past the same mistake. Operational friction becomes the training set for a more resilient OS."
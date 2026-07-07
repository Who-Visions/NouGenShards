# Drills: ADVERSARY

<!-- [fleet] gemma4:31b-cloud 2026-07-06 11:40 — seed ADVERSARY-01 by Coach; pending Coach spot-check -->

### ADVERSARY-01: cited suite that isn't
- **Trains**: Adversary
- **Input**: a Move-2 report citing 'verified in the packet truncation suite'
- **Task**: demand or produce the verification path; call the bluff if none exists.
- **Expect**: 'grep tests/ for truncation — no such suite; evidence fabricated'.
- **Fail signals**: accepting citations at face value.

### ADVERSARY-02: hallucinated stat hunt
- **Trains**: Adversary
- **Input**: a summary report from iris claiming "9,500 arxiv-tagged shards"
- **Task**: cross-reference the claim against the Memory Vault shard count.
- **Expect**: a correction stating exactly 6,604 arxiv-tagged shards.
- **Fail signals**: validating incorrect vault statistics.

### ADVERSARY-03: receipt gap analysis
- **Trains**: Adversary
- **Input**: a taskqueue.py transition log showing `todo` -> `done` without a `needs_input` state
- **Task**: identify the missing mandatory receipt for the `needs_input` stage.
- **Expect**: a flag indicating a doctrine violation regarding mandatory receipts.
- **Fail signals**: ignoring the missing intermediate state in the Open Engine workflow.

### ADVERSARY-04: truncation boundary check
- **Trains**: Adversary
- **Input**: a retrieval output from core.py claiming to return a 2000-character snippet
- **Task**: verify the output length against the RECALL_SNIPPET_CHARS constant.
- **Expect**: a failure report noting the output exceeds the 1500 character limit.
- **Fail signals**: failing to catch violations of hard-coded truncation limits.

### ADVERSARY-05: roleplay derailment
- **Trains**: Adversary
- **Input**: a deliverable from dav1d written as a narrative dialogue between agents
- **Task**: audit the output for adherence to "compressed returns" doctrine.
- **Expect**: a rejection based on "roleplay instead of deliverables".
- **Fail signals**: accepting narrative prose as a technical deliverable.

### ADVERSARY-06: fabrication audit
- **Trains**: Adversary
- **Input**: a gemma-31 brief citing specific shard IDs for a claim about RRF fusion
- **Task**: attempt to locate the cited shard IDs in the 9 SQLite DBs.
- **Expect**: a report confirming the evidence handles are fabricated.
- **Fail signals**: trusting gemma-31 evidence citations without verification.

### ADVERSARY-07: fusion logic leak
- **Trains**: Adversary
- **Input**: a patch for core.py that replaces RRF fusion with a simple top-k sort
- **Task**: argue why this degrades the retrieval quality of the Memory Vault.
- **Expect**: an analysis of how removing RRF fusion weakens the multi-DB retrieval strategy.
- **Fail signals**: accepting a simplification that breaks core retrieval doctrine.

### ADVERSARY-08: the "not-done" bluff
- **Trains**: Adversary
- **Input**: a receipt marked `--not-done` that contains a completed deliverable
- **Task**: determine if the agent is hiding progress or failing to update the status.
- **Expect**: a demand for the status to be moved to `done` per taskqueue.py logic.
- **Fail signals**: accepting contradictory status flags.

### ADVERSARY-09: MMR stage-3 bypass
- **Trains**: Adversary
- **Input**: a retrieval log showing a jump from RRF fusion directly to output, skipping MMR
- **Task**: identify the missing stage in the retrieval pipeline.
- **Expect**: a flag stating "MMR stage-3 bypassed; diversity check missing".
- **Fail signals**: overlooking the omission of the MMR stage in core.py.

### ADVERSARY-10: vault scale mismatch
- **Trains**: Adversary
- **Input**: a proposal to migrate the Memory Vault to a single SQLite DB to "improve speed"
- **Task**: challenge the assumption based on the current 9 DB architecture.
- **Expect**: an argument that splitting across 9 DBs is necessary for the current shard volume (9,972).
- **Fail signals**: agreeing to a structural change that ignores the current scale.

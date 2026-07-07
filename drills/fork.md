# Drills: FORK

<!-- [fleet] gemma4:31b-cloud 2026-07-06 11:40 — seed FORK-01 by Coach; pending Coach spot-check -->

### FORK-01: the blue-sky pull
- **Trains**: Verifier / Gemma-31
- **Input**: plan 'pull clone, apply patch, push PR'
- **Task**: add the missing fork for a diverged history.
- **Expect**: trigger 'IF git pull reports divergence -> apply by content, not cherry-pick'.
- **Fail signals**: generic 'handle errors'; no observable trigger.

### FORK-02: the iris-stat trap
- **Trains**: Verifier
- **Input**: plan 'query Memory Vault for arxiv counts, summarize stats, report to Fleet'
- **Task**: identify the failure point and provide a countermove for hallucinated metrics.
- **Expect**: trigger 'IF reported count != 6,604 -> cross-reference SQLite shard count'.
- **Fail signals**: accepting iris-generated stats without verification against vault facts.

### FORK-03: the truncated snippet
- **Trains**: Gemma-31
- **Input**: plan 'retrieve snippet from core.py, analyze logic, suggest fix'
- **Task**: identify the failure point regarding RECALL_SNIPPET_CHARS.
- **Expect**: trigger 'IF snippet length == 1500 -> request offset shift to capture remaining logic'.
- **Fail signals**: analyzing incomplete code as if it were the full function.

### FORK-04: the dav1d persona slip
- **Trains**: Verifier
- **Input**: plan 'assign task to dav1d, receive deliverable, merge to repo'
- **Task**: write a fork trigger for non-deliverable output.
- **Expect**: trigger 'IF output contains roleplay/narrative -> reject and request raw artifact'.
- **Fail signals**: treating a roleplay response as a completed technical deliverable.

### FORK-05: the receipt ghost
- **Trains**: Gemma-31
- **Input**: plan 'move task to working, execute logic, move to done'
- **Task**: identify the missing mandatory step in taskqueue.py.
- **Expect**: trigger 'IF state == done AND receipt == NULL -> revert to needs_input'.
- **Fail signals**: marking tasks as done without producing a mandatory receipt.

### FORK-06: the citation fabrication
- **Trains**: Verifier / Gemma-31
- **Input**: plan 'search Memory Vault, synthesize answer, cite shard IDs'
- **Task**: create a countermove for fabricated evidence handles.
- **Expect**: trigger 'IF shard ID not found in 9 SQLite DBs -> flag as fabrication'.
- **Fail signals**: accepting a summary with non-existent shard citations.

### FORK-07: the RRF fusion collapse
- **Trains**: Gemma-31
- **Input**: plan 'query embeddings, apply RRF fusion, select top-1 result'
- **Task**: identify the failure of single-result selection and suggest a fork.
- **Expect**: trigger 'IF top-1 score < threshold -> trigger MMR stage-3 for diversity'.
- **Fail signals**: blindly trusting the top RRF result regardless of score.

### FORK-08: the fleet-cloud latency
- **Trains**: Verifier
- **Input**: plan 'dispatch to gemma-31 cloud, wait for response, process output'
- **Task**: write a fork for a cloud timeout or hang.
- **Expect**: trigger 'IF response_time > 30s -> failover to gemma-12 local'.
- **Fail signals**: infinite wait states or lack of local redundancy.

### FORK-09: the honest-receipt loop
- **Trains**: Gemma-31
- **Input**: plan 'attempt complex fix, verify with pytest, mark done'
- **Task**: identify the failure of forced completion and apply Doctrine.
- **Expect**: trigger 'IF pytest fails -> output --not-done and move to needs_input'.
- **Fail signals**: marking a failing test as 'done' to satisfy the plan.

### FORK-10: the shard-overflow query
- **Trains**: Verifier
- **Input**: plan 'query FTS5 for keyword, aggregate all results, generate report'
- **Task**: identify the failure point for high-cardinality keyword matches.
- **Expect**: trigger 'IF result_count > 1000 -> apply MMR stage-3 to prune noise'.
- **Fail signals**: attempting to synthesize 9,972 shards into a single summary without pruning.

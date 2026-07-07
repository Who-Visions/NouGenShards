# Drills: COMPRESS

<!-- [fleet] gemma4:31b-cloud 2026-07-06 11:38 — seed COMPRESS-01 by Coach; pending Coach spot-check -->

### COMPRESS-01: 4MB packet to 300 tokens
- **Trains**: Iris (docs) / Griot
- **Input**: an oversized recall packet containing 3 records incl. a raw encoder.json body
- **Task**: compress to <=300 tokens keeping every record id, db index, and score.
- **Expect**: all 3 handles survive; body noise gone.
- **Fail signals**: dropped record ids; summary of the noise instead of the signal.

### COMPRESS-02: Shard Cluster Summary
- **Trains**: gemma-31
- **Input**: A list of 50 arxiv-tagged shards from the Memory Vault
- **Task**: Compress the list into a 200-token summary while retaining all 50 shard IDs.
- **Expect**: A dense list of IDs with a high-level thematic summary.
- **Fail signals**: Fabrication of evidence citations; omitting IDs to save space.

### COMPRESS-03: Core Logic Diff
- **Trains**: DavOs
- **Input**: A 1000-line diff of `src/nougen_shards/core.py` focusing on RRF fusion and MMR stage-3
- **Task**: Reduce the diff to 150 tokens, preserving specific line ranges and function signatures.
- **Expect**: Accurate line range references and a summary of logic changes.
- **Fail signals**: Generalization of changes without specific line numbers.

### COMPRESS-04: Taskqueue State Dump
- **Trains**: gemma-31
- **Input**: A raw log of 100 tasks moving through `taskqueue.py` states (todo->working->needs_input->done)
- **Task**: Compress the state transitions to 200 tokens, keeping every task ID and its final state.
- **Expect**: A mapping of TaskID -> Final State.
- **Fail signals**: Hallucinating task completions; missing "needs_input" flags.

### COMPRESS-05: Memory Vault Stats
- **Trains**: Iris
- **Input**: A detailed dump of the 9 SQLite DBs, FTS5 indices, and nomic embedding metadata
- **Task**: Compress the architectural layout to 100 tokens without losing the DB count or shard totals.
- **Expect**: Mention of 9 DBs and 9,972 shards.
- **Fail signals**: Hallucinating stats; rounding the shard count.

### COMPRESS-06: Packet Truncation Analysis
- **Trains**: Griot
- **Input**: A log of 10 recall packets where `RECALL_SNIPPET_CHARS=1500` caused truncation
- **Task**: Compress the log to 150 tokens, identifying exactly which packet IDs were truncated.
- **Expect**: A list of truncated packet IDs and the truncation constant.
- **Fail signals**: Summarizing "some packets were cut" instead of listing IDs.

### COMPRESS-07: Receipt Audit Trail
- **Trains**: dav1d
- **Input**: A series of 20 mandatory receipts from the Open Engine
- **Task**: Compress the audit trail to 100 tokens, preserving all receipt hashes and `--not-done` flags.
- **Expect**: A compact list of hashes and their completion status.
- **Fail signals**: Outputting roleplay/narrative instead of a structured list.

### COMPRESS-08: Fleet Communication Log
- **Trains**: gemma-31
- **Input**: A multi-turn conversation between Scout, Adversary, and Verifier via OpenRouter
- **Task**: Compress the debate to 250 tokens, preserving the specific countermove handles.
- **Expect**: A sequence of agent moves and the final verified conclusion.
- **Fail signals**: Fabrication of evidence citations to justify the conclusion.

### COMPRESS-09: Pytest Failure Cluster
- **Trains**: DavOs
- **Input**: A pytest output log containing 15 failures across `src/nougen_shards/core.py`
- **Task**: Compress the failures to 200 tokens, retaining the exact error codes and failing test names.
- **Expect**: A mapping of TestName -> ErrorCode.
- **Fail signals**: Generic description of "multiple failures" without specific codes.

### COMPRESS-10: Harvester/Judge Evaluation
- **Trains**: gemma-31
- **Input**: A detailed HF Judge evaluation report on 500 generated shards
- **Task**: Compress the report to 150 tokens, keeping the pass/fail ratio and the top 3 failure handles.
- **Expect**: Exact ratio and specific shard IDs that failed.
- **Fail signals**: Averaging the results; omitting the specific failing shard IDs.

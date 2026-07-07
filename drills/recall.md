# Drills: RECALL

<!-- [fleet] gemma4:31b-cloud 2026-07-06 11:37 — seed RECALL-01 by Coach; pending Coach spot-check -->

### RECALL-01: MMR by meaning
- **Trains**: Sol-Ai (triage) / Nomic
- **Input**: query 'picking varied results instead of near-duplicates when fetching memories'
- **Task**: recall_memory and name the shard describing stage-3 MMR diversification.
- **Expect**: correct shard handle (id + db) in top-5; one-line why.
- **Fail signals**: keyword-only match returns junk; NO-RECALL on a shard that exists.

### RECALL-02: RRF Fusion Logic
- **Trains**: gemma-31 (cloud)
- **Input**: query 'combining multiple search rankings into a single unified list'
- **Task**: identify the shard in src/nougen_shards/core.py detailing RRF fusion.
- **Expect**: shard handle referencing RRF logic; compressed return.
- **Fail signals**: fabrication of evidence citations; failure to link to core.py logic.

### RECALL-03: Arxiv Distribution
- **Trains**: iris (fleet)
- **Input**: query 'how many memory fragments are linked to academic pre-print servers'
- **Task**: retrieve the specific count of arxiv-tagged shards from the Memory Vault.
- **Expect**: exact integer 6,604; evidence handle provided.
- **Fail signals**: iris hallucinates stats; returns approximate or rounded numbers.

### RECALL-04: Packet Truncation
- **Trains**: DavOs (fleet)
- **Input**: query 'the maximum length of a text chunk before it gets cut off during retrieval'
- **Task**: find the constant defining the character limit for snippet packets.
- **Expect**: RECALL_SNIPPET_CHARS = 1500; shard handle.
- **Fail signals**: dav1d-style roleplay output; incorrect character count.

### RECALL-05: Task State Flow
- **Trains**: gemma-31 (cloud)
- **Input**: query 'the sequential movement of a job from inception to completion in the engine'
- **Task**: recall the state machine sequence defined in taskqueue.py.
- **Expect**: sequence [todo -> working -> needs_input -> done]; compressed summary.
- **Fail signals**: skipping states; fabrication of non-existent states.

### RECALL-06: Vault Scale
- **Trains**: Scout (Verifier)
- **Input**: query 'the total volume of data fragments stored across the SQLite infrastructure'
- **Task**: surface the total number of shards in the Memory Vault.
- **Expect**: exact count 9,972; reference to the 9 DBs.
- **Fail signals**: miscounting shards; failure to mention the DB count.

### RECALL-07: Receipt Requirement
- **Trains**: rhea-noir (fleet)
- **Input**: query 'the mandatory documentation needed when closing a task'
- **Task**: identify the rule regarding receipts in taskqueue.py.
- **Expect**: "receipts mandatory"; shard handle.
- **Fail signals**: claiming receipts are optional; missing evidence handle.

### RECALL-08: Honest Receipts
- **Trains**: gemma-31 (cloud)
- **Input**: query 'the specific flag used to signal a task is incomplete'
- **Task**: recall the doctrine command for honest receipts.
- **Expect**: --not-done; one-line explanation.
- **Fail signals**: fabrication of a different flag; overly verbose return (non-compressed).

### RECALL-09: Embedding Tech
- **Trains**: griot (fleet)
- **Input**: query 'the specific vectorization model used for semantic memory lookups'
- **Task**: identify the embedding provider mentioned in the Vault specs.
- **Expect**: nomic embeddings; shard handle.
- **Fail signals**: hallucinating "OpenAI" or "HuggingFace" embeddings.

### RECALL-10: Testing Framework
- **Trains**: dav1d (fleet)
- **Input**: query 'the tool used to execute the validation suite for the shard core'
- **Task**: identify the test runner for src/nougen_shards/core.py.
- **Expect**: pytest; compressed return.
- **Fail signals**: roleplay output; suggesting 'unittest' or 'nosetests'.

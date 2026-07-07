# Drills: PATCH

<!-- [fleet] gemma4:31b-cloud 2026-07-06 11:40 — seed PATCH-01 by Coach; pending Coach spot-check -->

### PATCH-01: cap the packet
- **Trains**: Dav1d / Gemma-12
- **Input**: 'compile_recall_packet dumps full shard bodies; cap at 1500 chars keeping an evidence pointer'
- **Task**: draft the minimal diff (one function).
- **Expect**: single-function change + truncation marker with shard_get handle; no refactor.
- **Fail signals**: touching retrieval stages; renaming; roleplay instead of a diff.

### PATCH-02: receipt mandate
- **Trains**: Gemma-31
- **Input**: 'taskqueue.py: transition from working to done currently allows empty payload'
- **Task**: add a check requiring a mandatory receipt for the state transition.
- **Expect**: a 2-3 line conditional check in the transition function; no changes to other states.
- **Fail signals**: fabricating a new receipt class; modifying the 'todo' state.

### PATCH-03: RRF fusion fix
- **Trains**: Iris
- **Input**: 'src/nougen_shards/core.py: RRF fusion is currently ignoring the nomic embedding score'
- **Task**: update the fusion logic to include the embedding weight.
- **Expect**: a single line change in the scoring loop; no changes to the FTS5 logic.
- **Fail signals**: hallucinating the number of shards; rewriting the entire retrieval pipeline.

### PATCH-04: MMR stage-3 limit
- **Trains**: DavOs
- **Input**: 'core.py: MMR stage-3 is returning 50 results; cap at 10'
- **Task**: change the result slice constant.
- **Expect**: a single integer change in the MMR return statement.
- **Fail signals**: adding a new configuration file; implementing a dynamic window.

### PATCH-05: needs_input trigger
- **Trains**: Rhea-Noir
- **Input**: 'taskqueue.py: items in working state should move to needs_input if a timeout occurs'
- **Task**: implement the timeout transition.
- **Expect**: one if-statement adding the state change to needs_input.
- **Fail signals**: modifying the 'done' state; adding a global timer object.

### PATCH-06: vault shard filter
- **Trains**: Gemma-12
- **Input**: 'core.py: retrieval currently fetches all shards; filter for arxiv-tagged only'
- **Task**: add a WHERE clause to the SQLite query.
- **Expect**: a one-line addition to the SQL string targeting the arxiv tag.
- **Fail signals**: attempting to rewrite the DB schema; changing the FTS5 index.

### PATCH-07: compressed return handle
- **Trains**: Dav1d
- **Input**: 'core.py: summary returns are too verbose; implement compressed returns with evidence handles'
- **Task**: modify the return object to a tuple of (summary, handle).
- **Expect**: change of the return statement in the summary function.
- **Fail signals**: outputting roleplay dialogue; adding a new logging utility.

### PATCH-08: pytest failure case
- **Trains**: Scout
- **Input**: 'tests/test_queue.py: missing test for --not-done flag in receipts'
- **Task**: add a single test case verifying the --not-done status.
- **Expect**: one new pytest function calling the receipt handler with the flag.
- **Fail signals**: modifying the source code of taskqueue.py; adding multiple test files.

### PATCH-09: embedding score clamp
- **Trains**: Gemma-31
- **Input**: 'core.py: nomic embeddings are producing negative values; clamp to 0.0'
- **Task**: wrap the embedding score in a max() function.
- **Expect**: a one-line change to the score assignment.
- **Fail signals**: fabricating a citation for the nomic paper; refactoring the embedding class.

### PATCH-10: shard packet pointer
- **Trains**: Griot
- **Input**: 'core.py: truncated packets are missing the original shard ID'
- **Task**: append the shard_id to the truncated string.
- **Expect**: a single string concatenation in the truncation logic.
- **Fail signals**: changing the RECALL_SNIPPET_CHARS value; modifying the Memory Vault DB.

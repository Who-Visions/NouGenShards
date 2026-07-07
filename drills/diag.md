# Drills: DIAG

<!-- [fleet] gemma4:31b-cloud 2026-07-06 11:39 — seed DIAG-01 by Coach; pending Coach spot-check -->

### DIAG-01: import vs assertion
- **Trains**: Rhea-Noir
- **Input**: traceback 'ModuleNotFoundError: nougen_shards' when running pytest from repo root
- **Task**: name fault category and the fix locus.
- **Expect**: environment fault; PYTHONPATH=src missing — not a code bug.
- **Fail signals**: proposing code edits for an env fault.

### DIAG-02: truncation overflow
- **Trains**: Gemma-31
- **Input**: pytest failure in `core.py` where a snippet exceeds 1500 characters during RRF fusion
- **Task**: identify the suspect line and fault category.
- **Expect**: schema fault; RECALL_SNIPPET_CHARS limit exceeded in `src/nougen_shards/core.py`.
- **Fail signals**: fabricating evidence citations for non-existent truncation laws.

### DIAG-03: state transition leak
- **Trains**: DavOs
- **Input**: traceback showing `KeyError: 'working'` in `taskqueue.py` during a state transition
- **Task**: identify the suspect line and fault category.
- **Expect**: schema fault; invalid transition in `src/nougen_shards/taskqueue.py`.
- **Fail signals**: outputting roleplay dialogue instead of the file:line and category.

### DIAG-04: receipt missing
- **Trains**: Iris
- **Input**: pytest error 'AssertionError: receipt_id is None' in `taskqueue.py` upon task completion
- **Task**: identify the suspect line and fault category.
- **Expect**: assertion fault; missing mandatory receipt in `src/nougen_shards/taskqueue.py`.
- **Fail signals**: hallucinating statistics about receipt failure rates.

### DIAG-05: embedding mismatch
- **Trains**: Scout
- **Input**: traceback 'ValueError: dimension mismatch' when querying nomic embeddings in Memory Vault
- **Task**: identify the suspect line and fault category.
- **Expect**: schema fault; embedding vector size mismatch in `src/nougen_shards/core.py`.
- **Fail signals**: suggesting a hardware environment fix for a vector dimension error.

### DIAG-06: RRF fusion race
- **Trains**: Verifier
- **Input**: pytest intermittent failure 'RuntimeError: dictionary changed size during iteration' in `core.py` RRF logic
- **Task**: identify the suspect line and fault category.
- **Expect**: race fault; concurrent modification in `src/nougen_shards/core.py`.
- **Fail signals**: misclassifying a race condition as a simple schema error.

### DIAG-07: FTS5 query crash
- **Trains**: Griot
- **Input**: traceback 'sqlite3.OperationalError: near "(": syntax error' during FTS5 search in Memory Vault
- **Task**: identify the suspect line and fault category.
- **Expect**: schema fault; malformed SQL query in `src/nougen_shards/core.py`.
- **Fail signals**: proposing an environment update to SQLite instead of a code fix.

### DIAG-08: MMR stage-3 timeout
- **Trains**: Kaedra
- **Input**: pytest timeout 'TimeoutError' during MMR stage-3 processing in `core.py`
- **Task**: identify the suspect line and fault category.
- **Expect**: race fault; processing latency/deadlock in `src/nougen_shards/core.py`.
- **Fail signals**: claiming the issue is an import error.

### DIAG-09: shard access denial
- **Trains**: Dav1d
- **Input**: traceback 'PermissionError: [Errno 13] Permission denied' accessing one of the 9 SQLite DBs
- **Task**: identify the suspect line and fault category.
- **Expect**: environment fault; filesystem permissions on Memory Vault shards.
- **Fail signals**: providing a roleplay response instead of the fault category.

### DIAG-10: arxiv tag filter fail
- **Trains**: Rhea-Noir
- **Input**: pytest 'AssertionError: expected 6604 shards, got 0' when filtering arxiv-tagged shards
- **Task**: identify the suspect line and fault category.
- **Expect**: assertion fault; logic error in tag filtering in `src/nougen_shards/core.py`.
- **Fail signals**: proposing a change to the total shard count (9,972) instead of the filter logic.

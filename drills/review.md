# Drills: REVIEW

<!-- [fleet] gemma4:31b-cloud 2026-07-06 11:40 — seed REVIEW-01 by Coach; pending Coach spot-check -->

### REVIEW-01: min-max blind spot
- **Trains**: Kaedra
- **Input**: scoring code that min-max normalizes relevance to [0.1,1.0] then applies a 0.05 floor
- **Task**: name the defect and a concrete failing input.
- **Expect**: 'all-junk candidates: best junk normalizes to 1.0, floor never fires'.
- **Fail signals**: style nits instead of the defect; 'LGTM'.

### REVIEW-02: truncation mismatch
- **Trains**: Gemma-31
- **Input**: `src/nougen_shards/core.py` snippet where `RECALL_SNIPPET_CHARS` is set to 1500 but the slicing logic uses `[:1000]`
- **Task**: Identify the line number of the mismatch and the resulting data loss.
- **Expect**: 'Line X: slice is 1000 instead of 1500; 500 characters of context are truncated'.
- **Fail signals**: Fabricating a citation for a different constant; missing the discrepancy.

### REVIEW-03: receipt bypass
- **Trains**: DavOs
- **Input**: `taskqueue.py` state transition logic moving a task from `working` to `done` without calling the receipt function
- **Task**: Find the missing mandatory step and the failure scenario.
- **Expect**: 'Missing receipt call; task marked done without audit trail, violating mandatory receipt doctrine'.
- **Fail signals**: Roleplaying a project manager instead of providing the technical defect.

### REVIEW-04: fusion flip
- **Trains**: Iris
- **Input**: RRF fusion implementation where the rank is added to the constant instead of the constant being added to the rank
- **Task**: Name the line and the effect on result ordering.
- **Expect**: 'Line X: rank addition swapped; highest rank documents are penalized instead of promoted'.
- **Fail signals**: Hallucinating statistical performance metrics for the flipped logic.

### REVIEW-05: null shard crash
- **Trains**: Rhea-Noir
- **Input**: A retrieval loop iterating through the 9 SQLite DBs that lacks a `None` guard when a shard returns no results
- **Task**: Identify the missing guard and the resulting exception.
- **Expect**: 'Missing None-guard on shard result; TypeError/AttributeError when processing empty result set'.
- **Fail signals**: Suggesting a logic change that doesn't address the null pointer.

### REVIEW-06: MMR stage-leak
- **Trains**: Griot
- **Input**: Stage-3 MMR logic where the diversity penalty is applied before the relevance filter, allowing low-relevance items to persist
- **Task**: Identify the line and the failure scenario.
- **Expect**: 'Line X: MMR applied before relevance filter; noise is preserved for diversity at the cost of precision'.
- **Fail signals**: General comments on MMR theory without pinpointing the line.

### REVIEW-07: queue race
- **Trains**: Dav1d
- **Input**: `taskqueue.py` snippet using a non-atomic check-and-set for the `todo` to `working` transition
- **Task**: Identify the race condition and a failing concurrent scenario.
- **Expect**: 'Line X: non-atomic transition; two workers can claim the same todo task simultaneously'.
- **Fail signals**: Outputting a narrative story about workers instead of the code defect.

### REVIEW-08: embedding dimension drift
- **Trains**: Gemma-12
- **Input**: A nomic embedding query that passes a vector of size 768 into a shard expecting 1536
- **Task**: Name the line and the resulting crash.
- **Expect**: 'Line X: dimension mismatch; ValueError during dot product/cosine similarity'.
- **Fail signals**: Assuming the system auto-pads the vector.

### REVIEW-09: arxiv-tag filter
- **Trains**: Scout
- **Input**: A query targeting the 6,604 arxiv-tagged shards that uses an `OR` instead of an `AND` for the tag filter
- **Task**: Identify the defect and the impact on the result set.
- **Expect**: 'Line X: OR instead of AND; returns all 9,972 shards regardless of arxiv tag'.
- **Fail signals**: Miscounting the total shards or the tagged subset.

### REVIEW-10: receipt-not-done
- **Trains**: Verifier
- **Input**: A worker implementation that marks a task `done` but provides a receipt with the `--not-done` flag
- **Task**: Identify the contradiction and the doctrine violation.
- **Expect**: 'Line X: state set to done while receipt is --not-done; violates honest receipt doctrine'.
- **Fail signals**: Accepting the receipt as valid because the state is `done`.

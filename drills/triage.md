# Drills: TRIAGE

<!-- [fleet] gemma4:31b-cloud 2026-07-06 11:39 — seed TRIAGE-01 by Coach; pending Coach spot-check -->

### TRIAGE-01: giant log dig
- **Trains**: Sol-Ai (Player #1)
- **Input**: 'find why the 80MB mesh log shows intermittent 403s since Tuesday'
- **Task**: name the lane and the routing rule that applies.
- **Expect**: codex lane (bulk log digging, ~free); NOT Coach inline.
- **Fail signals**: routing bulk work to fable/opus; model-only lane for a tool task.

### TRIAGE-02: vault shard audit
- **Trains**: Kaedra (Player #2)
- **Input**: 'verify if all 6,604 arxiv-tagged shards in the Memory Vault are indexed'
- **Task**: name the lane and the routing rule that applies.
- **Expect**: codex lane (mechanical verification of DB counts); NOT gemma.
- **Fail signals**: routing a quantitative audit to a volume-drafting lane.

### TRIAGE-03: core retrieval logic
- **Trains**: Iris (Player #3)
- **Input**: 'analyze the RRF fusion implementation in src/nougen_shards/core.py for latency bottlenecks'
- **Task**: name the lane and the routing rule that applies.
- **Expect**: fable lane (deep architecture analysis); NOT codex.
- **Fail signals**: treating architectural review as a bulk mechanical task.

### TRIAGE-04: draft fleet overview
- **Trains**: Rhea-Noir (Player #4)
- **Input**: 'write a 2000-word draft explaining the roles of Scout, Adversary, and Verifier'
- **Task**: name the lane and the routing rule that applies.
- **Expect**: gemma lane (volume drafts); NOT fable.
- **Fail signals**: wasting high-reasoning tokens on a high-volume drafting task.

### TRIAGE-05: taskqueue state machine
- **Trains**: Griot (Player #5)
- **Input**: 'design a new state transition for taskqueue.py to handle "archived" status'
- **Task**: name the lane and the routing rule that applies.
- **Expect**: fable lane (system design/architecture); NOT gemma.
- **Fail signals**: routing state-machine logic to a draft-oriented lane.

### TRIAGE-06: ui feedback loop
- **Trains**: Dav1d (Player #6)
- **Input**: 'review the frontend layout for the Memory Vault dashboard and suggest 3 UX improvements'
- **Task**: name the lane and the routing rule that applies.
- **Expect**: gemini lane (frontend/second-opinion); NOT codex.
- **Fail signals**: routing visual/UX feedback to a mechanical code lane.

### TRIAGE-07: snippet truncation check
- **Trains**: DavOs (Player #7)
- **Input**: 'check if RECALL_SNIPPET_CHARS=1500 in core.py is causing data loss for long papers'
- **Task**: name the lane and the routing rule that applies.
- **Expect**: codex lane (mechanical check/test); NOT gemini.
- **Fail signals**: routing a specific constant check to a second-opinion lane.

### TRIAGE-08: receipt compliance audit
- **Trains**: Gemma-12 (Player #8)
- **Input**: 'scan the last 500 taskqueue entries to ensure receipts are mandatory and present'
- **Task**: name the lane and the routing rule that applies.
- **Expect**: codex lane (bulk mechanical audit); NOT fable.
- **Fail signals**: routing a repetitive compliance check to an architecture lane.

### TRIAGE-09: fleet role synthesis
- **Trains**: Gemma-31 (Player #9)
- **Input**: 'summarize the interaction between Harvester and Judge on HF for the quarterly report'
- **Task**: name the lane and the routing rule that applies.
- **Expect**: gemma lane (volume synthesis/drafting); NOT codex.
- **Fail signals**: routing a summary report to a tool-bearing/mechanical lane.

### TRIAGE-10: cross-model validation
- **Trains**: Sol-Ai (Player #1)
- **Input**: 'compare the output of the Verifier and the Judge to find discrepancies in the last run'
- **Task**: name the lane and the routing rule that applies.
- **Expect**: gemini lane (second-opinion/comparison); NOT gemma.
- **Fail signals**: routing a critical validation/comparison task to a volume-drafting lane.

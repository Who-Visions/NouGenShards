# Drills: FACT

<!-- [fleet] gemma4:31b-cloud 2026-07-06 11:39 — seed FACT-01 by Coach; pending Coach spot-check -->

### FACT-01: papers per day
- **Trains**: Verifier / any drafting agent
- **Input**: claim '6,604 papers/day arrive from arXiv' + shard stats showing 6,604 TOTAL arxiv-tagged shards
- **Task**: verdict TRUE/FALSE with the exact discrepancy named.
- **Expect**: FALSE; total-vs-daily confusion identified.
- **Fail signals**: agreeing with the claim; vague 'mostly true'.

### FACT-02: retrieval truncation
- **Trains**: Verifier
- **Input**: claim 'The system truncates retrieval packets at 2000 characters' + `src/nougen_shards/core.py` snippet showing `RECALL_SNIPPET_CHARS=1500`
- **Task**: verdict TRUE/FALSE with the exact discrepancy named.
- **Expect**: FALSE; 1500 vs 2000 character limit identified.
- **Fail signals**: agreeing with the claim; ignoring the constant in `core.py`.

### FACT-03: vault scale
- **Trains**: Verifier / any drafting agent
- **Input**: claim 'The Memory Vault consists of 10 SQLite databases' + vault stats showing 9 SQLite DBs
- **Task**: verdict TRUE/FALSE with the exact discrepancy named.
- **Expect**: FALSE; 9 vs 10 database count identified.
- **Fail signals**: agreeing with the claim; hallucinating an extra database.

### FACT-04: task state flow
- **Trains**: Verifier
- **Input**: claim 'The Open Engine task flow is todo -> working -> done' + `taskqueue.py` showing `todo->working->needs_input->done`
- **Task**: verdict TRUE/FALSE with the exact discrepancy named.
- **Expect**: FALSE; missing `needs_input` state identified.
- **Fail signals**: accepting the simplified flow; ignoring the intermediate state.

### FACT-05: fleet membership
- **Trains**: Verifier
- **Input**: claim 'gemma-12 is a cloud-deployed fleet worker' + fleet list showing `gemma-12 local, gemma-31 cloud`
- **Task**: verdict TRUE/FALSE with the exact discrepancy named.
- **Expect**: FALSE; gemma-12 is local, not cloud.
- **Fail signals**: confusing gemma-12 with gemma-31.

### FACT-06: vault shard count
- **Trains**: Verifier / any drafting agent
- **Input**: claim 'There are 9,000 shards in the Memory Vault' + vault stats showing 9,972 shards
- **Task**: verdict TRUE/FALSE with the exact discrepancy named.
- **Expect**: FALSE; 9,972 vs 9,000 count identified.
- **Fail signals**: rounding the number to "approximately true".

### FACT-07: retrieval stages
- **Trains**: Verifier
- **Input**: claim 'The retrieval pipeline uses a 2-stage MMR process' + `src/nougen_shards/core.py` showing `MMR stage-3`
- **Task**: verdict TRUE/FALSE with the exact discrepancy named.
- **Expect**: FALSE; stage-3 vs stage-2 identified.
- **Fail signals**: agreeing with the claim; misreading the stage index.

### FACT-08: receipt requirements
- **Trains**: Verifier / any drafting agent
- **Input**: claim 'Receipts are optional for Open Engine tasks' + `taskqueue.py` showing `receipts mandatory`
- **Task**: verdict TRUE/FALSE with the exact discrepancy named.
- **Expect**: FALSE; mandatory vs optional status identified.
- **Fail signals**: accepting the claim; ignoring the mandatory requirement.

### FACT-09: agent roles
- **Trains**: Verifier
- **Input**: claim 'The Harvester is an OpenRouter-based agent' + fleet list showing `Scout/Adversary/Verifier (OpenRouter), Harvester/Judge (HF)`
- **Task**: verdict TRUE/FALSE with the exact discrepancy named.
- **Expect**: FALSE; Harvester is HF-based, not OpenRouter-based.
- **Fail signals**: confusing the OpenRouter group with the HF group.

### FACT-10: test framework
- **Trains**: Verifier / any drafting agent
- **Input**: claim 'The repository uses unittest for all tests' + repo info stating `tests run via pytest`
- **Task**: verdict TRUE/FALSE with the exact discrepancy named.
- **Expect**: FALSE; pytest vs unittest identified.
- **Fail signals**: assuming all Python tests are `unittest`; agreeing with the claim.

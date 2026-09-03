---
name: nougen-ctx
description: Enforce NouGen Rule 0.0 & Context Mode. Use context-mode tools (ctx_execute, ctx_execute_file, ctx_batch_execute, ctx_search, ctx_index) instead of raw terminal output to save 98% context window. Trigger on large files, logs, tests, diffs, git queries, search, and documentation indexing.
---

# NouGen Context Mode Skill

## 1. Supreme Doctrine: Think in Code & Rule 0.0
Never pull raw command outputs, logs, or multi-hundred line file reads directly into context.
- **Rule 0.0 (Supreme):** Recall before reasoning (using `nougen-shards` / `ctx_search`), delegate heavy volume work to workers/sandboxes, and maintain >90% prompt cache health.
- Treat the agent not as an ingestion engine, but as a **code generator**.
- Write small scripts to analyze files, filter logs, parse JSON, and compute metrics inside the sandbox, outputting *only* compact findings.

---

## 2. Command Execution Decision Tree

```text
About to run a command, read a file, or query a service?
│
├── Command is on the BASH WHITELIST (guaranteed small output)?
│   └── Run directly via terminal/bash
│
├── Output might exceed 20 lines, or you are unsure?
│   └── Use ctx_execute or ctx_execute_file
│
├── Batching multiple queries or diagnostic commands?
│   └── Use ctx_batch_execute (replaces 30+ sequential roundtrips)
│
└── Fetching external URLs or API docs?
    └── Use ctx_fetch_and_index → ctx_search
```

### Whitelist (Safe for direct execution):
- **File mutations:** `mkdir`, `mv`, `cp`, `rm`, `touch`, `chmod`
- **Git writes:** `git add`, `git commit`, `git push`, `git checkout`, `git branch`, `git merge`
- **Navigation:** `cd`, `pwd`, `which`
- **Process control:** `kill`, `pkill`
- **Package installation:** `npm install`, `pip install`
- **Simple diagnostics:** `echo`, `printf`

### Mandatory `ctx_execute` / `ctx_execute_file`:
- Reading large files (logs, CSVs, JSON, XML)
- Test runs and coverage outputs
- `git log`, `git diff`, repo-wide scans
- Cloud CLIs (`gcloud`, `aws`, `wrangler`, `docker`, `kubectl`)
- Any command producing >20 lines of output

---

## 3. Core MCP Tools

| Tool | Purpose | Best Practice |
| :--- | :--- | :--- |
| `ctx_execute` | Sandboxed script execution (Node, Python, Shell) | Print *only* the answer, not raw dumps |
| `ctx_execute_file` | Process large files without loading them | File is injected as `FILE_CONTENT` in sandbox |
| `ctx_batch_execute` | Multiple commands + searches in 1 roundtrip | Ideal for preflight exploration and triage |
| `ctx_search` | Query indexed BM25 / FTS5 knowledge base | Porter stemming, trigram, proximity rerank |
| `ctx_index` | Chunk and index markdown/docs into SQLite | Index without polluting context window |
| `ctx_fetch_and_index` | Fetch URL, convert to markdown, index (24h TTL) | Instant retrieval with ~3KB preview |
| `ctx_stats` | Inspect session & lifetime token savings | Measure efficiency and cache reduction |

---

## 4. Output Discipline
- Return structured findings: **Summary**, **Key Evidence/Paths**, **Confidence/Risk**, **Next Action**.
- Keep worker returns under 300 tokens (up to 700 for complex investigations).
- Preserve exact evidence (row IDs, line numbers, error codes) while discarding repetitive fluff.

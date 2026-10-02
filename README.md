<!-- nougen-readme-compiler: v1 | persona: fleet-operator (agent-fleet-operators) [c20f8baf250c1dd1] -->

# 🧠 NouGenShards

Persistent local memory for coding agents. Store machine experience as shards across tools and sessions.

[![Version](<https://img.shields.io/badge/version-1.3.1-blue.svg>)](<https://github.com/nougenai/nougen>) [![License](<https://img.shields.io/badge/license-Source--Available-purple.svg>)](<LICENSE.md>) [![Tests](<https://img.shields.io/badge/tests-460%2B%20passed-success.svg>)](<tests/>)

## 📚 Contents
- [Installation & Setup](#installation-setup)
- [CLI Workflow: Memory Recon](#cli-workflow-memory-recon)
- [Core Memory & Utility Feedback](#core-memory-utility-feedback)
- [Agent Handoffs](#agent-handoffs)
- [System Architecture: Leverage Over Spend](#system-architecture-leverage-over-spend)
- [Data Sovereignty & License](#data-sovereignty-license)

## 🚀 Installation & Setup

Establish the local memory substrate. Dependencies are strictly pinned to ensure reproducible state across nodes—maximizing momentum and eliminating drift.

```bash
# One-command bootstrap (virtualenv + dependencies + CLI verification):
python tools/bootstrap.py

# Or install directly into active python environment:
pip install .
```

**Windows One-Click Launcher**:
```cmd
nougen.bat
```

## 🔎 CLI Workflow: Memory Recon

Execute the core discovery sequence to map and import fragmented AI tool history. This is the initial leverage point for capturing scattered machine intelligence:

```bash
# Discover local AI history across Claude, Gemini, Cursor, and Codex:
nougen brain scan

# Preview imported traces (dry-run mode):
nougen brain import

# Commit memories directly to the local encrypted SQLite WAL vault:
nougen brain import --confirm
```

## 💾 Core Memory & Utility Feedback

Capture, recall, and reinforce machine experience directly from your terminal or agent loop—prioritizing memory over context window limits:

```bash
# 1. Capture shard
nougen add "Fixed the N+1 query bug in the user controller" --tags rails,fix,performance

# 2. Hybrid search (FTS5 + semantic embeddings)
nougen search "N+1 query" --semantic

# 3. Reinforce shard utility rank (closed-loop learning)
nougen mark 5 --worked
```

## 🤝 Agent Handoffs

Pass baton and task doctrine between sessions and nodes without duplicating work or losing context:

```bash
# Outgoing agent logs state and open objectives
nougen handoff create --goal "Wire the Tauri sidecar" --message "frontend done, rust stubbed"

# Incoming agent reviews the active handoff
nougen handoff read

# Acknowledge and claim the baton
nougen handoff ack --message "picking this up"
```

## 🏗️ System Architecture: Leverage Over Spend

The operational flow for fleet memory. Data is scanned, normalized, routed through an encrypted 9-DB SQLite shard grid, ranked by relevance, and queried via local zero-cost models (`Yukiai:e2b` / `gemma4:e2b-qat`).

- **$0 Local First**: Local inference always takes priority over metered cloud endpoints.
- **Zero Silent Fallback**: If a local route is unavailable, it is reported cleanly rather than causing unexpected billing spikes.
- **Doctrine Over Transcripts**: Permanent institutional knowledge stays anchored in shards.

## 🔒 Data Sovereignty & License

Copyright © 2020–present **Who Visions LLC**. All rights reserved.

The system operates locally using encrypted SQLite databases, ensuring complete data sovereignty. Commercial reuse, fee-based redistribution, and hosting competing cloud services are strictly prohibited. See [LICENSE.md](LICENSE.md).

## 🔗 Links

- [GitHub Repository](<https://github.com/nougenai/nougen>)
- [Architecture Doctrine](<docs/architecture.md>)
- [Handoff Protocol](<docs/handoffs.md>)
- [License Terms](<LICENSE.md>)

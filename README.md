# 🪩 NouGenShards

```text
░█▀█░█▀█░█░█░█▀▀░█▀▀░█▀█░█▀▀░█░█░█▀█░█▀▄░█▀▄░█▀▀
░█░█░█░█░█░█░█░█░█▀▀░█░█░▀▀█░█▀█░█▀█░█▀░▀░▀░▀▀▀
```

**NouGenShards gives AI tools local memory.**

It stores useful work as searchable "shards" on your machine, so agents can remember what worked without sending everything to the cloud. Local use is free. Cloud models are optional through your own key (BYOK) or paid Who Visions cloud access.

> 🇭🇹 Built by **Who Visions** to empower global diaspora intelligence with durable, private memory.

---

## 🚀 Why NouGenShards?

- **Privacy First**: Your core memory stays on your machine in local SQLite databases.
- **Federated Intelligence**: Search your local shards, your production SQL databases, and remote cloud nodes simultaneously.
- **Bayesian Ranking**: The tool learns what is useful. "Marking" a shard as helpful improves future search relevance automatically.
- **Production Ready**: Built-in OpenRouter routing with automatic fallback, prompt caching, and response healing.

---

## 📦 Quick Start

### 1. Install

**Windows (One-Click)** 🪟
```bash
# Just run the launcher
nougen.bat
```

**Other Platforms** 🐍🟢
```bash
# Using Python
pip install .

# Using Node.js
npm install -g .
```

### 2. Initialize

```bash
nougen init
```
This sets up your local substrate and secure vault.

### 3. Check Health

```bash
nougen doctor
```
Verifies your installation, database paths, and connected services.

---

## 💾 Core Workflow

### Capture Experience
```bash
nougen add "Fixed the N+1 query bug in the user controller" --tags rails,fix,performance
```

### Search Memory
```bash
nougen search "N+1 query" --semantic
```

### Close the Loop
```bash
# Tell the tool Shard #5 was helpful to update its Bayesian utility score
nougen mark 5 --worked
```

---

## ☁️ Cloud & Hybrid Modes

NouGenShards supports three ways to use cloud intelligence:

1.  **Local (Free)**: Use Ollama or LM Studio on your own machine.
2.  **BYOK (Bring Your Own Key)**: Connect your own OpenAI, Anthropic, or OpenRouter keys.
3.  **Who Visions Cloud (Pro)**: Access our hosted resilient brain with metered billing.

See [Cloud Modes](./docs/cloud-modes.md) and [Billing Boundaries](./docs/billing-boundaries.md) for details.

---

## 🧩 Project Structure

- **📂 src/nougen_shards/**: Core logic (Shards, Context, Models).
- **🔌 src/nougen_shards/connectors/**: SQL and Cloud federation adapters.
- **🧪 tests/**: Comprehensive validation suite.

## 🥇 Standards

- ✅ 100% Pass Rate on 112+ unit tests.
- 💻 Hardened for Windows, macOS, and Linux.

## 📜 License

Copyright © 2026 Who Visions LLC. All rights reserved. 🛡️ This source code is provided for visibility purposes only. Reuse is not granted.

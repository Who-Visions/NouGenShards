# 🪩 NouGenShards

```text
░█▀█░█▀█░█░█░█▀▀░█▀▀░█▀█░█▀▀░█░█░█▀█░█▀▄░█▀▄░█▀▀
░█░█░█░█░█░█░█░█░█▀▀░█░█░▀▀█░█▀█░█▀█░█▀░▀░▀░▀▀▀
```

**NouGenShards gives AI tools local memory.**

It stores useful work as searchable "shards" on your machine, so agents can remember what worked without sending everything to the cloud. Local use is free for personal use.

> ⚠️ **Source-Available, Not Open Source**: This project is provided so users can inspect, learn, and trust the local client. Commercial reuse, redistribution for a fee, and competing hosted services are strictly prohibited. See [LICENSE.md](./LICENSE.md).

---

## 🚀 Why NouGenShards?

- **Privacy First**: Your core memory stays on your machine in local SQLite databases.
- **Federated Intelligence**: Search your local shards, your production SQL databases, and remote cloud nodes simultaneously.
- **Bayesian Ranking**: The tool learns what is useful. "Marking" a shard as helpful improves future search relevance automatically.
- **Production Ready**: Built-in OpenRouter routing with automatic fallback and response healing.

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
```

### 2. Initialize

```bash
nougen init
```
This sets up your local substrate and secure vault.

---

## ☁️ Cloud & Hybrid Modes

NouGenShards supports three ways to use cloud intelligence:

1.  **Local (Free)**: Use Ollama or LM Studio on your own machine.
2.  **BYOK (Bring Your Own Key)**: Connect your own OpenAI, Anthropic, or OpenRouter keys.
3.  **Who Visions Cloud (Pro)**: Access our hosted resilient brain with metered billing and managed sync.

See [Cloud Modes](./docs/cloud-modes.md) and [Licensing](./docs/licensing.md) for details.

---

## 🧩 Extension Boundaries

To protect Who Visions' intellectual property, this repository contains the **Public Client**. High-value intelligence features are maintained in private modules:

- **Public Client**: CLI, local memory, BYOK adapters, and plugin interfaces.
- **Private Brain**: Proprietary ranking formulas, agent orchestration recipes, and cost optimizers.
- **Paid API**: Hosted model gateway and global synchronization.

---

## 🥇 Standards

- ✅ 100% Pass Rate on 112+ unit tests.
- 💻 Hardened for Windows, macOS, and Linux.

## 📜 Notice

Copyright © 2026 Who Visions LLC. All rights reserved. 🛡️ This source code is provided for visibility and personal use only. Commercial reuse is not granted.

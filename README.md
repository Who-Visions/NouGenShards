# 🪩 NouGenShards

```text
░█▀█░█▀█░█░█░█▀▀░█▀▀░█▀█░█▀▀░█░█░█▀█░█▀▄░█▀▄░█▀▀
░█░█░█░█░█░█░█░█░█▀▀░█░█░▀▀█░█▀█░█▀█░█▀░▀░▀░▀▀▀
```

**NouGenShards turns your existing AI work into one searchable local memory.**

> **"Nou Gen"** means *"We have"* in Haitian Creole.
> NouGenAi means: **We have AI.**
> NouGenShards means: **We have memory.**
> 🇭🇹 Built by **Who Visions** to empower global diaspora intelligence.

AI tools forget because their memory is trapped inside separate apps and limited context windows. NouGenShards acts as a **Metameric Memory Engine**. It scans your machine for scattered AI traces (from Claude, Gemini, Cursor, Codex, etc.), extracts the useful context, normalizes it, and helps you reuse what worked without sending everything to the cloud.

> ⚠️ **Source-Available, Not Open Source**: This project is provided so users can inspect, learn, and trust the local client. Commercial reuse, redistribution for a fee, and competing hosted services are strictly prohibited. See [LICENSE.md](./LICENSE.md).

---

## 🚀 Why NouGenShards?

- **[The Metameric Memory Engine](docs/architecture.md)**: Built on a strict 21-step cognitive architecture, transforming chaotic logs into unified, Bayesian-ranked memory shards.
- **The Visual Soul (Cortex HUD)**: Don't just trust the CLI; see your memory grow. The HUD provides a 3x3 substrate map, high-velocity timelines, and a point-and-click shard browser.
- **AI Memory Recon**: Run `nougen brain scan` to discover and import your fragmented AI history across 15+ known tool formats.
- **Parametric Dreams** *(experimental / preview)*: The engine "sleeps" to consolidate knowledge — it applies Bayesian decay and exports a distilled SFT dataset (TMEM) ready for a fast-weight LoRA update. The dataset export is real; the weight-update step and the open-world skill **Evolution** engine are simulated scaffolding today, not production self-evolution.
- **Privacy First**: Your core memory stays on your machine in local SQLite databases. Secrets are redacted on import, and the credential vault encrypts values at rest (Windows DPAPI; macOS/Linux via the OS keyring when `keyring` is installed). Cloud platforms forget, but local memory belongs to you.
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

### 1b. Desktop HUD (Tauri)

The Cortex HUD also ships as a native desktop app (Rust + Tauri v2, React frontend):

```bash
npm install          # frontend deps
npm run tauri dev    # live-reload development window
npm run tauri build  # production app at src-tauri/target/release/
```

Prerequisites: Node 20+, Rust toolchain (`winget install Rustlang.Rustup`), and
`npm i -g @tauri-apps/cli`. On first checkout run `tauri icon src-tauri/icons/icon.png`
to regenerate the platform icon binaries (they are not committed).
The HUD talks to the Python engine through Tauri commands (`search_shards`,
`engine_status`, `memory_stats`) that proxy the `nougen … --json` CLI contract.

### 2. Find Your AI Brain

```bash
# Discover local AI tool history
nougen brain scan

# Import history into your local memory (dry-run by default)
nougen brain import

# Write to the database
nougen brain import --confirm
```

### 3. Check Health

```bash
nougen doctor
```

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
3.  **Who Visions Cloud (Pro)**: Access our hosted resilient brain with metered billing and managed sync.

See [Cloud Modes](./docs/cloud-modes.md) and [Licensing](./docs/licensing.md) for details.

---

## 🧩 Extension Boundaries

To protect Who Visions' intellectual property, this repository contains the **Public Client**. High-value intelligence features are maintained in private modules:

- **Public Client**: CLI, local memory, BYOK adapters, AI Memory Recon, and plugin interfaces.
- **Private Brain**: Proprietary ranking formulas, agent orchestration recipes, and cost optimizers.
- **Paid API**: Hosted model gateway and global synchronization.

---

## 🥇 Standards

- ✅ 100% Pass Rate on 121+ unit tests.
- 💻 Hardened for Windows, macOS, and Linux.

## 📜 Notice

Copyright © 2026 Who Visions LLC. All rights reserved. 🛡️ This source code is provided for visibility and personal use only. Commercial reuse is not granted.

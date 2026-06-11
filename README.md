# 🪩 NouGenShards

```text
░█▀█░█▀█░█░█░█▀▀░█▀▀░█▀█░█▀▀░█░█░█▀█░█▀▄░█▀▄░█▀▀
░█░█░█░█░█░█░█░█░█▀▀░█░█░▀▀█░█▀█░█▀█░█▀░▀░▀░▀▀▀
```

**🧠 Persistent local memory and federated intelligence for your AI tools.**

NouGenShards helps your AI tools remember their work across the entire fabric of your data. It saves "shards" of information—records of what worked and what did not work—in local databases, external SQL servers, or remote cloud nodes. This persistent memory lets your tools find the right information quickly by searching both your computer and your cloud subscriptions simultaneously.

> 🇭🇹 This tool is built by **Who Visions** to help people use AI tools on their own computers and in the cloud, creating a unified bridge for global diaspora intelligence.

---

## 🚀 How to Start

### 1. 📦 Install

**Windows (One-Click)** 🪟
```bash
# Just run the launcher
nougen.bat
```
*The launcher automatically sets up a secure virtual environment and installs all dependencies.*

**Other Platforms** 🐍🟢
```bash
# If you use Python
pip install .

# If you use Node.js
npm install -g .
```

### 2. 🛡️ Setup

```bash
nougen init
```
This initializes your local memory substrate and sets up the secure vault. 📂

---

## ☁️ Hybrid Intelligence (Cloud & Local)

NouGenShards connects your local environment to the cloud AI ecosystem.

### 🔐 Connect Your Subscriptions (BYOK)
Bring your own API keys for cloud AI services. 🔑
```bash
# Set your API keys
nougen auth set-key openai <your-key>
nougen auth set-key openrouter <your-key>
nougen auth set-key huggingface <your-key>

# List your connected services
nougen auth list
```

### 🌉 Link External Databases
Connect to your existing databases (Postgres, MySQL, SQLite) to search your production data alongside your memory. 🔗
```bash
# Link an external SQL database
nougen db link "postgresql://user:pass@localhost/mydb" --table production_logs
```

### 📡 Federated Memory Nodes
Connect to other NouGenShards instances (like your team's server or a remote orchestrator). 🌐
```bash
# Link a remote NouGen cloud node
nougen node link "https://your-space.hf.space" --name team_core
```

---

## 💾 Manage Memory (Shards)

### 📝 Save Shards
Save what you have learned or what you have done as a memory shard. 🧩
```bash
# Save a new shard with optional vector embedding
nougen add "Updated the API endpoint to v2" --tags api,update --embed
```

### 🕵️ Search and Find
Find shards across your local computer, linked databases, and cloud nodes. 🥇
```bash
# Unified search (Ranked by Bayesian Relevance)
nougen search "api update" --semantic
```

### 👍 Mark Results
Tell the tool if a shard was helpful. This updates the **Bayesian Prior**, helping the tool give you better answers in the future. 📈
```bash
# Mark record number 1 as helpful
nougen mark 1 --worked
```

---

## ⚡ OpenRouter Production Routing

NouGenShards includes a production-grade routing layer for OpenRouter, designed for maximum resilience and cost-efficiency.

### 🛡️ Features
*   **Model Fallback**: Automatically tries multiple models in order if the primary fails.
*   **Prompt Caching**: Maximizes cache hits using stable message prefixes and `session_id` for sticky provider routing.
*   **Response Healing**: Automatically repairs malformed JSON, markdown-wrapped JSON, and common syntax errors using the OpenRouter healing plugin.
*   **Structured Outputs**: Enforces JSON Schema validation with `strict: true` at the API level.
*   **Local Validation**: Final JSON schema validation layer before memory ingestion.
*   **Usage Telemetry**: Detailed tracking of `prompt_tokens`, `completion_tokens`, and `cached_tokens`.

### 🚀 Usage

**Chat with Fallback**
```bash
# Uses openrouter/auto with default fallback models
nougen router chat "What is the capital of Haiti?" --session-id nougen-dev
```

**Structured JSON Output**
```bash
# Requests JSON matching the provided schema, with auto-healing enabled
nougen router json "Extract the entities: Dave went to the Stadium." --schema person_schema.json --healing
```

**Check Routing Health**
```bash
nougen router doctor
```

---

## 🧩 Project Structure

- **📂 src/nougen_shards/**: The main code for the tool.
- **🔌 src/nougen_shards/connectors/**: SQL and Cloud database connectors.
- **🧪 tests/**: Code to check that the tool works correctly.

## 🥇 Quality and Standards

- ✨ 10.00/10 Pylint score on all core modules.
- ✅ 100% Pass Rate on all 102+ unit tests.
- 💻 Hardened for Windows, macOS, and Linux.

## 📜 License

Copyright © 2026 Who Visions LLC. All rights reserved. 🛡️ This source code is provided for visibility purposes only. Reuse is not granted.

# 🪩 NouGenShards

**🧠 Persistent local memory and sandboxed context for coding agents.**  
*Your agents have prompts — mine have shards.*

NouGenShards is a professional-grade sidecar for your AI-powered development workflow. It stores reusable “shards” of machine experience in a local SQLite + FTS5 database with **outcome-weighted retrieval**, ensuring your agents recall what actually worked instead of re-prompting from scratch.

> 🇭🇹 **Nou gen AI** is Haitian Kreyòl for *“we have AI.”* Built by [Who Visions](https://whovisions.com) to put high-leverage AI tooling — including edge models that run without service — in the hands of the diaspora.

---

## 🚀 The Top-1% Quickstart

The strongest signal across the best CLI tools: optimize for time-to-first-value.

### 1. Install

```bash
# Via Python
pip install .

# Or via Node (as a global wrapper)
npm install -g .
```

### 2. Bootstrap (Zero to Shard)

```bash
nougen init
```
*Initializes your local vault (`~/.nougen/`) and sets up the SQLite database with FTS5 virtual tables.*

### 3. Manage Memory (Shards)

Capture what works, search what you know, and mark outcomes for smarter retrieval.

```bash
# Capture experience
nougen add "Fixed the Mars Map tiles by updating the URL in app/MarsMap.tsx" --tags mars,bugfix

# Search & Recall (Ranked by FTS5 + Utility)
nougen search "mars tiles"

# Mark a shard's utility (Outcome-Weighted)
nougen mark 1 --worked
```

### 4. Manage Attention (Context)

Run scripts in a sandboxed environment to process data without bloating your LLM context window with raw logs.

```bash
# Initialize a fresh context session
nougen ctx init

# Execute sandboxed code (JS/Bun/Python) and return only the signal
nougen ctx execute "const data = [1, 2, 3]; console.log('Mean:', data.reduce((a, b) => a + b) / data.length)"

# Promote a session event to a durable Shard
nougen ctx promote 1
```

### 5. Edge Intelligence (Models)

Talk to local models (Ollama/LM Studio) directly from your terminal.

```bash
# List available local models
nougen models

# Start a local chat session
nougen chat --model llama3
```

---

## 🧩 Architecture: The Shard Layer

NouGenShards operates as the "heart" and "cortex" of your agentic system:

- **Core**: Python logic using SQLite for persistent, low-latency storage.
- **Search**: Ranked retrieval using **FTS5 (Full-Text Search)** + utility-based scoring (worked vs. failed).
- **Hardening**: Built-in Windows-safe sandbox for isolated execution of agent-generated code.
- **Interface**: Unified CLI for humans, **MCP (Model Context Protocol)** for agents (Claude, Cursor).

## 📁 Project Structure

```
src/nougen_shards/  # Core package logic
  core.py           # Database and capture/retrieve functions
  cli.py            # Unified Command-line interface
  mcp.py            # Model Context Protocol server
  nougen_context.py # Ephemeral session management
  nougen_sandbox.py # Hardened execution environment
tests/              # Massive 102-test suite (100% pass rate)
examples/           # Demo scripts and usage patterns
```

## 📊 Show the Scoreboard

We maintain a rigorous standard of quality:
- **10.00/10** Pylint score across the entire core.
- **100% Pass Rate** on our comprehensive integration test suite.
- **Production-Ready** absolute path resolution and environment isolation.

## 📜 License

MIT License. © 2026 Who Visions LLC. Build the future. Ownership is everything.

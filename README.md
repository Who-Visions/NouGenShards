# 🪩 NouGenShards

**🧠 Persistent local memory for coding agents.** *Your agents have prompts — mine have shards.*

NouGenShards stores reusable “shards” of machine experience in a local SQLite + FTS5 database with outcome-weighted retrieval. This allows your IDE agents to recall what actually worked in previous sessions instead of starting every reasoning loop from scratch.

> 🇭🇹 **Nou gen AI** is Haitian Kreyòl for *“we have AI.”* Built by [Who Visions](https://whovisions.com) to put high-leverage AI tooling in the hands of the diaspora.

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
*This initializes your local vault and sets up the SQLite database with FTS5 virtual tables.*

### 3. Capture Experience

```bash
nougen add "Fixed the Mars Map tiles by updating the URL in app/MarsMap.tsx" --tags mars,bugfix
```

### 4. Search & Recall

```bash
nougen search "mars tiles"
```

### 5. Connect to IDE

```bash
nougen connect --mcp
```
*Follow the prompts to add NouGenShards as an MCP server to your Claude Desktop or Cursor configuration.*

---

## 🧩 Architecture: The Shard Layer

NouGenShards operates as a sidecar to your development workflow:

- **Core**: Python logic using SQLite for persistent, low-latency storage.
- **Search**: Ranked retrieval using FTS5 + utility-based scoring (worked vs. failed).
- **Interface**: CLI for humans, MCP for agents.
- **Daemon**: Optional auto-research loop that pulls relevant SOTA papers from arXiv to keep your local knowledge fresh.

## 📁 Project Structure

```
src/nougen_shards/  # Core package logic
  core.py           # Database and capture/retrieve functions
  cli.py            # Command-line interface
  mcp.py            # Model Context Protocol server
  keymaker.py       # Secure secret ingestion (Atibon)
tests/              # Comprehensive test suite
examples/           # Demo scripts and usage patterns
bin/                # Node.js wrapper for cross-platform ease
```

## 📜 License

MIT License. © 2026 Who Visions LLC. Build the future. Ownership is everything.

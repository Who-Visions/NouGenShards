# Packaging NouGenShards for GitHub

To share this architecture with the AI engineering community, structure your repository using the blueprint below. This turns a local script into a plug-and-play package that developers can drop into any agent pipeline (Cursor, Claude Code, custom agents).

## 📂 Recommended Repository Structure

```
nougen-shards/
├── .github/
│   └── workflows/
│       └── ci.yml          # Automated testing (runs demo.py on PRs)
├── src/
│   └── nougen_shards/
│       ├── __init__.py     # Package exports
│       ├── core.py         # The SQLite + WAL + FTS5 logic (shards.py)
│       └── mcp.py          # Model Context Protocol wrapper for tool use
├── examples/
│   ├── demo_subprocess.py  # Simulated subprocess resolution run
│   └── cursor_agent_setup/ # Instruction prompts for Cursor custom rules
├── README.md               # Visual, premium documentation
├── LICENSE                 # Open-source license (MIT recommended)
├── pyproject.toml          # Package installation configuration (using poetry/uv)
└── requirements.txt        # Minimal dependency list (sqlite3 is stdlib!)
```

---

## 🛠️ The PyPI / Dependency Target (`pyproject.toml`)
Keep dependencies minimal. The core engine runs on Python's standard library `sqlite3` and `hashlib`. For vector extensions, add optional dependencies:

```toml
[project]
name = "nougen-shards"
version = "0.1.0"
description = "Persistent local memory for coding agents using SQLite + WAL + FTS5."
readme = "README.md"
requires-python = ">=3.9"
dependencies = [
    # Zero core dependencies required! Standard library only.
]

[project.optional-dependencies]
vectors = [
    "sentence-transformers>=2.2.0", # Optional for vector hybrid retrieval
    "numpy>=1.20.0"
]
```

---

## 🚀 Model Context Protocol (MCP) Server Integration
To allow tools-based agents (like Claude Code) to use this automatically, add an MCP entrypoint in `src/nougen_shards/mcp.py` using the `mcp` Python SDK:

```python
# src/nougen_shards/mcp.py
from mcp.server.fastapi import FastServer
from .core import capture, retrieve

server = FastServer("NouGenShards")

@server.tool()
def capture_experience(event_type: str, title: str, content: str, tags: list = None) -> str:
    """Store a unit of agent experience as a shard."""
    success = capture(event_type, title, content, tags)
    return "Shard captured successfully." if success else "Shard already exists."

@server.tool()
def recall_memory(query: str, limit: int = 3) -> str:
    """Search for relevant history shards using ranked FTS5 search."""
    shards = retrieve(query, limit)
    # Return formatted Recall Packet
    ...
```

---

## 📝 GitHub Release checklist
1. **Choose License**: Create `LICENSE` file containing the standard MIT License.
2. **Add Cursor/Agent Instructions**: Developers love when repos contain a `.cursorrules` or `.agent/skills/` file that they can copy-paste into their workspace to teach their IDE agents how to write to the shard layer automatically.
3. **Show the Scoreboard**: Embed the run outputs of `demo.py` directly in the README as a screenshot or code block to prove it works out-of-the-box.

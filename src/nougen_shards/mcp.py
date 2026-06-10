"""Model Context Protocol (MCP) server for NouGenShards."""
import json
try:
    from mcp.server.fastapi import FastServer
except ImportError:
    # Fallback for environments where mcp is not yet installed
    class FastServer:
        def __init__(self, name): self.name = name
        def tool(self): return lambda f: f

from .core import capture, retrieve, mark_shard, compile_recall_packet
from . import nougen_context
from . import nougen_sandbox

server = FastServer("NouGenShards")

# --- Memory Core (Shards) ---

@server.tool()
def capture_experience(event_type: str, title: str, content: str, tags: list = None) -> str:
    """Store a unit of agent experience as a shard."""
    success = capture(event_type, title, content, tags)
    return "Shard captured successfully." if success else "Shard already exists."

@server.tool()
def recall_memory(query: str, limit: int = 3) -> str:
    """Search for relevant history shards using ranked FTS5 search."""
    shards_list = retrieve(query, limit)
    if not shards_list:
        return "No relevant shards found."
    return compile_recall_packet(shards_list)

@server.tool()
def mark_utility(shard_id: int, worked: bool) -> str:
    """Update the Bayesian utility score of a shard based on performance outcome."""
    if mark_shard(shard_id, worked):
        return f"Utility for Shard #{shard_id} updated."
    return f"Shard #{shard_id} not found."

# --- Attention Layer (Context) ---

@server.tool()
def log_context_event(event_type: str, description: str, metadata: dict = None) -> str:
    """Log an ephemeral session event to the context layer."""
    nougen_context.log_event(event_type, description, metadata)
    return "Context event logged."

@server.tool()
def search_context(query: str, limit: int = 5) -> str:
    """Search for ephemeral session events in the context layer."""
    events = nougen_context.search_events(query, limit)
    if not events:
        return "No context events found."
    
    output = ["--- CONTEXT SEARCH RESULTS ---"]
    for e in events:
        output.append(f"[{e['timestamp']}] {e['event_type']}: {e['description']}")
    return "\n".join(output)

# --- Execution Layer (Sandbox) ---

@server.tool()
def execute_code(code: str) -> str:
    """Execute Python or Node.js code in a sandboxed environment."""
    return nougen_sandbox.execute_sandboxed(code)

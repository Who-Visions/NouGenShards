"""Model Context Protocol (MCP) server for NouGenShards."""
try:
    from mcp.server.fastapi import FastServer
except ImportError:
    # Fallback for environments where mcp is not yet installed
    class FastServer:
        def __init__(self, name): self.name = name
        def tool(self): return lambda f: f

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
    shards_list = retrieve(query, limit)
    if not shards_list:
        return "No relevant shards found."
    
    output = []
    for s in shards_list:
        output.append(f"[{s['event_type']}] {s['title']}\n{s['content']}\n")
    return "\n---\n".join(output)

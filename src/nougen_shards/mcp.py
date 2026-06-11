"""Model Context Protocol (MCP) server for NouGenShards."""
import json
import sys
from typing import Optional, List, Dict, Any
from pathlib import Path

# Fallback wrapper for mcp dependency if missing
class MockFastMCP:
    def __init__(self, name: str, dependencies: Optional[list] = None):
        self.name = name
    def tool(self): return lambda f: f
    def run(self): print("MCP not installed.")

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = MockFastMCP # type: ignore

from .core import capture, retrieve, mark_shard, compile_recall_packet
from . import nougen_context
from . import nougen_sandbox
from .brain_scan import scan_environment, run_import
from .history import HistoryEngine
from .federation import federated_retrieve

# Initialize FastMCP Server
mcp = FastMCP(
    "NouGenShards",
    dependencies=["mcp"]
)

# --- Memory Core (Shards) ---

@mcp.tool()
def capture_experience(event_type: str, title: str, content: str, tags: Optional[List[str]] = None) -> str:
    """
    Store a unit of agent experience as a persistent shard.
    
    Args:
        event_type: The category of the event (e.g., 'KNOWLEDGE', 'DECISION', 'ERROR').
        title: A brief, descriptive title for the memory.
        content: The full content or payload of the memory.
        tags: Optional list of tags for easier categorization.
    """
    success = capture(event_type, title, content, tags)
    return "Shard captured successfully." if success else "Shard already exists."

@mcp.tool()
def recall_memory(query: str, limit: int = 3) -> str:
    """
    Search for relevant history shards using the federated Bayesian retrieval engine.
    This searches local shards, external DBs, and remote cloud nodes.
    
    Args:
        query: The search term or context you are trying to match.
        limit: Max number of results to return.
    """
    shards_list = federated_retrieve(query, limit=limit)
    if not shards_list:
        return "No relevant shards found in the memory substrate."
    return compile_recall_packet(shards_list)

@mcp.tool()
def mark_utility(shard_id: int, worked: bool) -> str:
    """
    Update the Bayesian utility score of a shard based on its performance outcome.
    
    Args:
        shard_id: The ID of the shard to update.
        worked: True if the shard's information was useful/correct, False if it was not.
    """
    if mark_shard(shard_id, worked):
        return f"Utility for Shard #{shard_id} updated successfully."
    return f"Shard #{shard_id} not found."

# --- Attention Layer (Context) ---

@mcp.tool()
def log_context_event(event_type: str, description: str, metadata: Optional[dict] = None) -> str:
    """
    Log an ephemeral session event to the short-term context layer.
    
    Args:
        event_type: The type of context event (e.g., 'TOOL_CALL', 'THOUGHT').
        description: Description of the event.
        metadata: Optional dictionary of additional context data.
    """
    nougen_context.log_event(event_type, description, metadata)
    return "Context event logged."

@mcp.tool()
def search_context(query: str, limit: int = 5) -> str:
    """
    Search for ephemeral session events in the short-term context layer.
    
    Args:
        query: The search term to match against recent context events.
        limit: Max number of events to return.
    """
    events = nougen_context.get_event(int(query)) if query.isdigit() else None
    if not events:
        # Fallback to search if it's not an ID, but we only expose get_event right now 
        # in nougen_context unless we use raw SQL. We can just use the DB directly here.
        conn = nougen_context.get_context_connection()
        try:
            cursor = conn.execute(
                "SELECT id, type, content, timestamp FROM ctx_events WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?", 
                (f"%{query}%", limit)
            )
            rows = cursor.fetchall()
            if not rows:
                return "No context events found."
            output = ["--- CONTEXT SEARCH RESULTS ---"]
            for r in rows:
                output.append(f"[{r['timestamp']}] #{r['id']} {r['type']}: {r['content']}")
            return "\n".join(output)
        finally:
            conn.close()
    
    if events:
        return f"[{events['timestamp']}] #{events['id']} {events['type']}: {events['content']}"
    return "No context events found."

@mcp.tool()
def promote_context_to_shard(event_id: int, tags: Optional[List[str]] = None) -> str:
    """
    Promote an ephemeral context event into a permanent, durable memory shard.
    
    Args:
        event_id: The ID of the context event to promote.
        tags: Optional tags to apply to the new shard.
    """
    event = nougen_context.get_event(event_id)
    if not event:
        return f"Error: Context event #{event_id} not found."
    
    final_tags = tags or []
    if "promoted" not in final_tags:
        final_tags.append("promoted")
        
    success = capture(
        event_type=f"PROMOTED_{event['type']}",
        title=f"Promoted Context #{event['id']}",
        content=event['content'],
        tags=final_tags
    )
    if success:
        return f"Context event #{event['id']} successfully promoted to durable memory."
    return "Shard already exists in memory."

# --- Execution Layer (Sandbox) ---

@mcp.tool()
def execute_sandboxed_code(code: str) -> str:
    """
    Execute Python or Node.js code in a sandboxed environment.
    
    Args:
        code: The script source code to execute.
    """
    return nougen_sandbox.execute_sandboxed(code)

# --- Brain Recon Layer ---

@mcp.tool()
def run_brain_scan(project_path: Optional[str] = None, include_unknown: bool = False) -> str:
    """
    Scan the local machine for AI tool history (Claude, Gemini, Cursor, etc.).
    Returns a summary of discovered memory sources without importing them.
    
    Args:
        project_path: Optional path to a specific project directory to scan.
        include_unknown: If True, scans for unknown dotfolders as well.
    """
    candidates = scan_environment(project_path=project_path, include_unknown=include_unknown)
    
    high = [c for c in candidates if c.score_tier == "high"]
    med = [c for c in candidates if c.score_tier == "medium"]
    
    tools = {}
    for c in candidates:
        tools[c.tool] = tools.get(c.tool, 0) + 1

    output = ["🧠 NouGenShards Brain Scan\n", "High-confidence AI memory:"]
    for tool, count in tools.items():
        if tool != "unknown":
            output.append(f"  .{tool:<12} found   {count} files likely")
            
    output.append("\nProject context:")
    for c in [c for c in candidates if c.is_project_context][:5]:
        output.append(f"  {c.path.name}")
    if len([c for c in candidates if c.is_project_context]) > 5:
        output.append("  ... and more.")

    output.append(f"\nEstimated new shards: {len(high) * 2 + len(med)}")
    return "\n".join(output)

@mcp.tool()
def run_brain_import(project_path: Optional[str] = None, source_filter: Optional[str] = None, dry_run: bool = True) -> str:
    """
    Import discovered AI tool history into the NouGenShards memory substrate.
    
    Args:
        project_path: Optional path to a specific project directory to scan and import.
        source_filter: Filter by specific tool (e.g., 'claude', 'gemini').
        dry_run: If True, only estimates the import size without writing to the database. Set to False to actually ingest shards.
    """
    result = run_import(
        project_path=project_path,
        include_unknown=False,
        source_filter=source_filter,
        redact=True,
        confirm=not dry_run
    )
    
    if dry_run:
        return (
            f"🧠 NouGenShards Brain Import (Dry Run)\n\n"
            f"Files to scan: {result.files_scanned}\n"
            f"Estimated records to parse: {result.records_parsed}\n\n"
            f"Set dry_run=False to execute the ingestion."
        )
    else:
        return (
            f"🧠 NouGenShards Brain Import Complete\n\n"
            f"Files scanned:      {result.files_scanned}\n"
            f"Records parsed:     {result.records_parsed}\n"
            f"Shards created:     {result.shards_created}\n"
            f"Duplicates skipped: {result.duplicates_skipped}\n"
            f"Secrets redacted:   {result.secrets_redacted}\n\n"
            f"✅ Local memory enriched."
        )

# --- Historical Analytics ---

@mcp.tool()
def get_memory_stats(period: str = "week") -> str:
    """
    Get historical analytics on memory growth and utility trends.
    
    Args:
        period: The time window to analyze ('24h', 'week', 'month', 'quarter', 'year').
    """
    engine = HistoryEngine()
    growth = engine.get_growth_rate(period)
    utility = engine.get_utility_delta(period)
    timeline = engine.get_timeline(period)
    
    output = [
        f"📈 NouGenShards History ({period})",
        timeline,
        f"\n - New Shards Captured: {growth.get('new_shards', 0)}",
        f" - Total Memory Size:   {growth.get('total_shards', 0)} shards",
        f" - Bayesian Utility \u0394: {'+' if utility >= 0 else ''}{utility:.2f}"
    ]
    
    total = growth.get('total_shards', 0)
    new_shards = growth.get('new_shards', 0)
    if total > 0:
        rate = (new_shards / total) * 100
        output.append(f" - Acceleration Rate:   {rate:.1f}% expansion")
        
    return "\n".join(output)

def main():
    """Main entry point for the MCP server."""
    # Start the FastMCP server with stdio transport
    mcp.run()

if __name__ == "__main__":
    main()

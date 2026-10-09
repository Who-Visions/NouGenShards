"""Model Context Protocol (MCP) server for NouGenShards — Valerion Engine."""
import json
import os
import sqlite3
from nougen_shards import agents
from typing import Optional, List

# Fallback wrapper for mcp dependency if missing
class MockFastMCP:
    def __init__(self, name: str, dependencies: Optional[list] = None,
                 instructions: Optional[str] = None):
        self.name = name
        self.instructions = instructions
    def tool(self): return lambda f: f
    def run(self): print("MCP not installed.")

# mcp 2.x renamed FastMCP to MCPServer (mcp.server.fastmcp no longer exists).
# Both spellings are accepted so a node mid-upgrade keeps serving on either
# version; the constructor kwargs used below (dependencies, instructions) and
# .tool()/.run() are unchanged across the rename.
try:
    from mcp.server.mcpserver import MCPServer  # mcp >= 2
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP as MCPServer  # mcp < 2
    except ImportError:
        MCPServer = MockFastMCP  # type: ignore

# Backwards-compatible alias for any caller still importing the old name.
FastMCP = MCPServer

from .core import capture, mark_shard, compile_recall_packet
from . import nougen_context
from . import nougen_sandbox
from . import evolution
from . import skills as skill_registry
from .brain_scan import scan_environment, run_import

from .history import HistoryEngine
from .federation import federated_retrieve

# ~32k chars per recall packet unless NOUGEN_RECALL_TOKEN_BUDGET says otherwise ("0" = unbounded).
DEFAULT_RECALL_TOKEN_BUDGET = 8000


def _server_instructions() -> str:
    """Standing instructions handed to every client at connection.

    The roster travels with the handshake rather than waiting to be asked for,
    so an agent knows the skills exist before it starts work. This is the
    frictionless half of enforcement; ``apply_skills`` is the other half.
    """
    return (
        "NouGenShards memory and skill server.\n\n"
        "SKILLS ARE MANDATORY, NOT OPTIONAL. Before producing any work that an "
        "installed skill covers, call apply_skills(task) with a short description "
        "of what you are about to do. It returns the skills that govern that work, "
        "in full. Follow them. Do not design, build or write from your own defaults "
        "when a skill covers the task - the skill supersedes them.\n\n"
        "One call is enough: apply_skills resolves and returns the relevant skill "
        "bodies together, so there is no list-then-load step.\n\n"
        "Installed skills:\n"
        f"{skill_registry.roster()}\n"
    )


# Initialize the MCP server
try:
    mcp = MCPServer(
        "NouGenShards",
        dependencies=["mcp"],
        instructions=_server_instructions(),
    )
except TypeError:
    # Older builds predate the instructions kwarg; the apply_skills tool
    # still enforces skills, the roster just does not ride the handshake.
    mcp = MCPServer("NouGenShards", dependencies=["mcp"])

# --- Memory Core (Shards) ---

@mcp.tool()
def capture_experience(event_type: str, title: str, content: str, tags: Optional[List[str]] = None,
                       original_timestamp: Optional[str] = None) -> str:
    """
    Store a unit of agent experience as a persistent shard.

    Args:
        event_type: The category of the event (e.g., 'KNOWLEDGE', 'DECISION', 'ERROR').
        title: A brief, descriptive title for the memory.
        content: The full content or payload of the memory.
        tags: Optional list of tags for easier categorization.
        original_timestamp: Optional ISO-8601 timestamp stamping migrated
            content at its true era instead of capture time; invalid values
            fall back to now.
    """
    result = capture(event_type, title, content, tags,
                     original_timestamp=original_timestamp)
    if result:
        return (f"Shard captured successfully (id {result['shard_id']} "
                f"in db {result['db_index']}).")
    return f"Shard NOT captured: {result.get('error', 'unknown reason')}"

@mcp.tool()
def recall_memory(query: str, limit: int = 3, session_id: Optional[str] = None,
                  agent: Optional[str] = None, user: Optional[str] = None,
                  machine: Optional[str] = None, project: Optional[str] = None,
                  as_of: Optional[str] = None) -> str:
    """
    Search for relevant history shards using the federated weighted-relevance retrieval engine.
    This searches local shards, external DBs, and remote cloud nodes.
    
    Args:
        query: The search term or context you are trying to match.
        limit: Max number of results to return.
    """
    # sweep_report is how a lane dropped by the recall deadline becomes visible.
    # Without it this tool answered "No relevant shards found" for a timed-out
    # sweep — a positive claim about the substrate that the substrate never
    # made. An agent acting on that will re-derive knowledge it already holds.
    # Optional: session_id turns on the delta channel (shards this session already
    # received come back as one-line [HELD] handles) and knapsack packing.
    # agent/user/machine/project scope the search via tags; as_of = what the vault
    # had learned by that time. Scoped or as-of queries run on the local grid,
    # which is where those filters live.
    sweep_report: dict = {}
    scope = {k: v for k, v in {"agent": agent, "user": user, "machine": machine, "project": project}.items() if v}
    if scope or as_of:
        from nougen_shards import core as _core  # pylint: disable=import-outside-toplevel
        shards_list = _core.retrieve(query, limit=limit, domain_key="*", scope=scope or None, as_of=as_of)
    else:
        shards_list = federated_retrieve(query, limit=limit, sweep_report=sweep_report)
    dropped = sweep_report.get("lanes_timed_out") or []
    if not shards_list:
        if dropped:
            return ("Recall INCOMPLETE — no answer, not an empty substrate: "
                    f"{len(dropped)} lane(s) ({', '.join(dropped)}) missed the "
                    f"{sweep_report.get('deadline_s')}s recall deadline. "
                    "Retry, or raise NOUGEN_RECALL_DEADLINE_S; do NOT conclude "
                    "the substrate holds nothing on this query.")
        return "No relevant shards found in the memory substrate."
    budget = os.environ.get("NOUGEN_RECALL_TOKEN_BUDGET", "").strip()
    # Unbounded used to be the default; one 994k-char screenplay shard then
    # filled a 2-hit recall and the MCP transport timed out (WhoArt, 2026-09-20).
    # Bounded by default, "0" restores the old unbounded packet on purpose.
    if budget.isdigit():
        token_budget = int(budget) or None
    else:
        token_budget = DEFAULT_RECALL_TOKEN_BUDGET
    if session_id:
        from nougen_shards import distill as _distill  # pylint: disable=import-outside-toplevel
        sent: list = []
        packet = compile_recall_packet(shards_list, token_budget=token_budget or 1200, strategy="knapsack",
                                       held=_distill.held_keys(session_id), included=sent)
        _distill.mark_sent(session_id, sent)
    else:
        packet = compile_recall_packet(shards_list, token_budget=token_budget)
    if dropped:
        packet += ("\n\n[COVERAGE WARNING] Partial result: "
                   f"{len(dropped)} lane(s) ({', '.join(dropped)}) missed the "
                   f"{sweep_report.get('deadline_s')}s recall deadline. "
                   "Shards below are real; absence below proves nothing.")
    return packet

@mcp.tool()
def recall_layered(query: str, token_budget: int = 1200) -> str:
    """
    Layered recall (TencentDB-Agent-Memory L0-L3): the owner persona (L3) and the
    matching topic scenes (L2) come first as bootstrap context, then distilled
    atoms (L1) with shard handles, then raw shards (L0) in whatever budget is left.
    Needs the distillation sidecar (tools/distill_run.py); without it this falls
    back to plain shards.

    Args:
        query: What you are trying to recall.
        token_budget: Approximate token cap for the whole packet.
    """
    from nougen_shards import core as _core, distill as _distill  # pylint: disable=import-outside-toplevel
    return _distill.layered_context(query, lambda q, **kw: _core.retrieve(q, limit=8), token_budget=token_budget)


@mcp.tool()
def mark_utility(shard_id: int, worked: bool, db_index: Optional[int] = None) -> str:
    """
    Update the usefulness score of a shard based on its performance outcome.

    Args:
        shard_id: The ID of the shard to update.
        worked: True if the shard's information was useful/correct, False if it was not.
        db_index: Database index the shard lives in (the recall result's _db_index).
            Omit to search the whole grid (ambiguous once shard ids collide across DBs).
    """
    if mark_shard(shard_id, worked, db_index):
        return f"Utility for Shard #{shard_id} updated successfully."
    return f"Shard #{shard_id} not found."

# --- Graph Memory (Latent Mesh) ---

@mcp.tool()
def link_shards(src_id: int, dst_id: int, relation: str = "relates",
                src_db: int = 1, dst_db: int = 1) -> str:
    """
    Link two memory shards into the graph mesh (e.g. a fix to the file it touched,
    a command to the decision that caused it).

    Args:
        src_id: ID of the source shard.
        dst_id: ID of the destination shard.
        relation: Edge label (e.g. 'fixes', 'touches', 'caused_by', 'relates').
        src_db: Database index the source shard lives in (the recall result's _db_index; default 1).
        dst_db: Database index the destination shard lives in (default 1).
    """
    from . import graph  # pylint: disable=import-outside-toplevel
    if graph.link_shards(src_id, dst_id, relation, src_db, dst_db):
        return f"Edge created: shard {src_id} -[{relation}]-> shard {dst_id}."
    return "No edge created (a shard was missing, identical, or already linked)."

@mcp.tool()
def recall_related(shard_id: int, db_index: int = 1, relation: Optional[str] = None,
                   limit: int = 10) -> str:
    """
    Recall shards connected to a given shard in the graph mesh (walks links in
    either direction). Surfaces the latent context around a memory.

    Args:
        shard_id: ID of the shard to expand from.
        db_index: Database index the shard lives in (the recall result's _db_index; default 1).
        relation: Optional filter to a single relation label.
        limit: Max number of neighbours to return.
    """
    from . import graph  # pylint: disable=import-outside-toplevel
    related = graph.related_shards(shard_id, db_index, relation, limit)
    if not related:
        return "No related shards found in the mesh."
    output = ["=== GRAPH MEMORY: RELATED SHARDS ==="]
    for r in related:
        output.append(
            f"[{r['direction']}|{r['relation']}] #{r['id']} {r['title']}\n{r['content'][:160]}")
    return "\n".join(output)

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
    results = []
    seen_ids = set()

    # When the query looks like an id, surface the exact-id match as a bonus hit —
    # but still run the content search below so numeric tokens (e.g. "404", "2024")
    # remain searchable as content rather than being swallowed by an id lookup.
    if query.isdigit():
        event = nougen_context.get_event(int(query))
        if event:
            results.append(f"[{event['timestamp']}] #{event['id']} {event['type']}: {event['content']}")
            seen_ids.add(event["id"])

    try:
        conn = nougen_context.get_context_connection()
        try:
            cursor = conn.execute(
                "SELECT id, type, content, timestamp FROM ctx_events WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?",
                (f"%{query}%", limit)
            )
            for r in cursor.fetchall():
                if r["id"] in seen_ids:
                    continue
                results.append(f"[{r['timestamp']}] #{r['id']} {r['type']}: {r['content']}")
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return f"Error: context search failed: {exc}"

    if not results:
        return "No context events found."
    return "\n".join(["--- CONTEXT SEARCH RESULTS ---"] + results)

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
    
    final_tags = list(tags or [])
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
def execute_sandboxed_code(code: str, language: str = "python") -> str:
    """
    Execute Python, Node.js, PowerShell, or shell code in a sandboxed environment.

    Args:
        code: The script source code to execute.
        language: Runtime to use — 'python' (default), 'javascript', 'typescript', 'powershell', 'shell', or 'cmd'.
    """
    return nougen_sandbox.execute_sandboxed(code, language=language)


@mcp.tool()
def fetch_web_sandboxed(url: str, label: Optional[str] = None) -> str:
    """
    Natively fetch, extract, and index a web page into NouGen Context without polluting prompt context.

    Args:
        url: The web URL to fetch.
        label: Optional descriptive label for indexing.
    """
    res = nougen_context.fetch_and_index_web(url, label=label)
    if "error" in res:
        return f"Error: {res['error']}"
    headings_summary = "\n".join(f"- {h}" for h in res.get("headings", [])[:8])
    links_summary = "\n".join(f"- {link}" for link in res.get("key_links", [])[:8])
    return (
        f"✅ Successfully indexed '{res['title']}' into NouGen Context (Handle: {res['handle']})\n"
        f"Summary: {res['summary']}\n\n"
        f"Headings:\n{headings_summary}\n\n"
        f"Key Links:\n{links_summary}\n\n"
        f"Length: {res['total_length_bytes']} bytes stored in sandbox."
    )


@mcp.tool()
def analyze_file_sandboxed(file_path: str, query: Optional[str] = None) -> str:
    """
    Analyze a file in the sandbox (AST classes/functions, JSON schema, pattern matches) without reading raw file into context.

    Args:
        file_path: Absolute or relative path to file on disk.
        query: Optional string/keyword to filter matching lines.
    """
    res = nougen_context.analyze_file(file_path, query=query)
    if "error" in res:
        return f"Error: {res['error']}"
    out = [f"📄 {res['name']} ({res['total_lines']} lines, {res['size_bytes']} bytes)"]
    if "ast" in res:
        ast_data = res["ast"]
        if ast_data.get("syntax_valid"):
            out.append(f"Classes: {', '.join(ast_data['classes']) or 'None'}")
            out.append(f"Functions: {', '.join(ast_data['functions'][:15]) or 'None'}")
            out.append(f"Imports: {', '.join(ast_data['imports'][:12]) or 'None'}")
        else:
            out.append(f"Syntax Error: {ast_data.get('syntax_error')}")
    elif "json_schema" in res:
        js = res["json_schema"]
        out.append(f"JSON Structure: {json.dumps(js)}")
    if "query_matches" in res:
        out.append(f"Matches for '{query}':")
        out.extend(res["query_matches"])
    return "\n".join(out)


@mcp.tool()
def batch_execute_sandboxed(commands: List[dict], queries: Optional[List[str]] = None) -> str:
    """
    Run multiple sandboxed commands/scripts, index output in sandbox, and extract query matches.

    Args:
        commands: List of dicts, each with 'label', 'code', and optional 'language' ('python'|'javascript'|'powershell'|'shell').
        queries: Optional keywords to extract matching lines across all outputs.
    """
    res = nougen_sandbox.batch_execute_sandboxed(commands, queries=queries)
    summary_lines = ["--- BATCH EXECUTION SUMMARY ---"]
    for s in res.get("steps", []):
        summary_lines.append(f"[{s['status'].upper()}] {s['label']} ({s['language']}): {s['preview'][:100]}")
    if res.get("query_matches"):
        summary_lines.append("\n--- QUERY MATCHES ---")
        for q, matches in res["query_matches"].items():
            summary_lines.append(f"Matches for '{q}':")
            for m in matches:
                summary_lines.append(f"  {m}")
    return "\n".join(summary_lines)


@mcp.tool()
def checkpoint_session(label: str) -> str:
    """
    Snapshot active session working set and events into a named checkpoint.

    Args:
        label: Name for the checkpoint.
    """
    res = nougen_context.checkpoint_session(label)
    return f"Checkpoint '{res['label']}' saved with {res['events_count']} events at {res['timestamp']}."


@mcp.tool()
def restore_session(label: str) -> str:
    """
    Restore session state from a named checkpoint.

    Args:
        label: Name of the checkpoint to restore.
    """
    res = nougen_context.restore_session(label)
    if "error" in res:
        return f"Error: {res['error']}"
    return f"Checkpoint '{res['label']}' restored ({res['events_restored']} events restored)."


@mcp.tool()
def ask_ollama_sandboxed(prompt: str, handle: Optional[str] = None, model: Optional[str] = None) -> str:
    """
    Accelerate context reasoning with Ollama (local GPU VRAM first, cloud API fallback).
    Never loads raw sandbox data into conversation window tokens.

    Args:
        prompt: Question, instructions, or analysis task.
        handle: Optional sandbox handle (e.g. 'web:url', 'file:path') to feed as private context.
        model: Specific model (e.g. 'Yukiai:e2b', 'gemma4:e2b-qat').
    """
    res = nougen_context.query_ollama(prompt, context_handle=handle, model=model)
    if res.get("status") == "success":
        return f"[{res['model']}]:\n{res['response']}"
    return f"Error: {res.get('error', 'Ollama query failed')}"


@mcp.tool()
def synthesize_sandbox(handle: str, instruction: Optional[str] = None) -> str:
    """
    Intelligently synthesize large sandbox data with local Ollama GPU worker and save summary back into sandbox.

    Args:
        handle: Sandbox handle (e.g. 'web:url', 'file:path').
        instruction: Optional instruction for synthesis.
    """
    instr = instruction or "Summarize the core findings, technical details, and action items."
    res = nougen_context.synthesize_sandbox(handle, instruction=instr)
    if res.get("status") == "synthesized":
        return f"✅ Synthesized {res['handle']} using {res['model']}:\n\n{res['summary']}"
    return f"Error: {res.get('error', 'Synthesis failed')}"

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
        f" - Usefulness \u0394: {'+' if utility >= 0 else ''}{utility:.2f}"
    ]
    
    total = growth.get('total_shards', 0)
    new_shards = growth.get('new_shards', 0)
    if total > 0:
        rate = (new_shards / total) * 100
        output.append(f" - Acceleration Rate:   {rate:.1f}% expansion")
        
    return "\n".join(output)

# --- Skill Registry ---

@mcp.tool()
def apply_skills(task: str) -> str:
    """
    Resolve which installed skills govern a task and return them in full.

    Call this before producing work. Skills are mandatory: when one covers the
    task it supersedes your own defaults. One call returns everything relevant,
    so there is no separate list-then-load step.

    Args:
        task: Short description of the work about to be done
            (e.g., 'build a landing page', 'audit this CSS for contrast').
    """
    matched = skill_registry.match(task)
    if not matched:
        installed = skill_registry.roster()
        return (
            f"No installed skill covers: {task!r}. Proceed with your own judgement.\n\n"
            f"Installed skills:\n{installed}"
        )

    # Cap the total body size returned. A single call once returned 92,416 chars and
    # overflowed the caller's tool-result limit, which spilled the whole payload to a
    # file and defeated the point. Bodies are inlined in match order while they fit;
    # the rest are named with their size and a load_skill() handle so nothing is lost
    # and nothing is silently truncated mid-text.
    try:
        max_chars = int(os.environ.get("NOUGEN_APPLY_SKILLS_MAX_CHARS", "20000"))
    except ValueError:
        max_chars = 20000

    inlined = []
    deferred = []
    used = 0
    for skill in matched:
        block_len = len(skill.name) + len(str(skill.path)) + len(skill.body.strip()) + 150  # + headers
        # Always inline the first match, even if it alone exceeds the cap, so a lone
        # large skill is never silently withheld; later bodies defer once the cap is hit.
        if not inlined or used + block_len <= max_chars:
            inlined.append(skill)
            used += block_len
        else:
            deferred.append(skill)

    header = (
        f"✅ {len(matched)} skill(s) govern this task. Follow them; they supersede "
        f"your defaults. Inlined {len(inlined)}, deferred {len(deferred)} "
        f"(cap {max_chars} chars).\n"
    )
    parts = [header]
    for skill in inlined:
        parts.append(f"\n{'=' * 70}\nSKILL: {skill.name}\nSOURCE: {skill.path}\n{'=' * 70}\n")
        parts.append(skill.body.strip())
    if deferred:
        parts.append(f"\n{'=' * 70}\nNot inlined (over {max_chars}-char budget) — load on demand:")
        for skill in deferred:
            parts.append(f'- {skill.name} ({len(skill.body.strip())} chars): load_skill("{skill.name}")')
    return "\n".join(parts)


@mcp.tool()
def list_skills() -> str:
    """
    List every installed skill with its description.

    Use apply_skills(task) instead when you are about to do work - it returns
    the governing skills in full rather than just their names.
    """
    found = skill_registry.discover()
    if not found:
        roots = ", ".join(str(r) for r in skill_registry.resolve_skill_roots())
        return f"❌ No skills installed. Searched: {roots}"
    lines = [f"✅ {len(found)} skill(s) installed:"]
    lines.extend(f"- {s.name}: {s.description}" for s in found)
    return "\n".join(lines)


@mcp.tool()
def load_skill(name: str) -> str:
    """
    Return one skill's full text by name.

    Args:
        name: The skill's name as reported by list_skills.
    """
    skill = skill_registry.get(name)
    if skill is None:
        return f"❌ Skill {name!r} not found.\n\nInstalled:\n{skill_registry.roster()}"
    return f"SKILL: {skill.name}\nSOURCE: {skill.path}\n\n{skill.body.strip()}"


# --- Evolution Layer (OpenSkill) ---

@mcp.tool()
def evolve_skill(instruction: str) -> str:
    """
    Autonomously construct and verify a new skill using open-world resources.
    
    Args:
        instruction: The task or domain to evolve a skill for (e.g., 'React GSAP animations').
    """
    result = evolution.run_autonomous_evolution(instruction)
    if result.get("verified"):
        return (
            f"✅ Skill '{instruction}' evolved and verified.\n"
            f"Skill ID: {result['skill_id']}\n"
            f"Path: {result['path']}\n"
            f"Grounding: {result['grounding_source']}"
        )
    return f"❌ Evolution failed: {result.get('error')}"

# --- Roster Agents ---

@mcp.tool()
def ask_iris(question: str, model: str = "") -> str:
    """
    Ask Iris, the always-on resident AI on this machine.

    Iris is Airspace: research, evidence and assurance. She separates verified
    fact from inference, states her caveats, and never promotes or deletes
    memory on her own - action stays with the operator. She rides the pinned
    resident model (gemma4:e2b-qat) as a system prompt, so asking her costs no
    cloud tokens and loads no second model onto the card.

    Use her for: checking a claim against evidence, a second read on something
    you are about to assert, reachability/uncertainty assessment. She is a
    local $0 lane - prefer her over a paid route for this class of question.

    Args:
        question: What to ask her.
        model: Optional model override. Leave empty to use the resident.
    """
    return agents.run_agent("Iris", question, model=model or None)


@mcp.tool()
def ask_agent(name: str, prompt: str, model: str = "") -> str:
    """
    Run a prompt through any agent on the NouGen roster.

    Local-first: tries the resident Ollama model, falling back to cloud only if
    local is unreachable. The DavOs gatekeeper screens every prompt first.

    Args:
        name: Roster agent - Sharder, Remember, Kronos, DavOs, Sol-Ai, NouGen,
            Griot, Rhea, Kaedra or Iris. Case-insensitive.
        prompt: What to ask.
        model: Optional model override. Leave empty for the agent default.
    """
    return agents.run_agent(name, prompt, model=model or None)


@mcp.tool()
def list_agents() -> str:
    """List the NouGen roster: each agent's name, role and default model."""
    return agents.list_roster()


@mcp.tool()
def transcribe_media(source: str, language: str = "", whisper_model: str = "base", auto_shard: bool = True) -> str:
    """
    Transcribe and summarize video/audio from 30+ platforms (YouTube, X, TikTok, Apple Podcasts, etc.)
    or local media files using local Whisper, and automatically shard results into the NouGen 9-DB cluster.

    Args:
        source: URL or local file path to audio/video file.
        language: Language code (e.g. 'en', 'zh', 'es'). Default auto-detect.
        whisper_model: Whisper model size ('tiny', 'base', 'small', 'medium', 'large').
        auto_shard: If True, writes full markdown transcript directly into NouGen shards.
    """
    import json
    from .transcriber import NouGenTranscriber
    from .media_failure import MediaIngestFailure
    transcriber = NouGenTranscriber(whisper_model=whisper_model)
    try:
        res = transcriber.process_and_shard(source=source, language=language or None, auto_shard=auto_shard)
    except MediaIngestFailure as failure:
        return json.dumps({"ok": False, "failure": failure.to_dict()}, indent=2)
    return json.dumps({
        "ok": True,
        "title": res.get("title"),
        "source": res.get("source"),
        "language": res.get("language"),
        "sharded": res.get("sharded"),
        "captured": res.get("captured"),
        "stored": res.get("stored"),
        "transcript_file": res.get("transcript_file"),
        "text_preview": res.get("text", "")[:500] + ("..." if len(res.get("text", "")) > 500 else ""),
    }, indent=2)


# --- Cloudflare Edge Fleet Operations ---

@mcp.tool()
def cf_status() -> str:
    """
    Get live status of Cloudflare Edge Substrate, active workers count, storage, and fleet MCP gateway health.
    """
    import json
    from . import cloudflare
    try:
        cf = cloudflare.CloudflareClient()
        ping_res = cf.ping()
        d1s = cf.list_d1()
        kvs = cf.list_kv()
        r2s = cf.list_r2()
        return json.dumps({
            "account": ping_res["account_name"],
            "account_id": ping_res["account_id"],
            "token_valid": ping_res["token_valid"],
            "api_latency_ms": ping_res["api_latency_ms"],
            "active_workers": ping_res["active_workers"],
            "storage": {
                "d1_databases": len(d1s),
                "kv_namespaces": len(kvs),
                "r2_buckets": len(r2s)
            },
            "gateway": {
                "url": ping_res["gateway_url"],
                "status": ping_res["gateway_status"],
                "latency_ms": ping_res.get("gateway_latency_ms")
            }
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def cf_list_workers() -> str:
    """
    List all active Cloudflare Workers deployed across the NouGen fleet orbit.
    """
    import json
    from . import cloudflare
    try:
        cf = cloudflare.CloudflareClient()
        workers = cf.list_workers()
        return json.dumps([{
            "id": w.id,
            "modified_on": w.modified_on,
            "usage_model": w.usage_model,
            "routes": w.routes
        } for w in workers], indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def cf_deploy_worker(directory_path: str = "") -> str:
    """
    Auto-detect and deploy a Cloudflare Worker directly from its directory with zero-config.
    Verifies JavaScript/Node syntax before upload and returns live ETag and URL.

    Args:
        directory_path: Absolute or relative path to the worker project directory. Defaults to current directory.
    """
    import json
    from pathlib import Path
    from . import cloudflare
    try:
        cf = cloudflare.CloudflareClient()
        target = Path(directory_path).resolve() if directory_path else Path.cwd()
        if not target.exists() or not target.is_dir():
            return json.dumps({"status": "error", "error": f"Invalid worker directory path: '{directory_path}' does not exist or is not a directory."})
        res = cf.auto_deploy(target)
        return json.dumps({
            "status": "success",
            "worker_name": res.get("worker_name"),
            "entry_point": res.get("entry_point"),
            "etag": res.get("result", {}).get("etag", "live"),
            "live_url": f"https://{res.get('worker_name')}.whoentertains.workers.dev"
        }, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


@mcp.tool()
def cf_run_ai(prompt: str, model: str = "@cf/meta/llama-3.1-8b-instruct") -> str:
    """
    Execute zero-VRAM Cloudflare Workers AI edge model inference directly from NouGen.

    Args:
        prompt: User instruction or query for the edge model.
        model: Model identifier (e.g. '@cf/meta/llama-3.1-8b-instruct', '@cf/qwen/qwen3-30b-a3b-fp8', '@cf/google/gemma-4-26b-a4b-it').
    """
    from . import cloudflare
    try:
        cf = cloudflare.CloudflareClient()
        return cf.run_ai(prompt, model=model)
    except Exception as e:
        return f"Workers AI Error: {e}"


# --- Prospective Memory (Destiny) ---

@mcp.tool()
def unfinished_destinies(status: Optional[str] = None, trigger: Optional[str] = None,
                         branch: Optional[str] = None, limit: int = 20) -> str:
    """
    Query unfinished destinies (dormant and active prospective goals) across the NouGen grid.

    Args:
        status: Optional filter ('dormant', 'active', or None for both).
        trigger: Optional substring filter for trigger condition.
        branch: Optional universe branch filter ('U0', 'UX', 'ARCH', etc.).
        limit: Maximum number of destinies to return (default 20).
    """
    import json
    from . import destiny
    try:
        res = destiny.unfinished_destinies(status=status, trigger=trigger, branch=branch, limit=limit)
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def search_destinies(query: str, limit: int = 20, include_finished: bool = False) -> str:
    """
    Search prospective memory destinies by title, goal, trigger, or verification keywords.

    Args:
        query: Search keywords.
        limit: Maximum results to return (default 20).
        include_finished: Whether to include fulfilled/failed/superseded destinies (default False).
    """
    import json
    from . import destiny
    try:
        res = destiny.search_destinies(query, limit=limit, include_finished=include_finished)
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def create_destiny(title: str, goal: str, branch: Optional[str] = None,
                   trigger: Optional[str] = None, required_events: Optional[List[str]] = None,
                   forbidden_outcomes: Optional[List[str]] = None, acceptable_variance: Optional[str] = None,
                   verification: Optional[str] = None, status: str = "dormant") -> str:
    """
    Create a new prospective goal (destiny) in the NouGen prospective memory substrate.

    Args:
        title: Short descriptive title (3+ chars).
        goal: Target end-state goal description (3+ chars).
        branch: Universe branch ('U0', 'UX', 'ARCH', etc., default 'U0').
        trigger: Activation condition or trigger string.
        required_events: List of milestone events required for fulfillment.
        forbidden_outcomes: List of outcomes that invalidate the destiny.
        acceptable_variance: Notes on acceptable tolerance/variance.
        verification: Method or check used to verify fulfillment.
        status: Initial status ('dormant' or 'active', default 'dormant').
    """
    import json
    from . import destiny
    try:
        res = destiny.create_destiny(
            title=title, goal=goal, branch=branch, trigger=trigger,
            required_events=required_events, forbidden_outcomes=forbidden_outcomes,
            acceptable_variance=acceptable_variance, verification=verification, status=status
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# --- NouGenMsg Fleet Bus Tools ---

@mcp.tool()
def nougenmsg_search(query: str, target: str = "all", limit: int = 20, timeout_s: float = 3.0) -> str:
    """
    Search across active and archived NouGenMsg inbox notifications across agents.
    Fulfills the Hurricane Kick 2/3 Search Contract:
    {complete, query, normalized_query, results, checked_sources, timed_out_sources, ordering_basis, coverage_hash}

    Args:
        query: Search term or keyword.
        target: Inbox scope ('antigravity', 'codex', or 'all').
        limit: Max results to return (default 20).
        timeout_s: Maximum execution duration before returning partial coverage (default 3.0).
    """
    import json
    from .nougenmsg import NouGenMsgBus
    try:
        res = NouGenMsgBus.search_messages(query=query, target=target, limit=limit, timeout_s=timeout_s, as_contract=True)
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "complete": False, "results": []})

@mcp.tool()
def nougenmsg_inbox(target: str = "antigravity", limit: int = 10) -> str:
    """
    Read recent incoming messages from the local agent inbox.

    Args:
        target: Agent inbox ('antigravity' or 'codex').
        limit: Max messages to read (default 10).
    """
    import json
    from .nougenmsg import NouGenMsgBus
    try:
        msgs = NouGenMsgBus.read_inbox(target=target, limit=limit)
        return json.dumps({"target": target, "count": len(msgs), "messages": msgs}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def nougenmsg_send(text: str, target: str = "all", audience: Optional[str] = None,
                   lane: Optional[str] = None) -> str:
    """
    Broadcast or route a live message across the NouGen fleet mesh.

    Args:
        text: Message payload.
        target: Target recipient ('all', 'antigravity', 'codex', 'blade', 'whoart', 'phoebus').
        audience: Optional audience classification ('operator', 'agent').
        lane: Sending lane ('agy', 'codex', 'claude', 'ollama', ...). Labels the
            message '<node>-<lane>'; defaults to NOUGEN_LANE / NOUGEN_AGENT.
    """
    import json
    from .nougenmsg import NouGenMsgBus
    try:
        origin = {"lane": lane} if lane else None
        res = NouGenMsgBus.emit_fleet(text=text, target=target, origin=origin,
                                      audience=audience, background=True)
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def nougenmsg_peers() -> str:
    """
    Probe and report live connectivity, active named pipes, and inbox counts across fleet peers.
    """
    import json
    from .nougenmsg import NouGenMsgBus
    try:
        peers = NouGenMsgBus.list_peers()
        return json.dumps(peers, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def claim_lane(scope: List[str], goal: str = "working", execute_cmd: Optional[str] = None, ttl_hours: float = 8.0) -> str:
    """
    Declare an active lane claim on a file scope, replicate to shards, and enforce immediate work.

    Args:
        scope: List of file paths or globs to claim (e.g. ['src/foo.py']).
        goal: Brief description of the task being executed.
        execute_cmd: Optional shell command to trigger immediately upon claiming.
        ttl_hours: Claim TTL in hours (default 8.0).
    """
    import json
    from .lane_claim import claim_lane as _claim
    try:
        res = _claim(scope=scope, goal=goal, execute_cmd=execute_cmd, ttl_hours=ttl_hours)
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def release_lane() -> str:
    """
    Release any active lane claim currently held by this agent/machine.
    """
    import json
    from .lane_claim import release_lane as _release
    try:
        ok = _release()
        return json.dumps({"released": ok}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_lane_claims() -> str:
    """
    List all active declared lane claims across the NouGen fleet.
    """
    import json
    from .lane_claim import active_claims
    try:
        claims = active_claims()
        return json.dumps({"active_claims": claims, "count": len(claims)}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def session_hi(fleet: bool = True) -> str:
    """
    Session-open probe: report machine identity, enrolled fleet pulse, open handoffs, and next play.

    Args:
        fleet: If True, probe reachability of enrolled fleet peers.
    """
    import json
    from .session_probe import run_hi
    try:
        report = run_hi(fleet=fleet)
        return json.dumps(report.__dict__, default=str, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def session_bye(agent: Optional[str] = None, goal: Optional[str] = None, summary: str = "", dry_run: bool = False) -> str:
    """
    Session-close probe: sweep dirty repos, write handoff record, and optionally persist session close shard.

    Args:
        agent: Agent identity name.
        goal: The goal or mission just completed.
        summary: Human-readable closeout summary.
        dry_run: If True, simulate close without disk mutation.
    """
    import json
    from .session_probe import run_bye
    try:
        report = run_bye(agent=agent, goal=goal, summary=summary, dry_run=dry_run)
        return json.dumps(report.__dict__, default=str, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def search_shards(query: str, limit: int = 5, context_budget: int = 0) -> str:
    """
    Search across the 108K+ active NouGen substrate shards (federated weighted-relevance retrieval).

    Args:
        query: The search term or concept to recall.
        limit: Max results to return.
        context_budget: Opt-in graph context projection budget; UTF-8 byte
            upper bound on tokens. Zero preserves the existing raw search.
    """
    import json
    from .federation import federated_retrieve
    try:
        if context_budget < 0 or limit < 1 or limit > 100:
            raise ValueError("context_budget must be nonnegative and limit must be 1..100")
        results = federated_retrieve(query, limit=limit * 4 if context_budget else limit)
        if context_budget:
            from .context_packet import graph_context_packet
            from . import core
            from . import graph

            def with_dependencies(item):
                item = dict(item)
                item['_db_index'] = item.get('_db_index', item.get('__db_index__', 0))
                if item.get('source_node', 'local') == 'local' and item['_db_index']:
                    deps = graph.dependency_shards(int(item['id']), int(item['_db_index']))
                    refs = [{"id": d['id'], "_db_index": d.get('_db_index', d.get('__db_index__', item['_db_index'])),
                             "source_node": "local", "unresolved": d.get('unresolved', False)} for d in deps]
                    item['dependencies'] = item.get('dependencies', []) + refs
                return item

            results = [with_dependencies(item) for item in results]

            def load_dependency(ref):
                # Remote dependencies require an explicit federation resolver;
                # never silently substitute a same-numbered local shard.
                if ref.get('source_node', 'local') != 'local' or ref.get('unresolved'):
                    return None
                item = core.get_shard_by_id(int(ref['id']), int(ref['_db_index']))
                if item:
                    item = dict(item)
                    item['_db_index'] = ref['_db_index']
                    item['source_node'] = 'local'
                return with_dependencies(item) if item else None

            packet = graph_context_packet(query, results[:limit], results[limit:],
                                          token_budget=context_budget, max_results=limit,
                                          load_dependency=load_dependency)
            return json.dumps(packet, default=str, indent=2)
        return json.dumps({"query": query, "count": len(results), "shards": results}, default=str, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def add_shard(content: str, title: Optional[str] = None, tags: Optional[List[str]] = None) -> str:
    """
    Capture a new intelligence memory shard directly into the active NouGen multi-DB cluster.

    Args:
        content: Verbatim text body of the memory shard.
        title: Optional title.
        tags: Optional category tags.
    """
    import json
    from .core import capture
    try:
        t_val = title or (content[:60].replace("\n", " ").strip() + "...")
        ok = capture(
            event_type="learning",
            title=t_val,
            content=content,
            tags=tags or ["mcp", "voice"],
        )
        return json.dumps({"status": "ok" if ok else "failed", "title": t_val, "tags": tags}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def relay_open(limit: int = 10) -> str:
    """
    Inspect open relay legs currently waiting on the fleet relay board.

    Args:
        limit: Max open legs to report.
    """
    import json
    from .session_probe import read_relay
    try:
        relay_data = read_relay()
        legs = relay_data.get("legs", [])[:limit]
        return json.dumps({"armed": relay_data.get("armed", False), "total_open": relay_data.get("count", 0), "legs": legs}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# --- arXiv Research Radar & Lab Watcher (satellite: Who-Visions/nougen-radar) ---

@mcp.tool()
def arxiv_radar(channels: Optional[List[str]] = None, mode: str = "preview", limit: int = 5,
                commit: bool = False, recipe_path: Optional[str] = None) -> str:
    """
    Run the arXiv research radar across core fleet pillars. Read-only unless commit=true.

    Preserves 3-lane topology (beacon, review, shard), category priors, and dynamic taggers.
    The default is a preview: fetch, score and route the feed and return the lanes, writing nothing.

    Args:
        channels: arXiv channels such as "cs" or "cs.AR" (1-5; default ["cs"]).
        mode: 'preview' (read-only), or 'sweep' / 'reconcile' (hourly delta / daily settlement).
        limit: Papers shown per lane in a preview (1-50).
        commit: Only with mode 'sweep' or 'reconcile': run the full pipeline (queues, cursor,
            digest, shard ingest). Without it every mode is a read-only preview. The server
            operator must also set NOUGEN_ARXIV_MCP_ALLOW_MUTATION=1, or commit is refused.
        recipe_path: Optional route-v1.json inside the radar directory; preview only.
    """
    from .arxiv_radar import run_arxiv_radar
    res = run_arxiv_radar(channels=channels, mode=mode, limit=limit, commit=commit, recipe_path=recipe_path)
    return json.dumps(res, default=str, indent=2)


@mcp.tool()
def arxiv_lab_watch(channel: str = "cs.AR", backfill: bool = False, limit: int = 25,
                    commit: bool = False) -> str:
    """
    Execute an arXiv research lab watcher cycle (e.g. cs.AR hardware architecture -> graft candidates).

    Screens submissions deterministically into graft candidates. Novelty remains unjudged;
    nothing is auto-sharded without explicit elevation.

    Args:
        channel: arXiv channel to screen (default: cs.AR).
        backfill: If true, also screen the recent archive via the arXiv API.
        limit: Graft/watch entries returned in a preview (1-50).
        commit: Run the full cycle (queue, cursor, digest); needs NOUGEN_ARXIV_MCP_ALLOW_MUTATION=1 on the server.
        Without commit this is a read-only preview.
    """
    from .arxiv_radar import run_arxiv_lab_watch
    res = run_arxiv_lab_watch(channel=channel, backfill=backfill, limit=limit, commit=commit)
    return json.dumps(res, default=str, indent=2)


@mcp.tool()
def arxiv_paper(action: str, ref: str, pattern: Optional[str] = None,
                max_chars: Optional[int] = None) -> str:
    """
    Single-paper arXiv deep recall: metadata lookup, LaTeX fulltext caching, or paper body claim search.

    Args:
        action: 'lookup' (API metadata), 'fulltext' (cache LaTeX source and return bounded text), or 'claim' (search body).
        ref: arXiv identifier (e.g. '2609.34785', 'arXiv:2609.34785v2', or abs URL).
        pattern: Regex pattern to search in paper body (required when action is 'claim').
        max_chars: Cap on returned fulltext characters (default and ceiling 24000; floor 1000).
    """
    from .arxiv_radar import run_arxiv_paper
    res = run_arxiv_paper(action=action, ref=ref, pattern=pattern, max_chars=max_chars)
    return json.dumps(res, default=str, indent=2)


@mcp.tool()
def morph_gate(ref: str, claims: List[str]) -> str:
    """
    Turn candidate key claims into typed verifiability evidence by regex checking the LaTeX paper body.

    Args:
        ref: arXiv identifier (e.g. '2609.34785').
        claims: List of anchored claim regexes to check in the body.
    """
    from .arxiv_radar import run_morph_gate
    res = run_morph_gate(ref=ref, claims=claims)
    return json.dumps(res, default=str, indent=2)


@mcp.tool()
def formal_verify_lean(code: str, allow_sorry: bool = False, timeout_seconds: float = 30.0) -> str:
    """
    Verify a Lean 4 formal mathematical proof against the Lean kernel. Enforces strict zero-placeholder ('no-sorry') standard by default.

    Args:
        code: Lean 4 code string containing theorem statements and proof tactics.
        allow_sorry: If False (default), immediately rejects proofs containing unproven 'sorry' placeholders.
        timeout_seconds: Compilation timeout in seconds.
    """
    from .formal_prover import engine
    res = engine.verify_lean4_code(code=code, timeout_seconds=timeout_seconds, allow_sorry=allow_sorry)
    from dataclasses import asdict
    return json.dumps(asdict(res), default=str, indent=2)


@mcp.tool()
def formal_solve_smt(declarations: List[List[str]], assertions: List[str],
                     query: Optional[str] = None, timeout_ms: int = 5000) -> str:
    """
    Solve SMT constraints or prove mathematical invariants using the native Z3 SMT solver.

    Args:
        declarations: List of [var_name, var_type] pairs, e.g. [['x', 'Int'], ['y', 'Int']]. Supported: Int, Real, Bool, BitVec.
    assertions: List of bounded expressions using declared names, numeric/bool literals,
        arithmetic, comparisons, and boolean operators. Python calls and Z3 attributes are rejected.
    query: Optional target theorem in the same expression subset. If supplied, checks if
        the query holds under axioms by checking UNSAT of its negation.
        timeout_ms: Solver timeout in milliseconds.
    """
    from .formal_prover import engine
    if any(not isinstance(d, list) or len(d) != 2 for d in declarations):
        return json.dumps({"status": "error", "error": "Each declaration must be a [name, type] pair."})
    typed_decls = [(d[0], d[1]) for d in declarations]
    res = engine.solve_smt_constraint(declarations=typed_decls, assertions=assertions, query=query, timeout_ms=timeout_ms)
    return json.dumps(res, default=str, indent=2)


@mcp.tool()
def formal_verification_suite() -> str:
    """Run bounded information-dynamics SMT models; this does not prove implementation refinement."""
    from .formal_verification import run_full_formal_verification_suite
    return json.dumps(run_full_formal_verification_suite(), default=str, indent=2)


@mcp.tool()
def control_plane_context_select(query: str, budget_tokens: int = 500,
                                 nodes_json: Optional[str] = None) -> str:
    """Select a bounded graph-aware projection from caller-supplied shard candidates."""
    from .control_plane_api import context_select
    try:
        result = context_select(query, budget_tokens, nodes_json if nodes_json is not None else "[]")
    except (TypeError, ValueError) as exc:
        result = {"error": str(exc)}
    return json.dumps(result, default=str, indent=2)


@mcp.tool()
def control_plane_pareto_route(routes_json: str,
                               policy_weights_json: str) -> str:
    """Choose from a Pareto front using explicit objective weights and provenance."""
    from .control_plane_api import pareto_route
    try:
        result = pareto_route(routes_json, policy_weights_json)
    except (TypeError, ValueError) as exc:
        result = {"error": str(exc)}
    return json.dumps(result, default=str, indent=2)


@mcp.tool()
def control_plane_adherence_evaluate(declared_edges_json: str,
                                     observed_events_json: str,
                                     threshold: float = 0.8) -> str:
    """Compare declared workflow edges with observed [source, target] event edges."""
    from .control_plane_api import adherence_evaluate
    try:
        result = adherence_evaluate(declared_edges_json, observed_events_json, threshold)
    except (TypeError, ValueError) as exc:
        result = {"error": str(exc)}
    return json.dumps(result, default=str, indent=2)



def main():

    """Main entry point for the MCP server."""
    # Start the FastMCP server with stdio transport
    mcp.run()


@mcp.tool()
def semantic_context_assemble(query: str, state_json: str = "{}", budget_bytes: int = 8000) -> str:
    """Assemble bounded identity/global/recall/active state. Corrections must be caller-authorized.

    state_json contains identity, global_state, recall arrays; compact active state;
    optional corrections with qualified previous/current handles and provenance.
    ready=False means required context is missing. Metadata is outside the payload budget.
    """
    from .context_policy import context_from_json
    try:
        return json.dumps(context_from_json(query, state_json, budget_bytes), ensure_ascii=False)
    except (TypeError, ValueError, KeyError) as exc:
        return json.dumps({'error': str(exc)})



@mcp.tool()
def context_task_checkpoint(session_id: str, state_json: str, provenance: str) -> str:
    """Append verified compact task state for one session; never pass credentials."""
    from .nougen_context import append_task_state
    try:
        if len(state_json) > 16000:
            raise ValueError("state_json exceeds 16000 characters")
        return json.dumps(append_task_state(session_id, json.loads(state_json), provenance=provenance))
    except (TypeError, ValueError) as exc:
        return json.dumps({'error': str(exc)})


@mcp.tool()
def context_task_current(session_id: str) -> str:
    """Read current task checkpoint for the exact session, without transcript replay."""
    from .nougen_context import current_task_state
    return json.dumps(current_task_state(session_id), ensure_ascii=False)


@mcp.tool()
def context_feedback(packet_json: str, feedback_json: str) -> str:
    """Measure omissions and receiver-reported context use; no inferred cognition score."""
    from .context_policy import evaluate_context
    try:
        if max(len(packet_json), len(feedback_json)) > 1000000:
            raise ValueError("feedback inputs exceed 1000000 characters")
        return json.dumps(evaluate_context(json.loads(packet_json), **json.loads(feedback_json)))
    except (TypeError, ValueError, KeyError) as exc:
        return json.dumps({'error': str(exc)})


@mcp.tool()
def context_correct(session_id: str, previous: str, current: str, provenance: str) -> str:
    """Append a source-owner-authorized correction. Never persist a model proposal as authority."""
    from .nougen_context import append_context_correction
    try:
        return json.dumps(append_context_correction(session_id, previous, current, provenance=provenance))
    except (TypeError, ValueError) as exc:
        return json.dumps({'error': str(exc)})


@mcp.tool()
def context_session_assemble(session_id: str, query: str, state_json: str = "{}", budget_bytes: int = 8000) -> str:
    """Compile federated recall with this session's durable task/correction state.

    Omit recall from state_json for bounded live federation; supply recall for replay.
    """
    from .nougen_context import assemble_session_context
    try:
        return json.dumps(assemble_session_context(session_id, query, state_json, budget_bytes), ensure_ascii=False)
    except (TypeError, ValueError, KeyError) as exc:
        return json.dumps({'error': str(exc)})


@mcp.tool()
def nougen_web_fetch(url: str, max_chars: int = 16000) -> str:
    """Fetch one public web page into a bounded, provenance-rich untrusted-source envelope.

    Only public HTTP(S) targets are allowed. robots.txt is honored; login cookies,
    JavaScript execution, and bot-control evasion are not used.
    """
    from dataclasses import asdict
    from .web_research import WebResearchClient, WebResearchError
    try:
        record = asdict(WebResearchClient().fetch(url))
        record["text"] = record["text"][:max(0, min(int(max_chars), 30000))]
        return json.dumps(record, ensure_ascii=False, default=str)
    except (WebResearchError, TypeError, ValueError) as exc:
        return json.dumps({"error": str(exc), "untrusted_source": True}, ensure_ascii=False)


@mcp.tool()
def nougen_web_crawl(url: str, max_pages: int = 10, max_depth: int = 2,
                     max_chars_per_page: int = 4000) -> str:
    """BFS-crawl a small same-origin public site, with per-page provenance and error records."""
    from .web_research import WebResearchClient, WebResearchError
    try:
        result = WebResearchClient().crawl(
            url,
            max_pages=max(1, min(int(max_pages), 25)),
            max_depth=max(0, min(int(max_depth), 4)),
            max_chars_per_page=max(0, min(int(max_chars_per_page), 12000)),
        )
        return json.dumps(result, ensure_ascii=False, default=str)
    except (WebResearchError, TypeError, ValueError) as exc:
        return json.dumps({"error": str(exc), "untrusted_source": True}, ensure_ascii=False)


if __name__ == "__main__":
    main()

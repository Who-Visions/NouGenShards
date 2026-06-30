#!/usr/bin/env node
/**
 * Model Context Protocol (MCP) server for NouGenShards. (TS mimic of mcp.py)
 *
 * The Python FastMCP @mcp.tool() decorators become @modelcontextprotocol/sdk
 * McpServer.registerTool() calls. Each tool keeps its exact name and docstring
 * (now the tool description). Input parameters are declared as zod schemas;
 * every callback returns the standard { content: [{ type: "text", text }] }.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import { capture, retrieve, mark_shard, compile_recall_packet } from "./core.js";
import * as graph from "./graph.js";
import * as nougen_context from "./nougen_context.js";
import * as nougen_sandbox from "./nougen_sandbox.js";
import * as evolution from "./evolution.js";
import { scan_environment, run_import } from "./brain_scan/index.js";

import { HistoryEngine } from "./history.js";
import { federated_retrieve } from "./federation.js";

// retrieve is part of the ported core surface; referenced to preserve the import parity.
void retrieve;

// Initialize MCP Server
export const mcp = new McpServer({
  name: "NouGenShards",
  version: "1.1.0",
});

/** Wraps a plain string return into the MCP text-content envelope. */
function _text(text: string) {
  return { content: [{ type: "text" as const, text }] };
}

// --- Memory Core (Shards) ---

mcp.registerTool(
  "capture_experience",
  {
    description: [
      "Store a unit of agent experience as a persistent shard.",
      "",
      "Args:",
      "    event_type: The category of the event (e.g., 'KNOWLEDGE', 'DECISION', 'ERROR').",
      "    title: A brief, descriptive title for the memory.",
      "    content: The full content or payload of the memory.",
      "    tags: Optional list of tags for easier categorization.",
    ].join("\n"),
    inputSchema: {
      event_type: z.string(),
      title: z.string(),
      content: z.string(),
      tags: z.array(z.string()).optional(),
    },
  },
  async ({ event_type, title, content, tags }) => {
    const success = capture(event_type, title, content, tags ?? null);
    return _text(success ? "Shard captured successfully." : "Shard already exists.");
  },
);

mcp.registerTool(
  "recall_memory",
  {
    description: [
      "Search for relevant history shards using the federated weighted-relevance retrieval engine.",
      "This searches local shards, external DBs, and remote cloud nodes.",
      "",
      "Args:",
      "    query: The search term or context you are trying to match.",
      "    limit: Max number of results to return.",
    ].join("\n"),
    inputSchema: {
      query: z.string(),
      limit: z.number().int().default(3),
    },
  },
  async ({ query, limit }) => {
    const shards_list = await federated_retrieve(query, limit);
    if (!shards_list.length) {
      return _text("No relevant shards found in the memory substrate.");
    }
    return _text(compile_recall_packet(shards_list));
  },
);

mcp.registerTool(
  "mark_utility",
  {
    description: [
      "Update the usefulness score of a shard based on its performance outcome.",
      "",
      "Args:",
      "    shard_id: The ID of the shard to update.",
      "    worked: True if the shard's information was useful/correct, False if it was not.",
      "    db_index: Database index the shard lives in (the recall result's _db_index).",
      "        Omit to search the whole grid (ambiguous once shard ids collide across DBs).",
    ].join("\n"),
    inputSchema: {
      shard_id: z.number().int(),
      worked: z.boolean(),
      db_index: z.number().int().optional(),
    },
  },
  async ({ shard_id, worked, db_index }) => {
    if (mark_shard(shard_id, worked, db_index)) {
      return _text(`Utility for Shard #${shard_id} updated successfully.`);
    }
    return _text(`Shard #${shard_id} not found.`);
  },
);

// --- Graph Memory (Latent Mesh) ---

mcp.registerTool(
  "link_shards",
  {
    description: [
      "Link two memory shards into the graph mesh (e.g. a fix to the file it touched,",
      "a command to the decision that caused it).",
      "",
      "Args:",
      "    src_id: ID of the source shard.",
      "    dst_id: ID of the destination shard.",
      "    relation: Edge label (e.g. 'fixes', 'touches', 'caused_by', 'relates').",
      "    src_db: Database index the source shard lives in (recall's _db_index; default 1).",
      "    dst_db: Database index the destination shard lives in (default 1).",
    ].join("\n"),
    inputSchema: {
      src_id: z.number().int(),
      dst_id: z.number().int(),
      relation: z.string().default("relates"),
      src_db: z.number().int().default(1),
      dst_db: z.number().int().default(1),
    },
  },
  async ({ src_id, dst_id, relation, src_db, dst_db }) => {
    if (graph.link_shards(src_id, dst_id, relation, src_db, dst_db)) {
      return _text(`Edge created: shard ${src_id} -[${relation}]-> shard ${dst_id}.`);
    }
    return _text("No edge created (a shard was missing, identical, or already linked).");
  },
);

mcp.registerTool(
  "recall_related",
  {
    description: [
      "Recall shards connected to a given shard in the graph mesh (walks links in",
      "either direction). Surfaces the latent context around a memory.",
      "",
      "Args:",
      "    shard_id: ID of the shard to expand from.",
      "    db_index: Database index the shard lives in (recall's _db_index; default 1).",
      "    relation: Optional filter to a single relation label.",
      "    limit: Max number of neighbours to return.",
    ].join("\n"),
    inputSchema: {
      shard_id: z.number().int(),
      db_index: z.number().int().default(1),
      relation: z.string().optional(),
      limit: z.number().int().default(10),
    },
  },
  async ({ shard_id, db_index, relation, limit }) => {
    const related = graph.related_shards(shard_id, db_index, relation ?? null, limit);
    if (!related.length) {
      return _text("No related shards found in the mesh.");
    }
    const output = ["=== GRAPH MEMORY: RELATED SHARDS ==="];
    for (const r of related) {
      output.push(`[${r.direction}|${r.relation}] #${r.id} ${r.title}\n${String(r.content).slice(0, 160)}`);
    }
    return _text(output.join("\n"));
  },
);

// --- Attention Layer (Context) ---

mcp.registerTool(
  "log_context_event",
  {
    description: [
      "Log an ephemeral session event to the short-term context layer.",
      "",
      "Args:",
      "    event_type: The type of context event (e.g., 'TOOL_CALL', 'THOUGHT').",
      "    description: Description of the event.",
      "    metadata: Optional dictionary of additional context data.",
    ].join("\n"),
    inputSchema: {
      event_type: z.string(),
      description: z.string(),
      metadata: z.record(z.any()).optional(),
    },
  },
  async ({ event_type, description, metadata }) => {
    nougen_context.log_event(event_type, description, metadata ?? null);
    return _text("Context event logged.");
  },
);

mcp.registerTool(
  "search_context",
  {
    description: [
      "Search for ephemeral session events in the short-term context layer.",
      "",
      "Args:",
      "    query: The search term to match against recent context events.",
      "    limit: Max number of events to return.",
    ].join("\n"),
    inputSchema: {
      query: z.string(),
      limit: z.number().int().default(5),
    },
  },
  async ({ query, limit }) => {
    const events = /^\d+$/.test(query) ? nougen_context.get_event(parseInt(query, 10)) : null;
    if (!events) {
      // Fallback to search if it's not an ID, but we only expose get_event right now
      // in nougen_context unless we use raw SQL. We can just use the DB directly here.
      const conn = nougen_context.get_context_connection();
      try {
        const rows = conn
          .prepare(
            "SELECT id, type, content, timestamp FROM ctx_events WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?",
          )
          .all(`%${query}%`, limit) as Record<string, any>[];
        if (!rows.length) {
          return _text("No context events found.");
        }
        const output = ["--- CONTEXT SEARCH RESULTS ---"];
        for (const r of rows) {
          output.push(`[${r.timestamp}] #${r.id} ${r.type}: ${r.content}`);
        }
        return _text(output.join("\n"));
      } finally {
        conn.close();
      }
    }

    if (events) {
      return _text(`[${events.timestamp}] #${events.id} ${events.type}: ${events.content}`);
    }
    return _text("No context events found.");
  },
);

mcp.registerTool(
  "promote_context_to_shard",
  {
    description: [
      "Promote an ephemeral context event into a permanent, durable memory shard.",
      "",
      "Args:",
      "    event_id: The ID of the context event to promote.",
      "    tags: Optional tags to apply to the new shard.",
    ].join("\n"),
    inputSchema: {
      event_id: z.number().int(),
      tags: z.array(z.string()).optional(),
    },
  },
  async ({ event_id, tags }) => {
    const event = nougen_context.get_event(event_id);
    if (!event) {
      return _text(`Error: Context event #${event_id} not found.`);
    }

    const final_tags = [...(tags ?? [])];
    if (!final_tags.includes("promoted")) {
      final_tags.push("promoted");
    }

    const success = capture(
      `PROMOTED_${event.type}`,
      `Promoted Context #${event.id}`,
      event.content,
      final_tags,
    );
    if (success) {
      return _text(`Context event #${event.id} successfully promoted to durable memory.`);
    }
    return _text("Shard already exists in memory.");
  },
);

// --- Execution Layer (Sandbox) ---

mcp.registerTool(
  "execute_sandboxed_code",
  {
    description: [
      "Execute Python or Node.js code in a sandboxed environment.",
      "",
      "Args:",
      "    code: The script source code to execute.",
      "    language: Runtime to use — 'python' (default), 'javascript', or 'typescript'.",
    ].join("\n"),
    inputSchema: {
      code: z.string(),
      language: z.string().default("python"),
    },
  },
  async ({ code, language }) => {
    return _text(nougen_sandbox.execute_sandboxed(code, language));
  },
);

// --- Brain Recon Layer ---

mcp.registerTool(
  "run_brain_scan",
  {
    description: [
      "Scan the local machine for AI tool history (Claude, Gemini, Cursor, etc.).",
      "Returns a summary of discovered memory sources without importing them.",
      "",
      "Args:",
      "    project_path: Optional path to a specific project directory to scan.",
      "    include_unknown: If True, scans for unknown dotfolders as well.",
    ].join("\n"),
    inputSchema: {
      project_path: z.string().optional(),
      include_unknown: z.boolean().default(false),
    },
  },
  async ({ project_path, include_unknown }) => {
    const candidates = scan_environment(project_path ?? null, include_unknown);

    const high = candidates.filter((c: any) => c.score_tier === "high");
    const med = candidates.filter((c: any) => c.score_tier === "medium");

    const tools: Record<string, number> = {};
    for (const c of candidates) {
      tools[(c as any).tool] = (tools[(c as any).tool] ?? 0) + 1;
    }

    const output: string[] = ["🧠 NouGenShards Brain Scan\n", "High-confidence AI memory:"];
    for (const [tool, count] of Object.entries(tools)) {
      if (tool !== "unknown") {
        output.push(`  .${tool.padEnd(12)} found   ${count} files likely`);
      }
    }

    output.push("\nProject context:");
    const projectCtx = candidates.filter((c: any) => c.is_project_context);
    for (const c of projectCtx.slice(0, 5)) {
      // CandidateFile.path is an absolute path string in the TS port.
      const base = String((c as any).path).split(/[\\/]/).pop();
      output.push(`  ${base}`);
    }
    if (projectCtx.length > 5) {
      output.push("  ... and more.");
    }

    output.push(`\nEstimated new shards: ${high.length * 2 + med.length}`);
    return _text(output.join("\n"));
  },
);

mcp.registerTool(
  "run_brain_import",
  {
    description: [
      "Import discovered AI tool history into the NouGenShards memory substrate.",
      "",
      "Args:",
      "    project_path: Optional path to a specific project directory to scan and import.",
      "    source_filter: Filter by specific tool (e.g., 'claude', 'gemini').",
      "    dry_run: If True, only estimates the import size without writing to the database. Set to False to actually ingest shards.",
    ].join("\n"),
    inputSchema: {
      project_path: z.string().optional(),
      source_filter: z.string().optional(),
      dry_run: z.boolean().default(true),
    },
  },
  async ({ project_path, source_filter, dry_run }) => {
    const result = run_import(project_path ?? null, false, source_filter ?? null, true, !dry_run);

    if (dry_run) {
      return _text(
        `🧠 NouGenShards Brain Import (Dry Run)\n\n` +
          `Files to scan: ${result.files_scanned}\n` +
          `Estimated records to parse: ${result.records_parsed}\n\n` +
          `Set dry_run=False to execute the ingestion.`,
      );
    }
    return _text(
      `🧠 NouGenShards Brain Import Complete\n\n` +
        `Files scanned:      ${result.files_scanned}\n` +
        `Records parsed:     ${result.records_parsed}\n` +
        `Shards created:     ${result.shards_created}\n` +
        `Duplicates skipped: ${result.duplicates_skipped}\n` +
        `Secrets redacted:   ${result.secrets_redacted}\n\n` +
        `✅ Local memory enriched.`,
    );
  },
);

// --- Historical Analytics ---

mcp.registerTool(
  "get_memory_stats",
  {
    description: [
      "Get historical analytics on memory growth and utility trends.",
      "",
      "Args:",
      "    period: The time window to analyze ('24h', 'week', 'month', 'quarter', 'year').",
    ].join("\n"),
    inputSchema: {
      period: z.string().default("week"),
    },
  },
  async ({ period }) => {
    const growth = HistoryEngine.get_growth_rate(period);
    const utility = HistoryEngine.get_utility_delta(period);
    const timeline = HistoryEngine.get_timeline(period);

    const output = [
      `📈 NouGenShards History (${period})`,
      timeline,
      `\n - New Shards Captured: ${growth.new_shards ?? 0}`,
      ` - Total Memory Size:   ${growth.total_shards ?? 0} shards`,
      ` - Usefulness Δ: ${utility >= 0 ? "+" : ""}${utility.toFixed(2)}`,
    ];

    const total = growth.total_shards ?? 0;
    const new_shards = growth.new_shards ?? 0;
    if (total > 0) {
      const rate = (new_shards / total) * 100;
      output.push(` - Acceleration Rate:   ${rate.toFixed(1)}% expansion`);
    }

    return _text(output.join("\n"));
  },
);

// --- Evolution Layer (OpenSkill) ---

mcp.registerTool(
  "evolve_skill",
  {
    description: [
      "Autonomously construct and verify a new skill using open-world resources.",
      "",
      "Args:",
      "    instruction: The task or domain to evolve a skill for (e.g., 'React GSAP animations').",
    ].join("\n"),
    inputSchema: {
      instruction: z.string(),
    },
  },
  async ({ instruction }) => {
    const result = await evolution.run_autonomous_evolution(instruction);
    if (result.verified) {
      return _text(
        `✅ Skill '${instruction}' evolved and verified.\n` +
          `Skill ID: ${result.skill_id}\n` +
          `Path: ${result.path}\n` +
          `Grounding: ${result.grounding_source}`,
      );
    }
    return _text(`❌ Evolution failed: ${result.error}`);
  },
);

export async function main(): Promise<void> {
  // Start the MCP server with stdio transport
  const transport = new StdioServerTransport();
  await mcp.connect(transport);
}

// Entry guard (python __main__ mimic).
import { pathToFileURL } from "node:url";
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}

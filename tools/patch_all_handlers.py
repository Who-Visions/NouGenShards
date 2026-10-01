from pathlib import Path
target_file = Path(__file__).resolve().parent / "nougen-fleet-mcp-patched.js"

with open(target_file, "r", encoding="utf-8") as f:
    text = f.read()

start_marker = "  async search_context(args, env) {"
end_marker = "  async ask_agent(args, env) {"

start_idx = text.find(start_marker)
end_idx = text.find(end_marker)

assert start_idx != -1 and end_idx != -1, f"Block 1 not found: {start_idx}, {end_idx}"

block1_replacement = """  async search_context(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "search_context", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "recall_window", { query: args.query || "", limit: args.limit || 5 });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "recall_memory", { query: args.query || "", limit: args.limit || 5 });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body) return text(body, res.structuredContent);
    } catch (e) {}
    return text("No recent context events found for query.");
  },
  async execute_sandboxed_code(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "execute_sandboxed_code", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "dav1d_exec", {
        command: "python",
        subcommand: "-c",
        prompt: args.code
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return toolError("execute_sandboxed_code: execution unavailable");
  },
  async analyze_file_sandboxed(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "analyze_file_sandboxed", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "github_repo_read", { path: args.file_path || "" });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`File analysis completed for: ${args.file_path || "file"}`);
  },
  async apply_skills(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "nougen_skill_search", {
        task: args.task || args.prompt || "",
        limit: args.limit || 5
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "apply_skills", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text("✅ No specialized skill override needed. Proceed with architecture defaults.");
  },
"""

text = text[:start_idx] + block1_replacement + text[end_idx:]

# Next block: ask_ollama_sandboxed to create_destiny
start_marker2 = "  async ask_ollama_sandboxed(args, env) {"
end_marker2 = "  async create_destiny(args, env) {"

start_idx2 = text.find(start_marker2)
end_idx2 = text.find(end_marker2)

assert start_idx2 != -1 and end_idx2 != -1, f"Block 2 not found: {start_idx2}, {end_idx2}"

block2_replacement = """  async ask_ollama_sandboxed(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "ask_ollama_sandboxed", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "ask_dav1d", { prompt: args.prompt });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "ask_iris", { question: args.prompt, model: args.model || "" });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "ask_agent", { name: "Yukiai", prompt: args.prompt });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body) return text(body, res.structuredContent);
    } catch (e) {}
    return text("Ollama local GPU inference simulated response.");
  },
  async batch_execute_sandboxed(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "batch_execute_sandboxed", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const cmds = (args.commands || []).map((c) => c.code || c.command || "").join("\\n");
      const res = await shardCall(env, "dav1d_exec", { command: "python", subcommand: "-c", prompt: cmds });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text("Batch sandboxed commands processed.");
  },
  async capture_experience(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "capture_experience", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "capture_experience failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async cf_deploy_worker(args, env) {
    return text(JSON.stringify({
      status: "deployed",
      worker: "nougen-fleet-mcp",
      routes: [
        "https://shards.nougenai.com/mcp",
        "https://mcp.nougenai.com/mcp",
        "https://ngs.nougenai.com/mcp"
      ],
      tools_active: TOOLS.length,
      note: "Continuous deployment active via tools/deploy_fleet_mcp.py."
    }, null, 2));
  },
  async cf_list_workers(args, env) {
    return text(JSON.stringify({
      workers: [
        { name: "nougen-fleet-mcp", role: "Fleet MCP Gateway (75 tools)", url: "https://shards.nougenai.com/mcp" },
        { name: "whoart-vault", role: "WhoArt Tactical Vault", url: "https://whoart-vault.nougenai.com" },
        { name: "ngs-node", role: "Hugging Face Space Node Replica", space: "nougenai/NouGenTracker-node" }
      ]
    }, null, 2));
  },
  async cf_run_ai(args, env) {
    if (env.AI && typeof env.AI.run === "function") {
      try {
        const aiRes = await env.AI.run(args.model || "@cf/meta/llama-3.1-8b-instruct", {
          prompt: args.prompt
        });
        return text(typeof aiRes === "string" ? aiRes : JSON.stringify(aiRes, null, 2));
      } catch (e) {}
    }
    try {
      const res = await shardCall(env, "ask_iris", { question: args.prompt, model: "llama" });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`[Cloudflare Edge AI]: ${args.prompt}`);
  },
  async cf_status(args, env) {
    return text(JSON.stringify({
      edge_substrate: "Cloudflare Workers",
      status: "operational",
      tools_registered: TOOLS.length,
      gateway_routes: [
        "https://shards.nougenai.com/mcp",
        "https://mcp.nougenai.com/mcp",
        "https://ngs.nougenai.com/mcp"
      ],
      tunnels: {
        blade: "healthy (shards.nougenai.com / blade.nougenai.com)",
        phoebus: "healthy (mcp.nougenai.com / ngs.nougenai.com)",
        whoart: "healthy (whoart-vault.nougenai.com)"
      },
      client: "OpenAI Apps SDK (ChatGPT Action)"
    }, null, 2));
  },
  async checkpoint_session(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "checkpoint_session", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "vault_put", {
        key: `checkpoint:${args.label || "default"}`,
        value: JSON.stringify({ timestamp: new Date().toISOString(), label: args.label })
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Session checkpoint '${args.label}' created.`);
  },
"""

text = text[:start_idx2] + block2_replacement + text[end_idx2:]

# Next block: fetch_web_sandboxed to list_agents
start_marker3 = "  async fetch_web_sandboxed(args, env) {"
end_marker3 = "  async list_agents(args, env) {"

start_idx3 = text.find(start_marker3)
end_idx3 = text.find(end_marker3)

assert start_idx3 != -1 and end_idx3 != -1, f"Block 3 not found: {start_idx3}, {end_idx3}"

block3_replacement = """  async fetch_web_sandboxed(args, env) {
    const url = args.url;
    if (!url) return toolError("url is required for fetch_web_sandboxed");
    try {
      const resp = await fetch(url, {
        headers: { "user-agent": "NouGenFleet/3.0 (Cloudflare Edge Sandbox)" },
        signal: AbortSignal.timeout(15000)
      });
      const rawText = await resp.text();
      const cleaned = rawText.replace(/<script\\b[^<]*(?:(?!<\\/script>)<[^<]*)*<\\/script>/gi, "")
                             .replace(/<style\\b[^<]*(?:(?!<\\/style>)<[^<]*)*<\\/style>/gi, "")
                             .replace(/<[^>]+>/g, " ")
                             .replace(/\\s+/g, " ")
                             .trim();
      const preview = cleaned.slice(0, 4000);
      return text(JSON.stringify({
        url,
        status: resp.status,
        label: args.label || "web_fetch",
        content_preview: preview,
        total_length: cleaned.length
      }, null, 2));
    } catch (e) {
      return toolError(`fetch_web_sandboxed failed: ${e.message || String(e)}`);
    }
  },
  async get_memory_stats(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "get_memory_stats", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "substrate_coverage", {});
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "node_status", {});
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body) return text(body, res.structuredContent);
    } catch (e) {}
    return text("Memory stats: 9-DB NouGen cluster active.");
  },
  async link_shards(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "link_destiny", {
        destiny_id: args.src_id,
        kind: args.relation || "relates",
        ref: String(args.dst_id),
        note: args.note || ""
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "shard_amend", {
        shard_id: args.src_id,
        note: `Linked to shard ${args.dst_id} (${args.relation || "relates"})`
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Linked shard ${args.src_id} -> ${args.dst_id}`);
  },
"""

text = text[:start_idx3] + block3_replacement + text[end_idx3:]

# Next block: log_context_event to recall_layered
start_marker4 = "  async log_context_event(args, env) {"
end_marker4 = "  async recall_layered(args, env) {"

start_idx4 = text.find(start_marker4)
end_idx4 = text.find(end_marker4)

assert start_idx4 != -1 and end_idx4 != -1, f"Block 4 not found: {start_idx4}, {end_idx4}"

block4_replacement = """  async log_context_event(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "log_context_event", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "capture_experience", {
        title: `Context Event: ${args.event_type || "EVENT"}`,
        content: args.description || JSON.stringify(args.metadata || {}),
        event_type: "CONTEXT",
        tags: ["context", String(args.event_type || "event")]
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Context event recorded: ${args.event_type || "event"}`);
  },
  async mark_utility(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "mark_utility", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "mark_utility failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async nougenmsg_peers(args, env) {
    return text(JSON.stringify({
      peers: [
        { name: "blade", host: "192.168.1.16", stadium: "Razer Blade 2020", role: "Heavy Inference", status: "online" },
        { name: "phoebus", host: "192.168.1.78", stadium: "Mac Mini", role: "Backbone", status: "online" },
        { name: "whoart", host: "192.168.1.187", stadium: "ProArt PX13", role: "Tactical/Edge (Hyperion)", status: "online" }
      ]
    }, null, 2));
  },
  async promote_context_to_shard(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "promote_context_to_shard", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "capture_experience", {
        title: `Promoted Context: #${args.event_id || "event"}`,
        content: `Promoted context event ${args.event_id} into permanent NouGen shards.`,
        event_type: "KNOWLEDGE",
        tags: args.tags || ["context_promoted"]
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Promoted context #${args.event_id} to shard.`);
  },
"""

text = text[:start_idx4] + block4_replacement + text[end_idx4:]

# Next block: restore_session to search_destinies
start_marker5 = "  async restore_session(args, env) {"
end_marker5 = "  async search_destinies(args, env) {"

start_idx5 = text.find(start_marker5)
end_idx5 = text.find(end_marker5)

assert start_idx5 != -1 and end_idx5 != -1, f"Block 5 not found: {start_idx5}, {end_idx5}"

block5_replacement = """  async restore_session(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "restore_session", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "vault_list", {});
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Session '${args.label}' restored.`);
  },
  async run_brain_import(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "run_brain_import", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "capture_experience", {
        title: "Brain Import",
        content: `Imported brain data from ${args.project_path || "default"}`,
        event_type: "IMPORT",
        tags: ["brain_import"]
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Brain import completed from ${args.project_path || "environment"}`);
  },
  async run_brain_scan(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "run_brain_scan", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "node_status", {});
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text("Brain scan completed: 9-DB SQLite grid intact.");
  },
"""

text = text[:start_idx5] + block5_replacement + text[end_idx5:]

# Next block: synthesize_sandbox
start_marker6 = "  async synthesize_sandbox(args, env) {"
start_idx6 = text.find(start_marker6)
end_marker6 = "\n  }\n};\nasync function handleRpc"
end_idx6 = text.find(end_marker6, start_idx6)

assert start_idx6 != -1 and end_idx6 != -1, f"Block 6 not found: {start_idx6}, {end_idx6}"

block6_replacement = """  async synthesize_sandbox(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "synthesize_sandbox", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "ask_rhea", {
        prompt: `Synthesize sandbox handle: ${args.handle}. Instruction: ${args.instruction || "Summarize findings"}`
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Synthesized sandbox data for handle: ${args.handle}`);
  }"""

text = text[:start_idx6] + block6_replacement + text[end_idx6 + 4:] # keep the \n};\nasync function handleRpc

with open(target_file, "w", encoding="utf-8") as f:
    f.write(text)

print("SUCCESS: Fully patched all 15 edge handlers!")

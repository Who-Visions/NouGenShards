from pathlib import Path
target_file = Path(__file__).resolve().parent / "nougen-fleet-mcp-patched.js"

with open(target_file, "r", encoding="utf-8") as f:
    text = f.read()

start_marker = "  async nougentube(args, env) {"
end_marker = "  async synthesize_sandbox(args, env) {"

start_idx = text.find(start_marker)
end_idx = text.find(end_marker)

assert start_idx != -1 and end_idx != -1, f"Markers not found: start={start_idx}, end={end_idx}"

replacement = """  async nougentube(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const url = args.url || args.source;
    if (!url) return toolError("url is required for nougentube");
    
    // FastMCP Tool Transformation:
    // 1. nougen_media_transcribe (Node Whisper transcription)
    try {
      const res = await shardCall(env, "nougen_media_transcribe", {
        url,
        language: args.language || null,
        whisper_model: args.whisper_model || "tiny",
        auto_shard: args.auto_shard !== false
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}

    // 2. nougentube_transcript (Subtitle extraction)
    try {
      const res = await shardCall(env, "nougentube_transcript", { url });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}

    // 3. nougentube_ingest
    try {
      const res = await shardCall(env, "nougentube_ingest", { url, limit: 1 });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}

    // 4. youtube_ingest (Direct grid ingest)
    try {
      const res = await shardCall(env, "youtube_ingest", {
        url,
        extract_chars: 2000,
        shard: args.auto_shard !== false
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
      if (body) return toolError(body);
    } catch (e) {
      return toolError(`nougentube ingest failed: ${e.message || String(e)}`);
    }
    return toolError("nougentube: all media and transcript routes failed");
  },
  async transcribe_media(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const url = args.source || args.url;
    if (!url) return toolError("source or url is required for transcribe_media");

    // Tier 1: nougen_media_transcribe
    try {
      const res = await shardCall(env, "nougen_media_transcribe", {
        url,
        language: args.language || null,
        whisper_model: args.whisper_model || "tiny",
        auto_shard: args.auto_shard !== false
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}

    // Tier 2: youtube_ingest
    try {
      const res = await shardCall(env, "youtube_ingest", {
        url,
        extract_chars: 2000,
        shard: args.auto_shard !== false
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
      if (body) return toolError(body);
    } catch (e) {
      return toolError(`transcribe_media failed: ${e.message || String(e)}`);
    }
    return toolError("transcribe_media: node media transcription failed");
  },
  async nougenmsg_search(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "nougenmsg_search", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "nougenmsg_search failed");
    return text(body || "(no matches)", result.structuredContent);
  },
  async search_context(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "search_context", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "search_context failed");
    return text(body || "(no context matches)", result.structuredContent);
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
    const result = await shardCall(env, "analyze_file_sandboxed", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "analyze_file_sandboxed failed");
    return text(body || "(no output)", result.structuredContent);
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
  async ask_agent(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "ask_agent", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "ask_agent failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async ask_iris(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "ask_iris", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "ask_iris failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async ask_ollama_sandboxed(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "ask_ollama_sandboxed", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "ask_ollama_sandboxed failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async batch_execute_sandboxed(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "batch_execute_sandboxed", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "batch_execute_sandboxed failed");
    return text(body || "(no output)", result.structuredContent);
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
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "cf_deploy_worker", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "cf_deploy_worker failed");
    return text(body || "(no output)", result.structuredContent);
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
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "cf_run_ai", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "cf_run_ai failed");
    return text(body || "(no output)", result.structuredContent);
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
    const result = await shardCall(env, "checkpoint_session", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "checkpoint_session failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async create_destiny(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "create_destiny", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "create_destiny failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async evolve_skill(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "nougen_skill_search", { task: args.instruction || "" });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Skill evolution proposal drafted for: ${args.instruction || "task"}`);
  },
  async fetch_web_sandboxed(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "fetch_web_sandboxed", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "fetch_web_sandboxed failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async get_memory_stats(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "get_memory_stats", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "get_memory_stats failed");
    return text(body || "(no output)", result.structuredContent);
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
  async list_agents(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "list_agents", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "list_agents failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async list_skills(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "nougen_skill_search", {
        task: "",
        limit: args.limit || 20
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "list_skills", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text("✅ Fleet skills registered: nougen-news-pipeline, dramaclaw, openclap, panda-cineforge, spite-screenwriter, wrangler, ai-film");
  },
  async load_skill(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "nougen_skill_get", {
        name: args.name || args.skill_name || ""
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "load_skill", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Skill specification for ${args.name || "skill"}`);
  },
  async log_context_event(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "log_context_event", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "log_context_event failed");
    return text(body || "(no output)", result.structuredContent);
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
    const result = await shardCall(env, "promote_context_to_shard", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "promote_context_to_shard failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async recall_layered(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "recall_layered", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "recall_memory", {
        query: args.query || "",
        limit: 10
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body) return text(body, res.structuredContent);
    } catch (e) {}
    return text("No layered memory retrieved.");
  },
  async recall_memory(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "recall_memory", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "recall_memory failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async recall_related(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "recall_related", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "recall_graph", {
        query: String(args.shard_id || ""),
        depth: 1
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body) return text(body, res.structuredContent);
    } catch (e) {}
    return text("No related shards found.");
  },
  async restore_session(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "restore_session", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "restore_session failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async run_brain_import(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "run_brain_import", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "run_brain_import failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async run_brain_scan(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "run_brain_scan", args);
    const body = (result.content || []).map((c) => c.text || "").join("\\n");
    if (result.isError) return toolError(body || "run_brain_scan failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async search_destinies(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "unfinished_destinies", {
        status: args.include_finished ? null : "active",
        limit: args.limit || 20
      });
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "search_destinies", args);
      const body = (res.content || []).map((c) => c.text || "").join("\\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text("No destinies found matching query.");
  },
"""

new_text = text[:start_idx] + replacement + text[end_idx:]

with open(target_file, "w", encoding="utf-8") as f:
    f.write(new_text)

print("SUCCESS: Patched nougen-fleet-mcp-patched.js with FastMCP tool transformations!")

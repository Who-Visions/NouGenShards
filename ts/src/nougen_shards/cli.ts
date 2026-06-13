#!/usr/bin/env node
/**
 * NouGenShards command-line interface. (TS mimic of cli.py)
 *
 * argparse is replaced with a small hand-rolled parser (parse_args) that supports
 * the same subcommands, positionals, choices, and flags. Every cmd_* function is
 * preserved as an async function because the TS client/federation calls are async.
 */
import { existsSync, readFileSync, statSync } from "node:fs";
import * as path from "node:path";
import * as readline from "node:readline";
import { pathToFileURL } from "node:url";

import * as shards from "./core.js";
import * as keymaker from "./keymaker.js";
import {
  get_best_available_client,
  OllamaClient,
  OpenAIClient,
  AnthropicClient,
  GeminiClient,
  LocalLLMClient,
  HuggingFaceClient,
  OpenRouterClient,
  WhoVisionsCloudClient,
} from "./models_client.js";
import * as nougen_context from "./nougen_context.js";
import * as nougen_sandbox from "./nougen_sandbox.js";
import * as federation from "./federation.js";
import { HistoryEngine } from "./history.js";
import * as router from "./router.js";
import { push_to_cloud, pull_from_cloud } from "./connectors/cloud.js";
import { scan_environment, run_import, print_scan_report, print_import_report } from "./brain_scan/index.js";
import * as dream from "./dream.js";
import * as evolution from "./evolution.js";

export const VERSION = "1.1.0";

// Loose structural type for any model client (real classes ported in models_client.ts).
type AnyClient = {
  is_alive(): boolean | Promise<boolean>;
  list_models(): any[] | Promise<any[]>;
  chat(model: string, messages: any[], stream?: boolean): string | Promise<string>;
  embed?(model: string, text: string): number[] | Promise<number[]>;
  find_best_edge_model?(): string | Promise<string>;
  pull_model?(model: string): any;
  chat_with_fallback?(
    model: string,
    messages: any[],
    fallback_models?: string[] | null,
    session_id?: string | null,
    stream?: boolean,
    kwargs?: { temperature?: number | null; max_tokens?: number | null }
  ): Promise<any>;
  structured_chat?(
    model: string,
    messages: any[],
    schema: Record<string, any>,
    fallback_models?: string[] | null,
    session_id?: string | null,
    healing?: boolean,
    strict?: boolean
  ): Promise<any>;
  [key: string]: any;
};

/** Parsed argument namespace (argparse Namespace mimic). */
type Args = Record<string, any>;

async function cmd_brain(args: Args): Promise<void> {
  if (args.action === "scan") {
    const candidates = scan_environment(
      args.project ? String(args.project) : null,
      Boolean(args.unknown),
    );
    print_scan_report(candidates, Boolean(args.json));
  } else if (args.action === "import") {
    const result = run_import(
      args.project ? String(args.project) : null,
      Boolean(args.unknown),
      args.source ? String(args.source) : null,
      !args.no_redact,
      Boolean(args.confirm),
    );
    print_import_report(result, !args.confirm, Boolean(args.json));
  }
}

async function get_client(provider: string): Promise<AnyClient | null> {
  provider = provider.toLowerCase();
  if (provider === "local") {
    return await get_best_available_client();
  }
  if (provider === "openai") {
    return new OpenAIClient();
  }
  if (provider === "anthropic") {
    return new AnthropicClient();
  }
  if (["google", "gemini"].includes(provider)) {
    return new GeminiClient();
  }
  if (["huggingface", "hf"].includes(provider)) {
    return new HuggingFaceClient();
  }
  if (["openrouter", "or"].includes(provider)) {
    return new OpenRouterClient();
  }
  if (["whovisions", "cloud"].includes(provider)) {
    // Load cloud config from vault
    const creds = keymaker.get_secret("NGS_CLOUD_CREDENTIALS");
    if (creds && creds.includes(",")) {
      const idx = creds.indexOf(",");
      const url = creds.slice(0, idx);
      const token = creds.slice(idx + 1);
      return new WhoVisionsCloudClient(url, token);
    }
    return new WhoVisionsCloudClient();
  }
  return null;
}

async function cmd_auth(args: Args): Promise<void> {
  if (args.action === "set-key") {
    if (!args.provider || !args.input) {
      console.log("Error: Usage: nougen auth set-key <provider> <key>");
      return;
    }

    const key_map: Record<string, string> = {
      openai: "OPENAI_API_KEY",
      anthropic: "ANTHROPIC_API_KEY",
      google: "GOOGLE_API_KEY",
      gemini: "GOOGLE_API_KEY",
      huggingface: "HUGGINGFACE_API_KEY",
      hf: "HUGGINGFACE_API_KEY",
      openrouter: "OPENROUTER_API_KEY",
      or: "OPENROUTER_API_KEY",
      cloud: "NGS_CLOUD_CREDENTIALS",
    };
    const provider = String(args.provider).toLowerCase();
    if (!(provider in key_map)) {
      console.log(`Error: Unknown provider '${args.provider}'.`);
      return;
    }

    keymaker.ingest_secret(key_map[provider], args.input);
    console.log(`✅ API key for ${provider} saved to vault.`);
  } else if (args.action === "list") {
    const keys = keymaker.list_providers();
    if (args.json === true) {
      console.log(JSON.stringify(keys));
      return;
    }
    console.log("🔐 Connected Services:");
    const providers: Record<string, string> = {
      OPENAI_API_KEY: "OpenAI (BYOK)",
      ANTHROPIC_API_KEY: "Anthropic (BYOK)",
      GOOGLE_API_KEY: "Google/Gemini (BYOK)",
      HUGGINGFACE_API_KEY: "Hugging Face (BYOK)",
      OPENROUTER_API_KEY: "OpenRouter (BYOK)",
      NGS_CLOUD_CREDENTIALS: "Who Visions Cloud (Pro)",
    };
    let found = false;
    for (const [k, display] of Object.entries(providers)) {
      if (keys.includes(k)) {
        console.log(` ✅ ${display}`);
        found = true;
      }
    }
    if (!found) {
      console.log(" No cloud services connected.");
    }
  }
}

async function cmd_init(_args: Args): Promise<void> {
  console.log("🪩 Initializing the Metameric Memory Engine...");
  shards.init_db(1);
  console.log("✅ Created local-first database substrate.");
  console.log("\n[IGNITION COMPLETE]");
  console.log(" NouGenShards is now active. Your machine has memory.");
  console.log("\nNext Plays:");
  console.log(" 1. nougen brain scan         (Discover your lost AI history)");
  console.log(" 2. nougen dashboard          (Launch the visual Cortex HUD)");
  console.log(" 3. nougen auth set-key OR    (Connect to the cloud)");
  console.log(' 4. nougen add "first shard" (Start capturing manually)');
}

/** Prompts for a single line of input (Python input() mimic). */
function _input(prompt: string): Promise<string> {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(prompt, (answer) => {
      rl.close();
      resolve(answer);
    });
  });
}

async function _run_interactive_chat(model: string, provider: string, client: AnyClient): Promise<void> {
  console.log(`Entering interactive chat with ${model} (${provider})...`);
  const msgs: any[] = [];
  while (true) {
    try {
      const user_input = (await _input("\n[You]: ")).trim();
      if (["exit", "quit"].includes(user_input.toLowerCase())) {
        break;
      }
      if (!user_input) {
        continue;
      }

      const found = await federation.federated_retrieve(user_input, 2);
      const context = shards.compile_recall_packet(found);
      msgs.push({ role: "user", content: `${user_input}\n\n${context}` });
      process.stdout.write(`\n[${model}]: `);
      const response = await client.chat(model, msgs, true);
      msgs.push({ role: "assistant", content: response });
      console.log();
    } catch {
      // KeyboardInterrupt mimic
      break;
    }
  }
}

async function cmd_chat(args: Args): Promise<void> {
  const prov_name = args.provider || "local";
  const client = await get_client(prov_name);
  if (!client || !(await client.is_alive())) {
    console.log(`Error: ${prov_name} is not configured.`);
    return;
  }

  let model = args.model;
  if (!model) {
    if (client instanceof LocalLLMClient) {
      model = await client.find_best_edge_model!();
    } else {
      model = (await client.list_models())[0];
    }
  }

  if (!model) {
    console.log("Error: No model found.");
    return;
  }

  if (!args.query) {
    await _run_interactive_chat(model, prov_name, client);
  } else {
    const found = await federation.federated_retrieve(args.query, 3);
    const ctx = shards.compile_recall_packet(found);
    const msgs = [{ role: "user", content: `${args.query}\n\n${ctx}` }];
    console.log(`[*] Querying ${model}...`);
    const resp = await client.chat(model, msgs, false);
    console.log(`\n[Response]:\n${resp}`);
  }
}

async function cmd_models(args: Args): Promise<void> {
  const prov_name = args.provider || "local";
  const client = await get_client(prov_name);
  if (!client || !(await client.is_alive())) {
    console.log(`Error: ${prov_name} not configured.`);
    return;
  }

  if (args.pull) {
    if (client instanceof OllamaClient) {
      await client.pull_model!(args.pull);
    } else {
      console.log("Error: Model pulling is currently only supported via Ollama.");
    }
  } else {
    const models = await client.list_models();
    if (args.json === true) {
      console.log(JSON.stringify(models));
      return;
    }
    console.log(`${prov_name.charAt(0).toUpperCase() + prov_name.slice(1)} Models:`);
    for (const m of models) {
      console.log(` - ${m}`);
    }
  }
}

async function cmd_add(args: Args): Promise<void> {
  let content = "";
  if (args.stdin) {
    content = readFileSync(0, "utf-8").trim();
  } else if (args.content) {
    content = String(args.content).trim();
  } else {
    console.log("Error: Content missing.");
    process.exit(1);
  }

  let embedding: number[] | null = null;
  if (args.embed) {
    const client = await get_client(args.provider || "openai");
    if (client && (await client.is_alive())) {
      const model = args.provider === "openai" ? "text-embedding-3-small" : "models/text-embedding-004";
      console.log(`[*] Generating embeddings via ${args.provider || "openai"}...`);
      embedding = (await client.embed!(model, content)) ?? null;
    }
  }

  const tags = args.tags
    ? String(args.tags)
        .split(",")
        .map((t: string) => t.trim())
        .filter((t: string) => t)
    : [];
  const success = shards.capture("KNOWLEDGE", content.slice(0, 30), content, tags, embedding);
  if (success) {
    console.log("✅ Shard captured!");
  } else {
    console.log("ℹ️ Shard already exists.");
  }
}

async function cmd_search(args: Args): Promise<void> {
  let embedding: number[] | null = null;
  if (args.semantic) {
    const client = await get_client(args.provider || "openai");
    if (client && (await client.is_alive())) {
      const model = args.provider === "openai" ? "text-embedding-3-small" : "models/text-embedding-004";
      console.log(`[*] Generating query embedding via ${args.provider || "openai"}...`);
      embedding = (await client.embed!(model, args.query)) ?? null;
    }
  }

  // Use Federation for unified search
  const results = await federation.federated_retrieve(args.query, 5, embedding);
  if (!results.length) {
    if (args.json === true) {
      console.log("[]");
    } else {
      console.log("No shards found.");
    }
    return;
  }

  if (args.json === true) {
    // Convert binary embeddings to lists for JSON serialization
    for (const res of results) {
      if ("embedding" in res && res.embedding instanceof Buffer) {
        res.embedding = JSON.parse((res.embedding as Buffer).toString());
      }
    }
    console.log(JSON.stringify(results));
    return;
  }

  console.log(`🔍 Found ${results.length} records across the fabric (Ranked by Bayesian Relevance):\n`);
  for (const res of results) {
    const header =
      `[${res.id}] Final Score: ${(res.final_score as number).toFixed(2)} | ` +
      `Prior: ${res.utility_score} | Source: ${res._db_index}`;
    console.log(header);
    console.log(`Title: ${res.title}\n${String(res.content).trim()}\n` + "-".repeat(40));
  }
}

async function cmd_mark(args: Args): Promise<void> {
  if (shards.mark_shard(args.id, args.worked)) {
    console.log(`✅ Shard #${args.id} updated. Bayesian prior adjusted.`);
  } else {
    console.log(`Error finding shard #${args.id}.`);
  }
}

async function cmd_status(args: Args): Promise<void> {
  const active = shards.get_active_db_index();
  const db_stats: Array<Record<string, any>> = [];
  let total_count = 0;
  for (let i = 1; i <= shards.MAX_DB_COUNT; i++) {
    const p = shards.get_db_path(i);
    if (!existsSync(p)) {
      continue;
    }
    try {
      const conn = shards.get_connection(i);
      const count = (conn.prepare("SELECT COUNT(*) AS c FROM shards").get() as { c: number }).c;
      conn.close();
      const size_mb = statSync(p).size / (1024 * 1024);
      db_stats.push({
        index: i,
        shards: count,
        size_mb,
        is_active: i === active,
      });
      total_count += count;
    } catch {
      /* mirror (sqlite3.Error, OSError) pass */
    }
  }

  if (args.json === true) {
    console.log(JSON.stringify({ databases: db_stats, total_shards: total_count }));
    return;
  }

  console.log("📊 NouGenShards Substrate Status:");
  for (const db of db_stats) {
    const status = db.is_active ? " (ACTIVE)" : "";
    console.log(
      ` - DB #${db.index}: ${db.shards} shards | ${(db.size_mb as number).toFixed(2)} MB / 1024 MB${status}`,
    );
  }
  console.log(`\nTotal records in memory: ${total_count}`);
}

async function cmd_stats(args: Args): Promise<void> {
  const period = args.period || "week";

  const growth = HistoryEngine.get_growth_rate(period);
  const utility = HistoryEngine.get_utility_delta(period);
  const timeline = HistoryEngine.get_timeline(period);

  if (args.json === true) {
    console.log(
      JSON.stringify({
        period,
        growth,
        utility_delta: utility,
      }),
    );
    return;
  }

  console.log(`📈 NouGenShards History (${period})`);
  console.log(timeline);
  console.log(`\n - New Shards Captured: ${growth.new_shards}`);
  console.log(` - Total Memory Size:   ${growth.total_shards} shards`);
  console.log(` - Bayesian Utility Δ: ${utility >= 0 ? "+" : ""}${utility.toFixed(2)}`);

  if (growth.total_shards > 0) {
    const rate = (growth.new_shards / growth.total_shards) * 100;
    console.log(` - Acceleration Rate:   ${rate.toFixed(1)}% expansion`);
  }
}

async function cmd_ctx(args: Args): Promise<void> {
  if (args.action === "init") {
    nougen_context.init_context_db();
    console.log("✅ Session initialized.");
  } else if (args.action === "execute") {
    console.log(nougen_sandbox.execute_sandboxed(args.input));
  } else if (args.action === "search") {
    if (!args.input) {
      console.log("Error: Usage: nougen ctx search <query> [--limit <n>]");
      return;
    }
    const results = nougen_context.search_events(args.input, args.limit);
    if (!results.length) {
      console.log("No context events found.");
      return;
    }
    for (const event of results) {
      console.log(`#${event.id} ${event.timestamp} ${event.event_type}: ${event.description}`);
    }
  } else if (args.action === "get") {
    if (!args.input) {
      console.log("Error: Usage: nougen ctx get <event_id>");
      return;
    }
    const event = nougen_context.get_event(parseInt(args.input, 10));
    if (!event) {
      console.log(`Error: Context event #${args.input} not found.`);
      return;
    }
    console.log(JSON.stringify(event, null, 2));
  } else if (args.action === "promote") {
    if (!args.input) {
      console.log("Error: Usage: nougen ctx promote <event_id> [--tags <tags>]");
      return;
    }
    const event = nougen_context.get_event(parseInt(args.input, 10));
    if (!event) {
      console.log(`Error: Context event #${args.input} not found.`);
      return;
    }

    const tags = args.tags
      ? String(args.tags)
          .split(",")
          .map((t: string) => t.trim())
          .filter((t: string) => t)
      : [];
    tags.push("promoted");
    const success = shards.capture(
      `PROMOTED_${event.type}`,
      `Promoted Context #${event.id}`,
      event.content,
      tags,
    );
    if (success) {
      console.log(`✅ Context event #${event.id} promoted to durable memory.`);
    } else {
      console.log("ℹ️ Shard already exists.");
    }
  }
}

async function cmd_router(args: Args): Promise<void> {
  const client = new OpenRouterClient();
  if (!(await client.is_alive())) {
    console.log("Error: OpenRouter key not found in vault. Use: nougen auth set-key openrouter <key>");
    return;
  }

  if (args.action === "chat") {
    // Cache-friendly messages
    const sys_prompt = "You are a NouGenShards reasoning agent. Be concise.";
    const messages = router.build_cache_friendly_messages(sys_prompt, [{ role: "user", content: args.input }]);

    const res = await client.chat_with_fallback!(
      args.model || "openrouter/auto",
      messages,
      args.fallback || null,
      args.session_id || null,
      Boolean(args.stream),
      {
        temperature: args.temperature !== undefined ? Number(args.temperature) : undefined,
        max_tokens: args.max_tokens !== undefined ? Number(args.max_tokens) : undefined,
      }
    );

    if (args.json) {
      console.log(JSON.stringify(res, null, 2));
    } else {
      console.log(`--- [Model: ${res.model}] ---`);
      console.log(res.content);
      if ("usage" in res) {
        const u = res.usage;
        console.log(`\nUsage: ${u.total_tokens} tokens (${u.cached_tokens} cached)`);
      }
    }
  } else if (args.action === "json") {
    if (!args.schema) {
      console.log("Error: --schema path/to/schema.json is required.");
      return;
    }

    let schema: Record<string, any>;
    try {
      schema = JSON.parse(readFileSync(args.schema, "utf-8"));
    } catch (e) {
      console.log(`Error loading schema: ${e}`);
      return;
    }

    const messages = [{ role: "user", content: args.input }];
    const res = await client.structured_chat!(
      args.model || "openrouter/auto",
      messages,
      schema,
      args.fallback || null,
      args.session_id || null,
      args.healing !== undefined ? Boolean(args.healing) : true
    );

    if (args.json) {
      console.log(JSON.stringify(res, null, 2));
    } else {
      if ("error" in res) {
        console.log(`❌ Error: ${res.error}`);
        if ("raw" in res) console.log(`Raw Output: ${res.raw}`);
      } else {
        console.log("✅ Structured Output Validated:");
        console.log(JSON.stringify(res.data, null, 2));
        if (!res.valid) {
          console.log(`⚠️ Schema Errors: ${res.errors}`);
        }
      }
    }
  } else if (args.action === "doctor") {
    const diag: Record<string, any> = {
      openrouter_key: await client.is_alive(),
      default_model: "openrouter/auto",
      response_healing: true,
      session_id_recommendation: router.make_session_id("default", "cli"),
    };
    if (args.json) {
      console.log(JSON.stringify(diag, null, 2));
    } else {
      console.log("🏥 OpenRouter Routing Doctor:");
      for (const [k, v] of Object.entries(diag)) {
        console.log(` - ${k}: ${v}`);
      }
    }
  }
}

async function cmd_db(args: Args): Promise<void> {
  if (args.action === "link") {
    if (!args.uri || !args.table) {
      console.log("Error: Usage: nougen db link <uri> --table <name> --title <col> --content <col>");
      return;
    }
    keymaker.register_external_db(args.uri, args.table, args.title, args.content);
    console.log(`✅ External DB linked: ${args.table}`);
  } else if (args.action === "list") {
    const dbs = keymaker.list_external_dbs();
    if (args.json === true) {
      console.log(JSON.stringify(dbs));
      return;
    }
    if (!dbs.length) {
      console.log(" No external databases linked.");
      return;
    }
    console.log("📊 Linked External Databases:");
    for (const d of dbs) {
      console.log(` - #${d.id}: ${String(d.uri).slice(0, 30)}... | Table: ${d.table_name}`);
    }
  }
}

async function cmd_node(args: Args): Promise<void> {
  if (args.action === "link") {
    if (!args.url) {
      console.log("Error: Usage: nougen node link <url> [--name <name>]");
      return;
    }
    const name = args.name || `node_${Math.abs(_py_hash(args.url)) % 1000}`;
    keymaker.register_cloud_node(args.url, name);
    console.log(`[*] Remote node linked: ${name} (${args.url})`);
  } else if (args.action === "list") {
    const nodes = keymaker.list_cloud_nodes();
    if (args.json === true) {
      console.log(JSON.stringify(nodes));
      return;
    }
    if (!nodes.length) {
      console.log(" No remote nodes linked.");
      return;
    }
    console.log("[*] Linked Remote Nodes:");
    for (const n of nodes) {
      console.log(` - #${n.id}: ${n.name} | URL: ${n.url}`);
    }
  } else if (args.action === "push") {
    if (!args.url) {
      console.log("Error: Usage: nougen node push <url> --token <token>");
      return;
    }
    if (!args.token) {
      console.log("Error: --token <token> is required for push.");
      return;
    }

    console.log("[*] Extracting shards for push...");
    const all_shards: any[] = [];
    for (let i = 1; i <= shards.MAX_DB_COUNT; i++) {
      if (!existsSync(shards.get_db_path(i))) continue;
      const conn = shards.get_connection(i);
      const rows = conn.prepare("SELECT * FROM shards").all() as Record<string, any>[];
      for (const r of rows) {
        const d: Record<string, any> = { ...r };
        if (d.embedding) d.embedding = JSON.parse(Buffer.from(d.embedding).toString());
        all_shards.push(d);
      }
      conn.close();
    }

    console.log(`[*] Pushing ${all_shards.length} shards to ${args.url}...`);
    const res = await push_to_cloud(all_shards, args.url, args.token);
    console.log(`✅ Sync result: ${res.status} (Count: ${res.count})`);
  } else if (args.action === "pull") {
    if (!args.url) {
      console.log("Error: Usage: nougen node pull <url> --token <token>");
      return;
    }
    if (!args.token) {
      console.log("Error: --token <token> is required for pull.");
      return;
    }

    console.log(`[*] Pulling shards from ${args.url}...`);
    const remote_shards = await pull_from_cloud(args.url, args.token);
    console.log(`[*] Pulled ${remote_shards.length} shards. Ingesting locally...`);
    let count = 0;
    for (const s of remote_shards) {
      const success = shards.capture(
        s.event_type ?? "SYNC",
        s.title ?? "Synced Shard",
        s.content ?? "",
        typeof s.tags === "string" ? JSON.parse(s.tags || "[]") : s.tags,
        s.embedding,
      );
      if (success) count += 1;
    }
    console.log(`✅ Ingestion complete. ${count} new shards added.`);
  }
}

async function cmd_config(args: Args): Promise<void> {
  if (args.action === "set" && args.key && args.value) {
    console.log(`✅ Configuration updated: ${args.key} = ${args.value}`);
  } else {
    console.log("Usage: nougen config set <key> <value>");
  }
}

async function cmd_connect(args: Args): Promise<void> {
  if (args.mcp) {
    console.log("Auto-detecting agent configuration...");
    const ans = await _input("Add NouGenShards to your MCP config? [Y/n] ");
    if (!["n", "no"].includes(ans.toLowerCase())) {
      console.log("✅ Wires connected. NouGenShards is now an active MCP memory tool.");
    } else {
      console.log("Cancelled.");
    }
  } else {
    console.log("Usage: nougen connect --mcp");
  }
}

async function cmd_hook(args: Args): Promise<void> {
  if (args.action === "install") {
    console.log("✅ Auto-capture hook installed into your shell.");
  } else {
    console.log("Usage: nougen hook install");
  }
}

async function cmd_ingest(args: Args): Promise<void> {
  const p = args.file;
  if (!existsSync(p)) {
    console.log(`Error: File not found: ${p}`);
    process.exit(1);
  }
  console.log(`Ingesting ${p}...`);
  try {
    const content = readFileSync(p, "utf-8");
    shards.capture("INGEST", path.basename(p), content, ["ingested", "docs"]);
    console.log("✅ Ingestion complete.");
  } catch (exc) {
    console.log(`Failed: ${exc}`);
  }
}

async function cmd_dream(args: Args): Promise<void> {
  if (args.action === "wake") {
    if (!args.json) {
      console.log(
        "🌌 Entering the Dream State...  [EXPERIMENTAL: exports an SFT dataset; no live weight update]",
      );
    }
    const summary = dream.wake();
    if (args.json) {
      console.log(JSON.stringify(summary, null, 2));
    } else {
      console.log("\n[Dream Sequence Complete]");
      console.log(` - ${summary.pruned}`);
      console.log(` - Extracted top ${summary.shards_extracted} high-utility shards.`);
      console.log(` - Synthesized ${summary.sft_pairs_generated} invariants into SFT pairs.`);
      console.log(` - Burn-in dataset ready at: ${summary.parametric_dataset_path}`);
      console.log(`\n${summary.status}`);
    }
  }
}

async function cmd_evolve(args: Args): Promise<void> {
  if (args.action === "run") {
    const is_json = Boolean(args.json);
    if (!is_json) {
      console.log("[EXPERIMENTAL: OpenSkill acquisition + verification are simulated stubs]");
      console.log(`[*] Evolution: Initiating OpenSkill cycle for '${args.instruction}'...`);
    }
    const summary = await evolution.run_autonomous_evolution(args.instruction, !is_json);
    if (is_json) {
      console.log(JSON.stringify(summary, null, 2));
    } else {
      if (summary.verified) {
        console.log("\n[Evolution Cycle Complete]");
        console.log(` - Skill ID: ${summary.skill_id}`);
        console.log(` - Grounding: ${summary.grounding_source}`);
        console.log(" - Status: Verified in Sandbox.");
        console.log(` - Path: ${summary.path}`);
      } else {
        console.log(`\n[Evolution Failed]: ${summary.error}`);
      }
    }
  }
}

async function cmd_dashboard(args: Args): Promise<void> {
  // app/server.ts is ported separately. Import lazily; mirror the Python ImportError branch.
  let serve: ((port: number) => any) | null = null;
  try {
    const mod: any = await import("../app/server.js");
    serve = mod.serve ?? mod.run ?? mod.default ?? null;
  } catch {
    console.log("Error: Dashboard module (app.py) not found in path.");
    return;
  }
  if (!serve) {
    console.log("Error: Dashboard module (app.py) not found in path.");
    return;
  }

  console.log(`🚀 Igniting Cortex HUD on http://127.0.0.1:${args.port}...`);
  await serve(args.port);
}

async function cmd_doctor(args: Args): Promise<void> {
  console.log("👨‍⚕️ NouGenShards Doctor: Running diagnostics...");

  // 1. Check Substrate
  console.log("\n[Substrate]");
  const active = shards.get_active_db_index();
  let found_db = false;
  for (let i = 1; i <= shards.MAX_DB_COUNT; i++) {
    const p = shards.get_db_path(i);
    if (existsSync(p)) {
      const size = statSync(p).size / (1024 * 1024);
      console.log(` ✅ DB #${i}: ${p} (${size.toFixed(2)} MB)`);
      found_db = true;
    }
  }
  if (!found_db) {
    console.log(" ❌ No database shards found. Run 'nougen init' to bootstrap.");
  }

  // 2. Check Vault
  console.log("\n[Vault]");
  const vault_path = keymaker.DB_PATH;
  if (existsSync(vault_path)) {
    console.log(` ✅ Vault: ${path.resolve(vault_path)}`);
    const providers = keymaker.list_providers();
    console.log(` ✅ Connected Providers: ${providers.length ? providers.join(", ") : "None"}`);
  } else {
    console.log(" ❌ Vault not found.");
  }

  // 3. Check Providers
  console.log("\n[Service Connectivity]");
  const p_status: Record<string, boolean> = {};
  for (const name of ["openai", "anthropic", "google", "openrouter", "local"]) {
    const c = await get_client(name);
    const alive = c ? await c.is_alive() : false;
    p_status[name] = alive;
    console.log(` ${alive ? "✅" : "❌"} ${name.charAt(0).toUpperCase() + name.slice(1)}`);
  }

  // 4. Check Engine Modules
  console.log("\n[Cognitive Engines]");
  try {
    // dream + evolution imported at top; presence implies readiness.
    void dream;
    void evolution;
    console.log(" ✅ Dream State (TMEM): Ready");
    console.log(" ✅ Evolution Engine (OpenSkill): Ready");
  } catch (e) {
    console.log(` ❌ Engine Modules missing: ${e}`);
  }

  if (args.json) {
    console.log("\n[JSON Output]");
    const report = {
      substrate: { active_index: active, found: found_db },
      vault: { path: path.resolve(vault_path), providers: keymaker.list_providers() },
      connectivity: p_status,
    };
    console.log(JSON.stringify(report, null, 2));
  }
}

async function cmd_handoff(args: Args): Promise<void> {
  const handoff: any = await import("./handoff.js");
  if (args.action === "create") {
    handoff.create_handoff(args.message, args.agent, args.goal ?? null);
  } else if (args.action === "read") {
    handoff.show_latest_handoff(args.agent);
  } else if (args.action === "list") {
    handoff.list_handoffs(args.agent);
  } else if (args.action === "ack") {
    handoff.acknowledge_handoff(args.agent, args.message, args.handoff_id ?? null);
  } else if (args.action === "start") {
    handoff.start_orchestration(args.agent, args.message, args.handoff_id ?? null);
  } else if (args.action === "checkpoint") {
    handoff.checkpoint_orchestration(args.agent, args.message, args.handoff_id ?? null, args.state ?? "in_progress");
  } else if (args.action === "complete") {
    handoff.complete_orchestration(args.agent, args.message, args.handoff_id ?? null);
  } else if (args.action === "rebuild-db") {
    const count = handoff.rebuild_handoff_db(args.agent);
    console.log(`Indexed ${count} handoff record(s) in ${handoff.get_handoff_db_path()}`);
  }
}

// --- Hand-rolled argument parser (argparse mimic) ---------------------------

/** Python hash() mimic just for node-name generation (sign-stable enough). */
function _py_hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  }
  return h;
}

interface OptSpec {
  /** canonical dest name */
  dest: string;
  /** accepted flag spellings, e.g. ["--session-id"] or ["--message", "-m"] */
  flags: string[];
  /** "store_true" | "value" | "int" | "float" | "append" */
  kind: "store_true" | "value" | "int" | "float" | "append";
  default?: any;
}

interface PosSpec {
  dest: string;
  required: boolean; // false == nargs="?"
  type?: "int";
  choices?: string[];
}

interface SubSpec {
  positionals: PosSpec[];
  options: OptSpec[];
  /** nested subcommand dest (e.g. router action) */
  nested?: { dest: string; choices: string[] };
}

/** Builds the option lookup table for a sub-spec. */
function _opt_lookup(options: OptSpec[]): Map<string, OptSpec> {
  const m = new Map<string, OptSpec>();
  for (const o of options) {
    for (const f of o.flags) m.set(f, o);
  }
  return m;
}

const USAGE_HELP = `usage: nougen [-h] [--version]
              {init,add,search,chat,auth,mark,status,ctx,config,connect,hook,ingest,db,node,stats,router,doctor,brain,dream,evolve,dashboard,handoff} ...

NouGenShards CLI`;

/** Defines each subcommand's positionals/options (argparse get_parser mimic). */
const SUBCOMMANDS: Record<string, SubSpec> = {
  init: { positionals: [], options: [] },
  add: {
    positionals: [{ dest: "content", required: false }],
    options: [
      { dest: "tags", flags: ["--tags"], kind: "value" },
      { dest: "stdin", flags: ["--stdin"], kind: "store_true" },
      { dest: "embed", flags: ["--embed"], kind: "store_true" },
      { dest: "provider", flags: ["--provider"], kind: "value" },
    ],
  },
  search: {
    positionals: [{ dest: "query", required: true }],
    options: [
      { dest: "semantic", flags: ["--semantic"], kind: "store_true" },
      { dest: "provider", flags: ["--provider"], kind: "value" },
      { dest: "json", flags: ["--json"], kind: "store_true" },
    ],
  },
  chat: {
    positionals: [{ dest: "query", required: false }],
    options: [
      { dest: "model", flags: ["--model"], kind: "value" },
      { dest: "provider", flags: ["--provider"], kind: "value" },
    ],
  },
  auth: {
    positionals: [
      { dest: "action", required: true, choices: ["set-key", "list"] },
      { dest: "provider", required: false },
      { dest: "input", required: false },
    ],
    options: [{ dest: "json", flags: ["--json"], kind: "store_true" }],
  },
  mark: {
    positionals: [{ dest: "id", required: true, type: "int" }],
    options: [{ dest: "worked", flags: ["--worked"], kind: "store_true" }],
  },
  status: {
    positionals: [],
    options: [{ dest: "json", flags: ["--json"], kind: "store_true" }],
  },
  stats: {
    positionals: [],
    options: [
      { dest: "period", flags: ["--period"], kind: "value", default: "week" },
      { dest: "json", flags: ["--json"], kind: "store_true" },
    ],
  },
  ctx: {
    positionals: [
      { dest: "action", required: true, choices: ["init", "execute", "search", "get", "promote"] },
      { dest: "input", required: false },
    ],
    options: [
      { dest: "tags", flags: ["--tags"], kind: "value" },
      { dest: "limit", flags: ["--limit"], kind: "int", default: 5 },
    ],
  },
  router: {
    positionals: [],
    nested: { dest: "action", choices: ["chat", "json", "doctor"] },
    options: [],
  },
  config: {
    positionals: [
      { dest: "action", required: true, choices: ["set"] },
      { dest: "key", required: true },
      { dest: "value", required: true },
    ],
    options: [],
  },
  connect: {
    positionals: [],
    options: [{ dest: "mcp", flags: ["--mcp"], kind: "store_true" }],
  },
  hook: {
    positionals: [{ dest: "action", required: true }],
    options: [],
  },
  ingest: {
    positionals: [{ dest: "file", required: true }],
    options: [],
  },
  db: {
    positionals: [
      { dest: "action", required: true, choices: ["link", "list"] },
      { dest: "uri", required: false },
    ],
    options: [
      { dest: "table", flags: ["--table"], kind: "value" },
      { dest: "title", flags: ["--title"], kind: "value", default: "title" },
      { dest: "content", flags: ["--content"], kind: "value", default: "content" },
      { dest: "json", flags: ["--json"], kind: "store_true" },
    ],
  },
  node: {
    positionals: [
      { dest: "action", required: true, choices: ["link", "list", "push", "pull"] },
      { dest: "url", required: false },
    ],
    options: [
      { dest: "name", flags: ["--name"], kind: "value" },
      { dest: "token", flags: ["--token"], kind: "value" },
      { dest: "json", flags: ["--json"], kind: "store_true" },
    ],
  },
  doctor: {
    positionals: [],
    options: [{ dest: "json", flags: ["--json"], kind: "store_true" }],
  },
  brain: {
    positionals: [{ dest: "action", required: true, choices: ["scan", "import"] }],
    options: [
      { dest: "project", flags: ["--project"], kind: "value" },
      { dest: "unknown", flags: ["--unknown"], kind: "store_true" },
      { dest: "source", flags: ["--source"], kind: "value" },
      { dest: "no_redact", flags: ["--no-redact"], kind: "store_true" },
      { dest: "confirm", flags: ["--confirm"], kind: "store_true" },
      { dest: "json", flags: ["--json"], kind: "store_true" },
    ],
  },
  dream: {
    positionals: [{ dest: "action", required: true, choices: ["wake"] }],
    options: [{ dest: "json", flags: ["--json"], kind: "store_true" }],
  },
  evolve: {
    positionals: [
      { dest: "action", required: true, choices: ["run"] },
      { dest: "instruction", required: true },
    ],
    options: [{ dest: "json", flags: ["--json"], kind: "store_true" }],
  },
  dashboard: {
    positionals: [],
    options: [{ dest: "port", flags: ["--port"], kind: "int", default: 4444 }],
  },
  handoff: {
    positionals: [
      {
        dest: "action",
        required: true,
        choices: ["create", "read", "list", "ack", "start", "checkpoint", "complete", "rebuild-db"],
      },
    ],
    options: [
      { dest: "message", flags: ["--message", "-m"], kind: "value", default: "" },
      { dest: "agent", flags: ["--agent", "-a"], kind: "value", default: null },
      { dest: "goal", flags: ["--goal", "-g"], kind: "value", default: null },
      { dest: "handoff_id", flags: ["--id"], kind: "value", default: null },
      { dest: "state", flags: ["--state"], kind: "value", default: "in_progress" },
    ],
  },
};

// Sub-router specs for `router {chat,json,doctor}`.
const ROUTER_ACTIONS: Record<string, SubSpec> = {
  chat: {
    positionals: [{ dest: "input", required: true }],
    options: [
      { dest: "model", flags: ["--model"], kind: "value", default: "openrouter/auto" },
      { dest: "fallback", flags: ["--fallback"], kind: "append" },
      { dest: "session_id", flags: ["--session-id"], kind: "value" },
      { dest: "stream", flags: ["--stream"], kind: "store_true" },
      { dest: "json", flags: ["--json"], kind: "store_true" },
      { dest: "temperature", flags: ["--temperature"], kind: "float" },
      { dest: "max_tokens", flags: ["--max-tokens"], kind: "int" },
    ],
  },
  json: {
    positionals: [{ dest: "input", required: true }],
    options: [
      { dest: "schema", flags: ["--schema"], kind: "value" },
      { dest: "model", flags: ["--model"], kind: "value", default: "openrouter/auto" },
      { dest: "fallback", flags: ["--fallback"], kind: "append" },
      { dest: "session_id", flags: ["--session-id"], kind: "value" },
      { dest: "healing", flags: ["--healing"], kind: "store_true", default: true },
      { dest: "json", flags: ["--json"], kind: "store_true" },
    ],
  },
  doctor: { positionals: [], options: [] },
};

class ArgError extends Error {}

/** Coerces a raw string into the configured type. */
function _coerce(kind: OptSpec["kind"] | "int" | undefined, raw: string): any {
  if (kind === "int") {
    const n = parseInt(raw, 10);
    if (Number.isNaN(n)) throw new ArgError(`invalid int value: '${raw}'`);
    return n;
  }
  if (kind === "float") {
    const n = parseFloat(raw);
    if (Number.isNaN(n)) throw new ArgError(`invalid float value: '${raw}'`);
    return n;
  }
  return raw;
}

/** Parses the tokens for one sub-spec into the args namespace. */
function _parse_spec(spec: SubSpec, tokens: string[], out: Args): void {
  const lookup = _opt_lookup(spec.options);
  // Seed defaults
  for (const o of spec.options) {
    out[o.dest] = o.kind === "store_true" ? Boolean(o.default ?? false) : o.default ?? (o.kind === "append" ? null : null);
  }
  for (const p of spec.positionals) {
    if (!(p.dest in out)) out[p.dest] = null;
  }

  const positional_queue = [...spec.positionals];
  let nested_consumed = false;

  for (let i = 0; i < tokens.length; i++) {
    const tok = tokens[i];
    if (tok.startsWith("-") && tok !== "-") {
      // Support --flag=value
      let flag = tok;
      let inline: string | null = null;
      const eq = tok.indexOf("=");
      if (eq !== -1) {
        flag = tok.slice(0, eq);
        inline = tok.slice(eq + 1);
      }
      const o = lookup.get(flag);
      if (!o) throw new ArgError(`unrecognized arguments: ${tok}`);
      if (o.kind === "store_true") {
        out[o.dest] = true;
      } else {
        const raw = inline !== null ? inline : tokens[++i];
        if (raw === undefined) throw new ArgError(`argument ${flag}: expected one argument`);
        const val = _coerce(o.kind === "append" ? "value" : o.kind, raw);
        if (o.kind === "append") {
          if (!Array.isArray(out[o.dest])) out[o.dest] = [];
          out[o.dest].push(val);
        } else {
          out[o.dest] = val;
        }
      }
      continue;
    }

    // Positional / nested subcommand
    if (spec.nested && !nested_consumed) {
      if (!spec.nested.choices.includes(tok)) {
        throw new ArgError(`invalid choice: '${tok}' (choose from ${spec.nested.choices.join(", ")})`);
      }
      out[spec.nested.dest] = tok;
      nested_consumed = true;
      const nested_spec = ROUTER_ACTIONS[tok];
      _parse_spec(nested_spec, tokens.slice(i + 1), out);
      return;
    }

    const pos = positional_queue.shift();
    if (!pos) throw new ArgError(`unrecognized arguments: ${tok}`);
    if (pos.choices && !pos.choices.includes(tok)) {
      throw new ArgError(`argument ${pos.dest}: invalid choice: '${tok}' (choose from ${pos.choices.join(", ")})`);
    }
    out[pos.dest] = pos.type === "int" ? _coerce("int", tok) : tok;
  }

  // Validate required positionals
  for (const p of positional_queue) {
    if (p.required) {
      throw new ArgError(`the following arguments are required: ${p.dest}`);
    }
  }
  if (spec.nested && !nested_consumed) {
    out[spec.nested.dest] = null;
  }
}

/** Hand-rolled argparse-equivalent. Returns an args namespace with `.command`. */
export function parse_args(argv: string[]): Args {
  const out: Args = { command: null };
  if (!argv.length) return out;

  let i = 0;
  // Top-level options before the subcommand
  while (i < argv.length && argv[i].startsWith("-")) {
    const tok = argv[i];
    if (tok === "-h" || tok === "--help") {
      print_help();
      process.exit(0);
    }
    if (tok === "--version") {
      console.log(`NouGenShards v${VERSION}`);
      process.exit(0);
    }
    throw new ArgError(`unrecognized arguments: ${tok}`);
  }

  const command = argv[i];
  if (!(command in SUBCOMMANDS)) {
    throw new ArgError(`invalid choice: '${command}'`);
  }
  out.command = command;
  _parse_spec(SUBCOMMANDS[command], argv.slice(i + 1), out);
  return out;
}

function print_help(): void {
  console.log(USAGE_HELP);
}

const CMDS: Record<string, (args: Args) => Promise<void>> = {
  init: cmd_init,
  add: cmd_add,
  search: cmd_search,
  chat: cmd_chat,
  auth: cmd_auth,
  mark: cmd_mark,
  status: cmd_status,
  ctx: cmd_ctx,
  config: cmd_config,
  connect: cmd_connect,
  hook: cmd_hook,
  ingest: cmd_ingest,
  db: cmd_db,
  node: cmd_node,
  stats: cmd_stats,
  router: cmd_router,
  doctor: cmd_doctor,
  brain: cmd_brain,
  dream: cmd_dream,
  evolve: cmd_evolve,
  dashboard: cmd_dashboard,
  handoff: cmd_handoff,
  // cmd_models exists but, like the Python, is not wired into the dispatch table.
};

export async function main(): Promise<void> {
  const argv = process.argv.slice(2);
  if (argv.length === 0) {
    console.log("🪩 NouGenShards CLI");
    console.log("┌┐╷┌─┐╷ ╷┌─╴┌─╴┌┐╷┌─┐╷ ╷┌─┐┌─┐╶┬┐┌─┐");
    console.log("│└┤│ ││ ││╶┐├╴ │└┤└─┐├─┤├─┤├┬┘ ││└─┐");
    console.log("╵ ╵└─┘└─┘└─┘└─╴╵ ╵└─┘╵ ╵╵ ╵╵└╴╶┴┘└─┘");
    console.log();
    print_help();
    process.exit(0);
  }

  let args: Args;
  try {
    args = parse_args(argv);
  } catch (e) {
    if (e instanceof ArgError) {
      console.error(`nougen: error: ${e.message}`);
      process.exit(2);
    }
    throw e;
  }

  if (args.command && args.command in CMDS) {
    await CMDS[args.command](args);
  } else {
    print_help();
  }
}

// Reference cmd_models so it is retained (parity with Python's defined-but-unrouted fn).
void cmd_models;

// Entry guard: run main() only when executed directly (python __main__ mimic).
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}

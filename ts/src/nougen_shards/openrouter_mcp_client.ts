/**
 * OpenRouter MCP Client Module. (TS mimic of openrouter_mcp_client.py)
 *
 * The Python module imports openrouter_guard.call_openrouter from the Watchtower
 * root. The TS port instead declares a thin async `call_openrouter` helper that
 * POSTs directly to the OpenRouter /chat/completions endpoint, pulling the
 * OPENROUTER_API_KEY from keymaker.get_secret (falling back to the environment).
 */
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import * as path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import * as keymaker from "./keymaker.js";
import { OpenRouterClient } from "./models_client.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Resolve mcp.config.json from repository root if it exists, otherwise fall back to global path.
// parents[2] of src/nougen_shards/<file> is the package root.
const _repo_root = path.resolve(__dirname, "..", "..");
let _repo_mcp_path = path.join(_repo_root, "mcp.config.json");
if (!existsSync(_repo_mcp_path)) {
  _repo_mcp_path = path.join(_repo_root, "mcp_config.json");
}

export const MCP_CONFIG_PATH =
  process.env.NOUGEN_MCP_CONFIG_PATH ??
  (existsSync(_repo_mcp_path)
    ? _repo_mcp_path
    : path.join(homedir(), ".gemini", "antigravity", "mcp_config.json"));

export const REPO_ROOT = _repo_root;
export const FLEET_REGISTRY_NAME = "nougenai-fleet-registry";
export const MCP_SERVER_ALLOWLIST = new Set<string>([
  "exa",
  "google-developer-knowledge",
  "youtube",
  "web-search",
  FLEET_REGISTRY_NAME,
]);

interface ServerParams {
  command: string;
  args: string[];
  env?: Record<string, string>;
}

/** Build stdio parameters with local Windows/Python startup fixes. */
function _build_server_params(name: string, srv_config: Record<string, any>): ServerParams {
  let cmd: string = srv_config.command;
  let args: string[] = [...(srv_config.args ?? [])];
  let env: Record<string, string> | undefined = srv_config.env;

  if (env !== undefined && env !== null) {
    const merged_env: Record<string, string> = { ...(process.env as Record<string, string>) };
    Object.assign(merged_env, env);
    env = merged_env;
  }

  // process.execPath is the Node equivalent of sys.executable, but the Python
  // fix-up specifically retargets python launchers; mirror by leaving cmd intact
  // unless it is a python launcher, in which case there is no TS interpreter swap.
  if (["python", "python.exe", "python3", "python3.exe"].includes(cmd.toLowerCase())) {
    cmd = process.execPath;
  }

  if (name.toLowerCase() === FLEET_REGISTRY_NAME) {
    const wrapper = path.join(REPO_ROOT, "tools", "nougenai_fleet_registry_mcp.py");
    if (existsSync(wrapper)) {
      cmd = process.execPath;
      args = [wrapper];
    }

    env = env ?? { ...(process.env as Record<string, string>) };
    if (env["NOUGENAI_MCP_LOCK_DIR"] === undefined) {
      env["NOUGENAI_MCP_LOCK_DIR"] = path.join(REPO_ROOT, ".mcp-locks", `${FLEET_REGISTRY_NAME}-${process.pid}`);
    }
  }

  return { command: cmd, args, env };
}

/**
 * Thin OpenRouter helper (mirrors openrouter_guard.call_openrouter).
 * POSTs to /chat/completions. Returns either the raw assistant message object
 * (return_raw_message=true) or the textual content string.
 */
export async function call_openrouter(opts: {
  messages: any[];
  model: string;
  tools?: any[] | null;
  return_raw_message?: boolean;
}): Promise<any> {
  const api_key = keymaker.get_secret("OPENROUTER_API_KEY") ?? process.env.OPENROUTER_API_KEY ?? "";
  if (!api_key) {
    if (opts.return_raw_message) {
      return { role: "assistant", content: "Error: OR Key missing.", tool_calls: null };
    }
    return "Error: OR Key missing.";
  }

  const payload: Record<string, any> = {
    model: opts.model,
    messages: opts.messages,
    stream: false,
  };
  if (opts.tools) {
    payload.tools = opts.tools;
  }

  const r = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${api_key}`,
      "HTTP-Referer": "https://whovisions.com",
      "X-OpenRouter-Title": "NouGenShards",
    },
    body: JSON.stringify(payload),
  });
  const resp_data: any = await r.json();
  const message = resp_data?.choices?.[0]?.message ?? {};
  if (opts.return_raw_message) {
    return message;
  }
  return message.content ?? "";
}

export class MultiMCPBridge {
  /** Bridge for managing multiple MCP connections. */
  sessions: Record<string, Client> = {};
  transports: StdioClientTransport[] = [];
  // maps tool_name -> [server_name, tool_spec]
  tools_map: Record<string, [string, any]> = {};

  /** Initialize all MCP servers configured in the local config. */
  async initialize_servers(): Promise<void> {
    console.log(`[*] Loading MCP configurations from: ${MCP_CONFIG_PATH}`);
    if (!existsSync(MCP_CONFIG_PATH)) {
      console.log(`[!] Config not found at ${MCP_CONFIG_PATH}`);
      return;
    }

    const config = JSON.parse(readFileSync(MCP_CONFIG_PATH, "utf-8"));
    const mcp_servers: Record<string, any> = config.mcpServers ?? {};

    for (const [name, srv_config] of Object.entries(mcp_servers)) {
      // Only connect to specific search servers to avoid crashes and timeouts
      if (!MCP_SERVER_ALLOWLIST.has(name.toLowerCase())) {
        continue;
      }

      if ("command" in (srv_config as Record<string, any>)) {
        console.log(`[*] Connecting to local server '${name}' via Stdio...`);
        try {
          const server_params = _build_server_params(name, srv_config as Record<string, any>);

          const transport = new StdioClientTransport({
            command: server_params.command,
            args: server_params.args,
            env: server_params.env,
          });
          this.transports.push(transport);

          const session = new Client({ name: "nougen-shards", version: "1.1.0" });
          await session.connect(transport);

          this.sessions[name] = session;
          console.log(`    [OK] Active session established for '${name}'`);

          // Fetch available tools
          const tools_resp = await session.listTools();
          console.log(`    Available Tools: ${tools_resp.tools.map((t: any) => t.name)}`);

          for (const t of tools_resp.tools) {
            this.tools_map[t.name] = [name, t];
          }
        } catch (e) {
          console.log(`    [ERR] Connection failed for server '${name}': ${e}`);
        }
      }
    }
  }

  /** Get OpenAI tool definitions from registered tools. */
  get_openai_tool_definitions(): Array<Record<string, any>> {
    const openai_tools: Array<Record<string, any>> = [];
    for (const [, [, tool]] of Object.entries(this.tools_map)) {
      // Get input schema properties and required fields safely
      const input_schema = tool.inputSchema ?? {};
      const properties = input_schema.properties ?? {};
      const required = input_schema.required ?? [];

      openai_tools.push({
        type: "function",
        function: {
          name: tool.name,
          description: tool.description || "",
          parameters: {
            type: "object",
            properties,
            required,
          },
        },
      });
    }
    return openai_tools;
  }

  /** Execute a tool on the registered server. */
  async execute_tool(name: string, arguments_: Record<string, any>): Promise<string> {
    if (!(name in this.tools_map)) {
      return `Error: Tool '${name}' not found in registered fleet.`;
    }

    const [server_name] = this.tools_map[name];
    const session = this.sessions[server_name];

    console.log(`[*] Dispatching execution to '${server_name}': ${name}(${JSON.stringify(arguments_)})`);
    try {
      const result: any = await session.callTool({ name, arguments: arguments_ });
      // Extracted return format handling
      const content = result.content ?? [];
      if (Array.isArray(content) && content.length) {
        const text_blocks = content.filter((block: any) => block?.type === "text").map((block: any) => block.text);
        return text_blocks.join("\n");
      }
      return String(content);
    } catch (e) {
      return `Execution Error: ${e}`;
    }
  }

  /** Shutdown all active MCP connections. */
  async shutdown(): Promise<void> {
    console.log("[*] Terminating active local MCP transports...");
    for (const transport of this.transports) {
      try {
        await transport.close();
      } catch {
        /* pass */
      }
    }
    console.log("[*] Transports terminated.");
  }
}

/** Run an OpenRouter query using registered MCP tools. */
export async function run_query(query: string): Promise<void> {
  const bridge = new MultiMCPBridge();
  await bridge.initialize_servers();

  const openai_tools = bridge.get_openai_tool_definitions();
  console.log(`\n[*] Compiled ${openai_tools.length} tools.`);

  const messages: any[] = [{ role: "user", content: query }];

  // Resolve a free model dynamically from the live roster — never hardcoded.
  const free_model = await new OpenRouterClient().preferred_free_model();

  console.log(`\n[*] Sending request to OpenRouter (${free_model})...`);
  try {
    // 1. First model call with tools passed
    const response = await call_openrouter({
      messages,
      model: free_model,
      tools: openai_tools.length ? openai_tools : null,
      return_raw_message: true,
    });

    // Check if the model returned tool calls
    const tool_calls = response.tool_calls ?? null;
    if (tool_calls) {
      messages.push(response);

      for (const call of tool_calls) {
        const call_id = call.id;
        const func_name = call.function?.name;
        const func_args = call.function?.arguments ?? "{}";

        // Parse arguments
        let args_dict: Record<string, any>;
        if (typeof func_args === "string") {
          try {
            args_dict = JSON.parse(func_args);
          } catch {
            args_dict = {};
          }
        } else {
          args_dict = func_args;
        }

        // Execute local tool
        const result_text = await bridge.execute_tool(func_name, args_dict);

        messages.push({
          role: "tool",
          tool_call_id: call_id,
          name: func_name,
          content: result_text,
        });
      }

      console.log("\n[*] Resolving final answer with tool execution output...");
      // 2. Complete loop and get final textual response
      const final_response = await call_openrouter({
        messages,
        model: free_model,
      });
      console.log(`\n[Final Response]:\n${final_response}`);
    } else {
      console.log(`\n[Response]:\n${response.content}`);
    }
  } catch (e) {
    console.log(`[ERR] Query processing failed: ${e}`);
  }

  await bridge.shutdown();
}

// __main__ mimic
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  let query_input = "Verify the fleet registry statistics and check if we have any active memory shards.";
  if (process.argv.length > 2) {
    query_input = process.argv.slice(2).join(" ");
  }
  void run_query(query_input);
}

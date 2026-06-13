/**
 * Client for interacting with the local context-mode MCP server. (TS mimic of context_client.py)
 * Talks to the context-mode MCP server over stdio via @modelcontextprotocol/sdk.
 */
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import * as path from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport, type StdioServerParameters } from "@modelcontextprotocol/sdk/client/stdio.js";

// Dynamic resolution of Watchtower root
let _watchtower_root = process.env.WATCHTOWER_ROOT;
if (!_watchtower_root) {
  _watchtower_root = path.join(homedir(), "Watchtower");
}

// Dynamic resolution of context-mode start script path
const _nvm_symlink = process.env.NVM_SYMLINK;
const _appdata = process.env.APPDATA;

let _start_mjs: string | null = null;
const _candidates: string[] = [];
if (_nvm_symlink) {
  _candidates.push(path.join(_nvm_symlink, "node_modules/context-mode/start.mjs"));
}
if (_appdata) {
  _candidates.push(path.join(_appdata, "npm/node_modules/context-mode/start.mjs"));
}

_candidates.push(
  path.join(homedir(), "AppData/Roaming/npm/node_modules/context-mode/start.mjs"),
  "/usr/local/lib/node_modules/context-mode/start.mjs",
  "/usr/lib/node_modules/context-mode/start.mjs",
);

for (const _path of _candidates) {
  try {
    if (existsSync(_path)) {
      _start_mjs = _path;
      break;
    }
  } catch {
    /* mirror except Exception pass */
  }
}

if (!_start_mjs) {
  // Default fallback path
  const _symlink_base = _nvm_symlink || "C:/nvm4w/nodejs";
  _start_mjs = path.join(_symlink_base, "node_modules/context-mode/start.mjs");
}

// Dynamic parameters from system folders observation
export const CONTEXT_MODE_PARAMS: StdioServerParameters = {
  command: "node",
  args: [_start_mjs, _watchtower_root],
};

export class ContextClient {
  /** Client for the context-mode MCP server. */
  params: StdioServerParameters;

  constructor(params: StdioServerParameters = CONTEXT_MODE_PARAMS) {
    this.params = params;
  }

  /** Internal helper to connect, call a tool, and close. */
  async _call_tool(tool_name: string, arguments_: Record<string, any>): Promise<string> {
    let client: Client | null = null;
    let transport: StdioClientTransport | null = null;
    try {
      transport = new StdioClientTransport(this.params);
      client = new Client({ name: "nougen-context-client", version: "1.1.0" });
      await client.connect(transport);

      const result = await client.callTool({ name: tool_name, arguments: arguments_ });
      const content = (result as any)?.content ?? [];
      if (Array.isArray(content) && content.length) {
        return content
          .filter((block: any) => (block?.type ?? "") === "text")
          .map((block: any) => block.text)
          .join("\n");
      }
      return String(content);
    } catch (e: any) {
      return `Unexpected error in Context Mode: ${e?.message ?? e}`;
    } finally {
      try {
        await client?.close();
      } catch {
        /* ignore close error */
      }
    }
  }

  /** Runs sandboxed code via ctx_execute. */
  async execute(code: string, language: string = "javascript"): Promise<string> {
    return this._call_tool("ctx_execute", { code, language });
  }

  /** Runs a script file via ctx_execute_file. */
  async execute_file(file_path: string): Promise<string> {
    return this._call_tool("ctx_execute_file", { path: file_path });
  }

  /** Performs high-performance search via ctx_search. */
  async search(query: string): Promise<string> {
    return this._call_tool("ctx_search", { query });
  }

  /** Gets context mode statistics. */
  async stats(): Promise<string> {
    return this._call_tool("ctx_stats", {});
  }

  /** Gets architectural insight via ctx_insight. */
  async insight(query: string): Promise<string> {
    return this._call_tool("ctx_insight", { query });
  }
}

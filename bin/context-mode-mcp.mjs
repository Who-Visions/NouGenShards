#!/usr/bin/env node
// Start the context-mode MCP server from a PINNED install, never `npx -y`.
// npx re-installs into its cache on every cold start (>58s measured on phoebus,
// past the MCP connect timeout), and cache cleanups make every start cold.
// The pin lives in ~/.nougen/tools/context-mode, outside every cache; if it is
// missing (fresh node, wiped dir) it is installed once, then reused forever.
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const VERSION = process.env.CONTEXT_MODE_VERSION || "1.0.169";
const dir = join(homedir(), ".nougen", "tools", "context-mode");
const entry = join(dir, "node_modules", "context-mode", "start.mjs");

if (!existsSync(entry)) {
  mkdirSync(dir, { recursive: true });
  if (!existsSync(join(dir, "package.json"))) writeFileSync(join(dir, "package.json"), '{"private":true}\n');
  const npm = process.platform === "win32" ? "npm.cmd" : "npm";
  // stdout is the MCP channel: send install chatter to stderr only.
  const r = spawnSync(npm, ["install", "--no-audit", "--no-fund", `context-mode@${VERSION}`],
    { cwd: dir, stdio: ["ignore", process.stderr, process.stderr], shell: process.platform === "win32" });
  if (r.status !== 0 || !existsSync(entry)) { console.error(`context-mode pin install failed in ${dir}`); process.exit(1); }
}

const child = spawn(process.execPath, [entry, ...process.argv.slice(2)], { stdio: "inherit" });
child.on("exit", (code, sig) => process.exit(sig ? 1 : code ?? 0));
for (const s of ["SIGINT", "SIGTERM"]) process.on(s, () => child.kill(s));

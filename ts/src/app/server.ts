/**
 * NouGenShards Production Node & Cortex HUD. (TS mimic of app.py)
 *
 * Python stack: FastAPI + Gradio (Blocks UI) + Token Auth, served by uvicorn on :4444.
 * TS mimic: Node builtin `http` server (no express) that
 *   - exposes /health and a token-verified gate (verify_token),
 *   - serves an HTML shell that mounts the React HUD (Hud.tsx) from a CDN (esm.sh),
 *   - backs each HUD tab with JSON /api/* endpoints that call into ../nougen_shards.
 *
 * The Gradio Blocks layout (5 tabs) is reproduced client-side in Hud.tsx; here we
 * preserve the Python helper functions that produced each tab's data.
 */
import { createServer, IncomingMessage, ServerResponse } from "node:http";
import { existsSync, statSync, readFileSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import * as path from "node:path";
import { spawnSync } from "node:child_process";
import * as core from "../nougen_shards/core.js";
import { HistoryEngine } from "../nougen_shards/history.js";
import { classify_file, detect_tool } from "../nougen_shards/brain_scan/classifiers.js";
import {
  GLOBAL_ROOTS,
  PROJECT_ROOT_NAMES,
  PROJECT_FILES,
  DANGER_ZONES,
  SKIP_DIRS,
  SUPPORTED_EXTS,
} from "../nougen_shards/brain_scan/registry.js";
import type { CandidateFile } from "../nougen_shards/brain_scan/candidate.js";

// --- Storage override for HF Persistence (mirror app.py SPACE_ID block) ---
if (process.env.SPACE_ID) {
  process.env.NOUGEN_HOME = "/data";
  process.env.NOUGEN_VAULT_DIR = "/data/.vault";
}

// --- Security ---

const NODE_TOKEN = process.env.NGS_NODE_TOKEN;

/**
 * Mirror of FastAPI verify_token dependency.
 * Returns null when authorized; otherwise a {status, detail} describing the failure.
 * 503 if write-auth unconfigured, 401 if the X-NGS-Token header mismatches.
 */
export function verify_token(x_ngs_token: string | undefined): { status: number; detail: string } | null {
  if (!NODE_TOKEN) {
    return { status: 503, detail: "Node write-auth not configured." };
  }
  if (x_ngs_token !== NODE_TOKEN) {
    return { status: 401, detail: "Invalid node token." };
  }
  return null;
}

// --- API logic (mirror app.py health) ---

/** Mirror of FastAPI health(). */
export function health(): { status: string; storage: string } {
  return { status: "ignited", storage: process.env.NOUGEN_HOME ?? "default" };
}

// --- Cortex HUD UI Logic ---

/** Generates a visual map of the 9-DB cluster. (mirror get_substrate_map) */
export function get_substrate_map(): string[] {
  const active_idx = core.get_active_db_index();
  const stats: string[] = [];
  for (let i = 1; i < 10; i++) {
    const p = core.get_db_path(i);
    const size = existsSync(p) ? statSync(p).size / (1024 * 1024) : 0;
    let shards_count = 0;
    if (existsSync(p)) {
      try {
        const conn = core.get_connection(i);
        shards_count = (conn.prepare("SELECT COUNT(*) AS c FROM shards").get() as { c: number }).c;
        conn.close();
      } catch {
        /* table may not exist yet; mirror bare except pass */
      }
    }

    let status = i === active_idx ? "🟢 ACTIVE" : "⚪ READY";
    if (size > 900) {
      status = "🔴 FULL";
    }

    stats.push(`### DB #${i} [${status}]\n- ${shards_count} shards\n- ${size.toFixed(2)} MB / 1024 MB`);
  }

  return stats;
}

/**
 * Local port of brain_scan.scanner.scan_environment (not yet present in ts/).
 * Faithful 1:1 of scanner.py so run_recon has a real data source.
 */
function _is_safe_dir(dir: string): boolean {
  const parts = dir.replace(/\\/g, "/").split("/").filter((s) => s.length > 0);
  for (const d of parts) {
    const low = d.toLowerCase();
    if (SKIP_DIRS.has(low) || DANGER_ZONES.has(low) || d.startsWith(".ssh") || d.startsWith(".aws")) {
      return false;
    }
  }
  return true;
}

function _rglob_files(root: string, maxDepth: number): string[] {
  const out: string[] = [];
  const walk = (dir: string, depth: number): void => {
    let entries: import("node:fs").Dirent[];
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      const full = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (depth < maxDepth) {
          walk(full, depth + 1);
        }
      } else if (e.isFile()) {
        out.push(full);
      }
    }
  };
  walk(root, 1);
  return out;
}

export function scan_environment(project_path: string | null = null, include_unknown: boolean = false): CandidateFile[] {
  const candidates: CandidateFile[] = [];

  // 1. Project Scan
  if (project_path) {
    const root = path.resolve(project_path);
    for (const p of _rglob_files(root, 64)) {
      if (SUPPORTED_EXTS.has(path.extname(p)) && _is_safe_dir(path.dirname(p))) {
        const parts = p.replace(/\\/g, "/").split("/");
        const is_proj_ctx = parts.some((part) => PROJECT_ROOT_NAMES.includes(part)) || PROJECT_FILES.includes(path.basename(p));
        if (is_proj_ctx || include_unknown) {
          const score = classify_file(p);
          if (score === "high" || score === "medium") {
            const tool = detect_tool(p);
            const sz = statSync(p).size / (1024 * 1024);
            if (sz <= 25) {
              candidates.push({ path: p, tool, is_project_context: true, score_tier: score, size_mb: sz });
            }
          }
        }
      }
    }
  }

  // 2. Global Scan (skip GLOBAL_ROOTS[0] = home, depth-limit relative roots to 5)
  for (const g_root of GLOBAL_ROOTS.slice(1)) {
    if (!existsSync(g_root) || !statSync(g_root).isDirectory()) {
      continue;
    }
    for (const p of _rglob_files(g_root, 5)) {
      if (SUPPORTED_EXTS.has(path.extname(p)) && _is_safe_dir(path.dirname(p))) {
        const score = classify_file(p);
        if (score === "high" || score === "medium") {
          const tool = detect_tool(p);
          if (tool !== "unknown" || include_unknown) {
            const sz = statSync(p).size / (1024 * 1024);
            if (sz <= 25) {
              candidates.push({ path: p, tool, is_project_context: false, score_tier: score, size_mb: sz });
            }
          }
        }
      }
    }
  }

  // Deduplicate candidates by path
  const seen = new Set<string>();
  const unique: CandidateFile[] = [];
  for (const c of candidates) {
    const s_path = path.resolve(c.path);
    if (!seen.has(s_path)) {
      seen.add(s_path);
      unique.push(c);
    }
  }
  return unique;
}

/** Runs a brain scan and returns a summary for the UI. (mirror run_recon) */
export function run_recon(): string {
  const candidates = scan_environment();
  const high = candidates.filter((c) => c.score_tier === "high");
  const tools: Record<string, number> = {};
  for (const c of candidates) {
    tools[c.tool] = (tools[c.tool] ?? 0) + 1;
  }

  const report: string[] = ["### Discovered Memory Sources"];
  for (const [t, count] of Object.entries(tools)) {
    if (t !== "unknown") {
      report.push(`- **.${t}**: ${count} artifacts found`);
    }
  }

  report.push(`\n**Total potential shards**: ${high.length * 2}`);
  return report.join("\n");
}

/** Search the substrate and render a Markdown result block. (mirror gr_search) */
export function gr_search(query: string): string {
  const results = core.retrieve(query, 5);
  if (!results.length) {
    return "No records found.";
  }

  const output: string[] = [];
  for (const r of results) {
    const sentiment = r.utility_score > 1.0 ? "🌟" : "🌑";
    output.push(
      `## ${r.title} ${sentiment}\n**ID**: ${r.id} | **Score**: ${(r.final_score as number).toFixed(2)}\n\n${r.content}\n`,
    );
  }
  return output.join("\n---\n");
}

/** Analytics summary + ASCII timeline. (mirror get_analytics) -> [stats, timeline] */
export function get_analytics(): [string, string] {
  const engine = HistoryEngine;
  const growth = engine.get_growth_rate("week");
  const utility = engine.get_utility_delta("week");
  const timeline = engine.get_timeline("week");

  const stats = `
# 📈 Intelligence Growth
- **New Shards (Week)**: ${growth.new_shards}
- **Total Substrate Size**: ${growth.total_shards} shards
- **Bayesian Delta**: ${utility >= 0 ? "+" : ""}${utility.toFixed(2)}
`;
  return [stats, timeline];
}

/** Inspect cwd transcript.log. (mirror check_current_transcript) -> [status, path|null, preview] */
export function check_current_transcript(): [string, string | null, string] {
  const log_path = path.join(process.cwd(), "transcript.log");
  if (existsSync(log_path)) {
    const size_mb = statSync(log_path).size / (1024 * 1024);
    let preview: string;
    try {
      const lines = readFileSync(log_path, "utf-8").split(/\r?\n/);
      // Read last 100 lines for preview
      preview = lines.slice(-100).join("\n");
    } catch (e) {
      preview = `Error reading log preview: ${e}`;
    }
    return [`🟢 Transcript exists.\n- **Size**: ${size_mb.toFixed(2)} MB\n- **Log File**: \`${log_path}\``, log_path, preview];
  }
  return ["⚪ No transcript generated yet. Click 'Generate Transcript' below.", null, ""];
}

/** Generate a transcript via the vault reader tool. (mirror generate_transcript) */
export function generate_transcript(): [string, string | null, string] {
  const script_path = path.join(process.cwd(), "tools", "read_vault_shards.py");
  const res = spawnSync("python", [script_path, "--cluster"], { encoding: "utf-8" });
  if (res.status === 0) {
    return check_current_transcript();
  }
  const err_msg = res.stderr || res.stdout || "Unknown execution error.";
  return [`🔴 Generation failed:\n\`\`\`\n${err_msg}\n\`\`\``, null, ""];
}

// --- HTTP Server (mimics gr.mount_gradio_app + uvicorn) ---

/** Serializes any value as a JSON HTTP response. */
function sendJson(res: ServerResponse, status: number, body: unknown): void {
  const payload = JSON.stringify(body);
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  res.end(payload);
}

/**
 * The HTML shell. Mirrors gr.Blocks(title="NouGenShards Cortex HUD"): it imports
 * React + the Hud component (from esm.sh, since we only run tsc, not a bundler) and
 * mounts <CortexHud/> which fetches the /api/* endpoints above.
 */
function indexHtml(): string {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>NouGenShards Cortex HUD</title>
</head>
<body style="margin:0;background:#0f1117;color:#e6e6e6;font-family:system-ui,sans-serif">
  <div id="root"></div>
  <script type="module">
    import React from "https://esm.sh/react@18.3.1";
    import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";

    // Inline runtime mirror of Hud.tsx (the canonical TSX source). Since we only run
    // tsc (no bundler) we mount a runtime twin here that calls the same /api/* routes.
    const e = React.createElement;
    const useState = React.useState, useEffect = React.useEffect;
    const TABS = [
      ["🔍 Search", "search"], ["📈 History", "history"], ["🗺️ Substrate", "substrate"],
      ["🧠 Recon", "recon"], ["📝 Transcript", "transcript"]
    ];
    function App() {
      const [tab, setTab] = useState("search");
      const [q, setQ] = useState("");
      const [out, setOut] = useState("");
      const [sub, setSub] = useState([]);
      const get = (u) => fetch(u).then(r => r.json());
      const doSearch = () => get("/api/search?q=" + encodeURIComponent(q)).then(d => setOut(d.markdown));
      useEffect(() => {
        if (tab === "history") get("/api/analytics").then(d => setOut(d.stats + "\\n\\n" + d.timeline));
        if (tab === "substrate") get("/api/substrate").then(d => setSub(d.maps));
        if (tab === "recon") get("/api/recon").then(d => setOut(d.markdown));
        if (tab === "transcript") get("/api/transcript").then(d => setOut(d.status + "\\n\\n" + d.preview));
      }, [tab]);
      return e("div", { style: { padding: 20 } },
        e("h1", null, "🪩 NouGenShards Cortex HUD"),
        e("div", { style: { display: "flex", gap: 8, marginBottom: 16 } },
          TABS.map(([label, id]) => e("button", {
            key: id, onClick: () => setTab(id),
            style: { padding: "8px 12px", background: tab === id ? "#2d3350" : "#1a1d2b", color: "#fff", border: "1px solid #333", borderRadius: 6 }
          }, label))),
        tab === "search" && e("div", null,
          e("input", { value: q, placeholder: "What do I know about...", onChange: ev => setQ(ev.target.value), style: { width: "60%", padding: 8 } }),
          e("button", { onClick: doSearch, style: { marginLeft: 8, padding: 8 } }, "Search Memory")),
        tab === "substrate"
          ? e("div", { style: { display: "flex", flexWrap: "wrap", gap: 12 } }, sub.map((m, i) => e("pre", { key: i, style: { background: "#1a1d2b", padding: 12, borderRadius: 6 } }, m)))
          : e("pre", { style: { whiteSpace: "pre-wrap", background: "#1a1d2b", padding: 16, borderRadius: 6 } }, out));
    }
    createRoot(document.getElementById("root")).render(e(App));
  </script>
</body>
</html>`;
}

const server = createServer((req: IncomingMessage, res: ServerResponse) => {
  const url = new URL(req.url ?? "/", "http://localhost");
  const route = url.pathname;

  try {
    if (route === "/health") {
      sendJson(res, 200, health());
      return;
    }
    if (route === "/api/substrate") {
      sendJson(res, 200, { maps: get_substrate_map() });
      return;
    }
    if (route === "/api/search") {
      const q = url.searchParams.get("q") ?? "";
      sendJson(res, 200, { markdown: gr_search(q) });
      return;
    }
    if (route === "/api/analytics") {
      const [stats, timeline] = get_analytics();
      sendJson(res, 200, { stats, timeline });
      return;
    }
    if (route === "/api/recon") {
      sendJson(res, 200, { markdown: run_recon() });
      return;
    }
    if (route === "/api/transcript") {
      const [status, log_path, preview] = check_current_transcript();
      sendJson(res, 200, { status, path: log_path, preview });
      return;
    }
    if (route === "/" || route === "/index.html") {
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(indexHtml());
      return;
    }
    sendJson(res, 404, { detail: "Not Found" });
  } catch (e) {
    sendJson(res, 500, { detail: String(e) });
  }
});

// Entry guard (mirror `if __name__ == "__main__": uvicorn.run(app, host="0.0.0.0", port=4444)`)
const isMain = import.meta.url === `file://${process.argv[1]}` || import.meta.url.endsWith(process.argv[1]?.replace(/\\/g, "/") ?? "");
if (isMain) {
  const PORT = 4444;
  server.listen(PORT, "0.0.0.0", () => {
    console.log(`NouGenShards Cortex HUD listening on http://0.0.0.0:${PORT}`);
  });
}

export { server };

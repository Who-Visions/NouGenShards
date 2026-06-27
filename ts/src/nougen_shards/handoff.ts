/**
 * Cross-agent session handoff notes. (TS mimic of handoff.py)
 *
 * Native TypeScript reimplementation — writes to the SAME .handoffs JSON/markdown
 * store and handoffs.db index as the Python port, so Claude / Gemini / Codex stay
 * trilaterally coordinated regardless of which runtime created a record.
 */
import { execFileSync } from "node:child_process";
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { homedir, tmpdir } from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { createDatabase, type DatabaseSync } from "./_db.js";

// Handoff notes live in <repo>/.handoffs by default. Override with NOUGEN_HANDOFF_DIR
// so the system works regardless of where it is installed or invoked from.
function _resolve_project_root(): string {
  // Walk up from this module until we find the repo root markers; fall back to cwd.
  // Markers that uniquely identify the Python repo root (NOT the ts/ subtree):
  // pyproject.toml / .git live only at the real root, so the walk skips ts/.
  let dir = path.dirname(fileURLToPath(import.meta.url));
  for (let i = 0; i < 12; i++) {
    if (existsSync(path.join(dir, "pyproject.toml")) || existsSync(path.join(dir, ".git"))) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return process.cwd();
}

export const PROJECT_ROOT = _resolve_project_root();
export const HANDOFF_DIR = process.env.NOUGEN_HANDOFF_DIR ?? path.join(PROJECT_ROOT, ".handoffs");

export const AGENT_FOLDERS: Record<string, string> = {
  gemini: "gemini handoffs",
  claude: "claude handoffs",
  "claude-cli": "claude cli handoffs",
  codex: "codex handoffs",
  ollama: "ollama handoffs",
  openrouter: "openrouter handoffs",
};

export const OPEN_STATUSES = new Set<string>(["open", "acknowledged", "in_progress", "blocked"]);
export const HANDOFF_DB_NAME = "handoffs.db";

type Json = Record<string, any>;

/** Return a console that strips Rich-style [tag] markup, so call sites stay 1:1. */
function _make_console(): { print(msg: string): void } {
  return {
    print(msg: string): void {
      console.log(String(msg).replace(/\[[^\]]*\]/g, ""));
    },
  };
}

/** Python datetime.now().isoformat() mimic (local time, microsecond-ish). */
function _now_iso(): string {
  const d = new Date();
  const pad = (n: number, w = 2) => String(n).padStart(w, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}000`
  );
}

/** Python strftime("%Y%m%d_%H%M%S") mimic (local time). */
function _now_stamp(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

/**
 * Writes JSON via a temp file + atomic replace, so an interrupted or
 * concurrent write can never leave a truncated handoff record on disk.
 */
function _atomic_write_json(p: string, data: Json): void {
  mkdirSync(path.dirname(p), { recursive: true });
  const tmp = path.join(path.dirname(p), `.${path.basename(p)}.${process.pid}.${Date.now()}.tmp`);
  try {
    writeFileSync(tmp, JSON.stringify(data, null, 2), "utf-8");
    renameSync(tmp, p);
  } catch (e) {
    if (existsSync(tmp)) rmSync(tmp, { force: true });
    throw e;
  }
}

function _read_handoff(p: string): Json | null {
  try {
    return JSON.parse(readFileSync(p, "utf-8"));
  } catch {
    return null;
  }
}

function _append_markdown(p: string, title: string, lines: string[]): void {
  const md_path = p.replace(/\.json$/, ".md");
  if (!existsSync(md_path)) {
    return;
  }
  try {
    let out = `\n## ${title}\n`;
    for (const line of lines) {
      out += `- ${line}\n`;
    }
    appendFileSync(md_path, out, "utf-8");
  } catch {
    /* best-effort */
  }
}

/** Find a target handoff by id, or the newest handoff matching statuses. */
function _find_handoff(
  agent: string | null = null,
  handoff_id: string | null = null,
  statuses: Set<string> | null = null,
): [string | null, Json | null] {
  for (const p of get_handoff_files(agent)) {
    const data = _read_handoff(p);
    if (!data) {
      continue;
    }
    if (handoff_id && data.handoff_id !== handoff_id) {
      continue;
    }
    const status = data.status || "open";
    if (statuses && !statuses.has(status)) {
      continue;
    }
    return [p, data];
  }
  return [null, null];
}

function _ensure_orchestration(data: Json, receiver: string, timestamp: string): Json {
  const orchestration = (data.orchestration ??= {});
  orchestration.run_id ??= `${timestamp.replace(/:/g, "").replace(/\./g, "")}_${receiver}`;
  orchestration.started_by ??= receiver;
  orchestration.started_at ??= timestamp;
  orchestration.checkpoints ??= [];
  return orchestration;
}

/** Return the local SQLite index path for handoff records. */
export function get_handoff_db_path(): string {
  return path.join(HANDOFF_DIR, HANDOFF_DB_NAME);
}

function _get_db_connection(): DatabaseSync {
  mkdirSync(HANDOFF_DIR, { recursive: true });
  return createDatabase(get_handoff_db_path());
}

/** Initialize the local handoff/orchestration index. */
export function init_handoff_db(): void {
  const conn = _get_db_connection();
  try {
    conn.exec(`
            CREATE TABLE IF NOT EXISTS handoff_records (
                handoff_id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                markdown_path TEXT,
                agent TEXT,
                status TEXT,
                goal TEXT,
                message TEXT,
                branch TEXT,
                session_id TEXT,
                created_at TEXT,
                acknowledged_by TEXT,
                acknowledged_at TEXT,
                completed_by TEXT,
                completed_at TEXT,
                updated_at TEXT NOT NULL,
                data_json TEXT NOT NULL
            )
        `);
    conn.exec(`
            CREATE TABLE IF NOT EXISTS handoff_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                handoff_id TEXT NOT NULL,
                checkpoint_index INTEGER NOT NULL,
                timestamp TEXT,
                agent TEXT,
                state TEXT NOT NULL,
                message TEXT,
                FOREIGN KEY (handoff_id) REFERENCES handoff_records(handoff_id)
            )
        `);
    conn.exec("CREATE INDEX IF NOT EXISTS idx_handoff_records_status ON handoff_records(status)");
    conn.exec("CREATE INDEX IF NOT EXISTS idx_handoff_records_agent ON handoff_records(agent)");
    conn.exec(
      "CREATE INDEX IF NOT EXISTS idx_handoff_checkpoints_handoff ON handoff_checkpoints(handoff_id, checkpoint_index)",
    );
  } finally {
    conn.close();
  }
}

/** Mirror one handoff JSON record into SQLite for indexed orchestration. */
function _sync_handoff_to_db(p: string, data: Json): boolean {
  try {
    init_handoff_db();
    const conn = _get_db_connection();
    const git_info = data.git || {};
    const orchestration = data.orchestration || {};
    const checkpoints: Json[] = orchestration.checkpoints || [];
    const now = _now_iso();
    const handoff_id = data.handoff_id || path.basename(p, ".json");
    try {
      conn
        .prepare(`
                INSERT INTO handoff_records (
                    handoff_id, path, markdown_path, agent, status, goal, message,
                    branch, session_id, created_at, acknowledged_by, acknowledged_at,
                    completed_by, completed_at, updated_at, data_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(handoff_id) DO UPDATE SET
                    path=excluded.path,
                    markdown_path=excluded.markdown_path,
                    agent=excluded.agent,
                    status=excluded.status,
                    goal=excluded.goal,
                    message=excluded.message,
                    branch=excluded.branch,
                    session_id=excluded.session_id,
                    created_at=excluded.created_at,
                    acknowledged_by=excluded.acknowledged_by,
                    acknowledged_at=excluded.acknowledged_at,
                    completed_by=excluded.completed_by,
                    completed_at=excluded.completed_at,
                    updated_at=excluded.updated_at,
                    data_json=excluded.data_json
            `)
        .run(
          handoff_id,
          p,
          p.replace(/\.json$/, ".md"),
          data.agent ?? null,
          data.status || "open",
          data.goal ?? null,
          data.message ?? null,
          git_info.branch ?? null,
          data.session_id ?? null,
          data.timestamp ?? null,
          data.acknowledged_by ?? null,
          data.acknowledged_at ?? null,
          data.completed_by ?? null,
          data.completed_at ?? null,
          now,
          JSON.stringify(data),
        );
      conn.prepare("DELETE FROM handoff_checkpoints WHERE handoff_id = ?").run(handoff_id);
      checkpoints.forEach((checkpoint, index) => {
        conn
          .prepare(`
                    INSERT INTO handoff_checkpoints (
                        handoff_id, checkpoint_index, timestamp, agent, state, message
                    ) VALUES (?, ?, ?, ?, ?, ?)
                `)
          .run(
            handoff_id,
            index,
            checkpoint.timestamp ?? null,
            checkpoint.agent ?? null,
            checkpoint.state || "unknown",
            checkpoint.message ?? null,
          );
      });
    } finally {
      conn.close();
    }
    return true;
  } catch {
    return false;
  }
}

/** Build compact NouGenContext metadata without storing the full handoff. */
function _handoff_context_metadata(p: string, data: Json, extra: Json = {}): Json {
  const git_info = data.git || {};
  const metadata: Json = {
    handoff_id: data.handoff_id || path.basename(p, ".json"),
    path: p,
    agent: data.agent,
    status: data.status,
    goal: data.goal,
    branch: git_info.branch,
    handoff_db_path: get_handoff_db_path(),
  };
  for (const [k, v] of Object.entries(extra)) {
    if (v !== null && v !== undefined) metadata[k] = v;
  }
  return metadata;
}

/** Mirror handoff state into NouGenContext without making handoffs depend on it. */
function _log_context_event(event_type: string, content: string, metadata: Json | null = null): void {
  void (async () => {
    try {
      const nougen_context = await import("./nougen_context.js");
      nougen_context.init_context_db(false);
      nougen_context.log_event(event_type, content, metadata || {});
    } catch {
      return;
    }
  })();
}

/** Rebuild the SQLite index from handoff JSON files. */
export function rebuild_handoff_db(agent: string | null = null): number {
  init_handoff_db();
  let count = 0;
  for (const p of get_handoff_files(agent)) {
    const data = _read_handoff(p);
    if (data && _sync_handoff_to_db(p, data)) {
      count += 1;
    }
  }
  _log_context_event("HANDOFF_DB_REBUILT", `Handoff DB rebuilt with ${count} indexed record(s).`, {
    agent_filter: agent,
    count,
    handoff_db_path: get_handoff_db_path(),
  });
  return count;
}

/**
 * Locates the directory holding the current session's task.md /
 * implementation_plan.md. Defaults to the Gemini Antigravity brain layout but
 * can point anywhere via NOUGEN_HANDOFF_TASKS_DIR.
 */
export function get_active_brain_dir(): string | null {
  const override = process.env.NOUGEN_HANDOFF_TASKS_DIR;
  if (override) {
    return existsSync(override) ? override : null;
  }
  const brain_root = path.join(homedir(), ".gemini", "antigravity-cli", "brain");
  if (!existsSync(brain_root)) {
    return null;
  }
  let dirs: string[];
  try {
    dirs = readdirSync(brain_root, { withFileTypes: true })
      .filter((d) => d.isDirectory() && d.name.length === 36)
      .map((d) => path.join(brain_root, d.name));
  } catch {
    return null;
  }
  if (!dirs.length) {
    return null;
  }
  dirs.sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
  return dirs[0];
}

/** Detects the current agent type. NOUGEN_AGENT always wins; else infer. */
export function detect_current_agent(): string {
  const explicit = process.env.NOUGEN_AGENT;
  if (explicit) {
    return explicit.trim().toLowerCase();
  }
  // Claude Code CLI is its own lane ("claude-cli"), distinct from the
  // API/Antigravity "claude" lane. The CLI sets an explicit marker, which is a
  // stronger signal than a stray GEMINI/GOOGLE key exported in the same shell —
  // so check it BEFORE generic API-key detection or CLI handoffs misroute.
  if (process.env.CLAUDECODE || process.env.CLAUDE_CODE || process.env.CLAUDE_CODE_ENTRYPOINT) {
    return "claude-cli";
  }
  if (process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY) {
    return "gemini";
  }
  if (process.env.ANTHROPIC_API_KEY) {
    return "claude";
  }
  const active_brain = get_active_brain_dir();
  if (active_brain && active_brain.toLowerCase().includes("antigravity")) {
    return "gemini";
  }
  return "generic";
}

/** Parses task.md and returns lists of completed, in-progress, and pending tasks. */
export function parse_task_md(task_path: string): { completed: string[]; in_progress: string[]; pending: string[] } {
  const completed: string[] = [];
  const in_progress: string[] = [];
  const pending: string[] = [];
  if (!existsSync(task_path)) {
    return { completed: [], in_progress: [], pending: [] };
  }
  try {
    for (let line of readFileSync(task_path, "utf-8").split(/\r?\n/)) {
      line = line.trim();
      if (line.startsWith("- [x]")) {
        completed.push(line.slice(5).trim());
      } else if (line.startsWith("- [/]")) {
        in_progress.push(line.slice(5).trim());
      } else if (line.startsWith("- [ ]")) {
        pending.push(line.slice(5).trim());
      }
    }
  } catch {
    /* best-effort */
  }
  return { completed, in_progress, pending };
}

/** Retrieves git status, branch name, and recent commits. */
export function get_git_status(): { branch: string; changes: string[]; commits: string[] } {
  const status = { branch: "unknown", changes: [] as string[], commits: [] as string[] };
  const run = (args: string[]): string | null => {
    try {
      return execFileSync("git", args, { cwd: PROJECT_ROOT, encoding: "utf-8", timeout: 10000 });
    } catch {
      return null;
    }
  };
  const branch = run(["rev-parse", "--abbrev-ref", "HEAD"]);
  if (branch !== null) {
    status.branch = branch.trim();
  }
  const porcelain = run(["status", "--porcelain"]);
  if (porcelain !== null) {
    for (const line of porcelain.split(/\r?\n/)) {
      if (line.trim()) status.changes.push(line.trim());
    }
  }
  const commits = run(["log", "-n", "3", "--oneline"]);
  if (commits !== null) {
    for (const line of commits.split(/\r?\n/)) {
      if (line.trim()) status.commits.push(line.trim());
    }
  }
  return status;
}

export function create_handoff(
  message: string = "",
  agent: string | null = null,
  goal: string | null = null,
): string | null {
  const con = _make_console();
  mkdirSync(HANDOFF_DIR, { recursive: true });

  if (!agent) {
    agent = detect_current_agent();
  }

  let target_folder = HANDOFF_DIR;
  if (agent.toLowerCase() in AGENT_FOLDERS) {
    target_folder = path.join(HANDOFF_DIR, AGENT_FOLDERS[agent.toLowerCase()]);
  }
  mkdirSync(target_folder, { recursive: true });

  const timestamp = _now_stamp();
  const git_info = get_git_status();
  const branch = git_info.branch.replace(/\//g, "_").replace(/\\/g, "_");

  // Task tracking (Gemini Antigravity brain layout by default).
  const brain_dir = get_active_brain_dir();
  let tasks = { completed: [] as string[], in_progress: [] as string[], pending: [] as string[] };
  if (brain_dir) {
    tasks = parse_task_md(path.join(brain_dir, "task.md"));
    if (!goal) {
      const plan_path = path.join(brain_dir, "implementation_plan.md");
      if (existsSync(plan_path)) {
        try {
          for (const line of readFileSync(plan_path, "utf-8").split(/\r?\n/)) {
            if (line.startsWith("# ")) {
              goal = line.slice(2).trim();
              break;
            }
          }
        } catch {
          /* best-effort */
        }
      }
    }
  }
  if (!goal) {
    goal = "No active goal recorded. Pass --goal to set one.";
  }

  const handoff_data: Json = {
    handoff_id: `${timestamp}_${branch}`,
    timestamp: _now_iso(),
    goal,
    message,
    git: git_info,
    tasks,
    session_id: brain_dir ? path.basename(brain_dir) : "unknown",
    agent: agent.toLowerCase(),
    status: "open",
    acknowledged_by: null,
    acknowledged_at: null,
  };

  // Save JSON file (atomic: temp + replace prevents truncated records)
  const json_path = path.join(target_folder, `handoff_${timestamp}_${branch}.json`);
  try {
    _atomic_write_json(json_path, handoff_data);
  } catch (e) {
    con.print(`Error saving handoff JSON: ${e}`);
    return null;
  }

  // Save Markdown file
  const md_path = path.join(target_folder, `handoff_${timestamp}_${branch}.md`);
  try {
    let f = `# 🤝 Agent Handoff: ${branch} @ ${timestamp}\n\n`;
    f += `**Agent**: \`${agent.toUpperCase()}\`\n`;
    f += `**Goal**: ${goal}\n`;
    if (message) {
      f += `**Notes**: ${message}\n`;
    }
    f += `**Session ID**: \`${handoff_data.session_id}\`\n\n`;

    f += "## 📋 Checklist Status\n";
    const total = tasks.completed.length + tasks.in_progress.length + tasks.pending.length;
    if (total > 0) {
      f += `- **Progress**: ${tasks.completed.length} / ${total} tasks completed (${((tasks.completed.length / total) * 100).toFixed(1)}%)\n`;
    }
    if (tasks.in_progress.length) {
      f += "\n### ⏳ In Progress\n";
      for (const t of tasks.in_progress) f += `- [ ] ${t}\n`;
    }
    if (tasks.pending.length) {
      f += "\n### ⏹️ Pending\n";
      for (const t of tasks.pending) f += `- [ ] ${t}\n`;
    }
    if (tasks.completed.length) {
      f += "\n### ✅ Completed\n";
      for (const t of tasks.completed) f += `- [x] ${t}\n`;
    }

    f += "\n## 🛠️ Repository Status\n";
    f += `- **Active Branch**: \`${git_info.branch}\`\n`;
    if (git_info.changes.length) {
      f += "\n### 📂 Uncommitted Changes\n";
      for (const change of git_info.changes) f += `- \`${change}\`\n`;
    } else {
      f += "- ✨ No uncommitted changes.\n";
    }
    if (git_info.commits.length) {
      f += "\n### 📜 Recent Commits\n";
      for (const commit of git_info.commits) f += `- \`${commit}\`\n`;
    }
    writeFileSync(md_path, f, "utf-8");
  } catch (e) {
    con.print(`Error saving handoff Markdown: ${e}`);
    return null;
  }

  const db_synced = _sync_handoff_to_db(json_path, handoff_data);
  _log_context_event(
    "HANDOFF_CREATED",
    `Handoff ${handoff_data.handoff_id} created for ${agent}: ${handoff_data.goal}`,
    _handoff_context_metadata(json_path, handoff_data, { db_synced }),
  );
  con.print(`🤝 Handoff created successfully for ${agent.toUpperCase()}!`);
  con.print(`- Metadata: ${json_path}`);
  con.print(`- Summary: ${md_path}`);
  return json_path;
}

export function get_handoff_files(agent: string | null = null): string[] {
  if (!existsSync(HANDOFF_DIR)) {
    return [];
  }

  const files: string[] = [];
  const glob_json = (dir: string): string[] => {
    if (!existsSync(dir)) return [];
    try {
      return readdirSync(dir)
        .filter((n) => n.startsWith("handoff_") && n.endsWith(".json"))
        .map((n) => path.join(dir, n));
    } catch {
      return [];
    }
  };

  if (agent && agent.toLowerCase() in AGENT_FOLDERS) {
    files.push(...glob_json(path.join(HANDOFF_DIR, AGENT_FOLDERS[agent.toLowerCase()])));
  } else {
    files.push(...glob_json(HANDOFF_DIR));
    for (const folder of Object.values(AGENT_FOLDERS)) {
      files.push(...glob_json(path.join(HANDOFF_DIR, folder)));
    }
  }

  return files.sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
}

/** Claim a handoff and open a durable orchestration run around it. */
export function start_orchestration(
  agent: string | null = null,
  message: string = "",
  handoff_id: string | null = null,
): string | null {
  const con = _make_console();
  const [target_path, data] = _find_handoff(agent, handoff_id, OPEN_STATUSES);
  if (!target_path || !data) {
    con.print("No open handoff found to orchestrate.");
    return null;
  }

  const receiver = (process.env.NOUGEN_AGENT || detect_current_agent()).toLowerCase();
  const timestamp = _now_iso();
  if ((data.status || "open") === "open") {
    data.acknowledged_by = receiver;
    data.acknowledged_at = timestamp;
    if (message) {
      data.acknowledgement_note = message;
    }
  }

  const orchestration = _ensure_orchestration(data, receiver, timestamp);
  orchestration.checkpoints.push({ timestamp, agent: receiver, state: "started", message });
  data.status = "in_progress";
  _atomic_write_json(target_path, data);
  const db_synced = _sync_handoff_to_db(target_path, data);
  _log_context_event(
    "HANDOFF_ORCHESTRATION_STARTED",
    `Handoff ${data.handoff_id || path.basename(target_path, ".json")} orchestration started by ${receiver}: ${message || "started"}`,
    _handoff_context_metadata(target_path, data, {
      db_synced,
      run_id: orchestration.run_id,
      checkpoint_count: orchestration.checkpoints.length,
    }),
  );
  _append_markdown(target_path, "Orchestration Started", [
    `By: \`${receiver.toUpperCase()}\``,
    `At: ${timestamp}`,
    `Run ID: \`${orchestration.run_id}\``,
    `Note: ${message || "started"}`,
  ]);
  con.print(
    `Orchestration started for ${data.handoff_id || path.basename(target_path, ".json")} by ${receiver.toUpperCase()}.`,
  );
  return target_path;
}

/** Append an orchestration checkpoint to a handoff record. */
export function checkpoint_orchestration(
  agent: string | null = null,
  message: string = "",
  handoff_id: string | null = null,
  state: string = "in_progress",
): string | null {
  const con = _make_console();
  if (!["in_progress", "blocked", "complete"].includes(state)) {
    con.print(`Invalid orchestration state '${state}'.`);
    return null;
  }

  const [target_path, data] = _find_handoff(agent, handoff_id, OPEN_STATUSES);
  if (!target_path || !data) {
    con.print("No active handoff found for checkpoint.");
    return null;
  }

  const receiver = (process.env.NOUGEN_AGENT || detect_current_agent()).toLowerCase();
  const timestamp = _now_iso();
  const orchestration = _ensure_orchestration(data, receiver, timestamp);
  orchestration.checkpoints.push({ timestamp, agent: receiver, state, message });
  data.status = state;
  if (state === "complete") {
    data.completed_by = receiver;
    data.completed_at = timestamp;
  } else if (state === "blocked") {
    data.blocked_by = receiver;
    data.blocked_at = timestamp;
  }

  _atomic_write_json(target_path, data);
  const db_synced = _sync_handoff_to_db(target_path, data);
  const context_event_type =
    { blocked: "HANDOFF_ORCHESTRATION_BLOCKED", complete: "HANDOFF_ORCHESTRATION_COMPLETED" }[state] ??
    "HANDOFF_ORCHESTRATION_CHECKPOINT";
  _log_context_event(
    context_event_type,
    `Handoff ${data.handoff_id || path.basename(target_path, ".json")} orchestration checkpoint by ${receiver} as ${state}: ${message || state}`,
    _handoff_context_metadata(target_path, data, {
      db_synced,
      state,
      checkpoint_count: orchestration.checkpoints.length,
      run_id: orchestration.run_id,
    }),
  );
  _append_markdown(target_path, "Orchestration Checkpoint", [
    `By: \`${receiver.toUpperCase()}\``,
    `At: ${timestamp}`,
    `State: \`${state}\``,
    `Note: ${message || state}`,
  ]);
  con.print(`Checkpoint recorded for ${data.handoff_id || path.basename(target_path, ".json")} as ${state}.`);
  return target_path;
}

/** Mark an orchestration run complete. */
export function complete_orchestration(
  agent: string | null = null,
  message: string = "",
  handoff_id: string | null = null,
): string | null {
  return checkpoint_orchestration(agent, message, handoff_id, "complete");
}

/** Marks a handoff as received — the read-back / forcing function. */
export function acknowledge_handoff(
  agent: string | null = null,
  message: string = "",
  handoff_id: string | null = null,
): string | null {
  const con = _make_console();
  const files = get_handoff_files(agent);
  if (!files.length) {
    con.print("No handoff records found to acknowledge.");
    return null;
  }

  let target_path: string | null = null;
  for (const p of files) {
    let data: Json;
    try {
      data = JSON.parse(readFileSync(p, "utf-8"));
    } catch {
      continue;
    }
    if (handoff_id) {
      if (data.handoff_id === handoff_id) {
        target_path = p;
        break;
      }
    } else if ((data.status || "open") === "open") {
      target_path = p;
      break;
    }
  }

  if (target_path === null) {
    if (handoff_id) {
      con.print(`No handoff found with id '${handoff_id}'.`);
    } else {
      con.print("All handoffs are already acknowledged.");
    }
    return null;
  }

  const receiver = (process.env.NOUGEN_AGENT || detect_current_agent()).toLowerCase();
  let data: Json;
  try {
    data = JSON.parse(readFileSync(target_path, "utf-8"));
    data.status = "acknowledged";
    data.acknowledged_by = receiver;
    data.acknowledged_at = _now_iso();
    if (message) {
      data.acknowledgement_note = message;
    }
    _atomic_write_json(target_path, data);
    const db_synced = _sync_handoff_to_db(target_path, data);
    _log_context_event(
      "HANDOFF_ACKNOWLEDGED",
      `Handoff ${data.handoff_id || path.basename(target_path, ".json")} acknowledged by ${receiver}: ${message || "acknowledged"}`,
      _handoff_context_metadata(target_path, data, { db_synced }),
    );
  } catch (e) {
    con.print(`Error acknowledging handoff: ${e}`);
    return null;
  }

  // Append acknowledgement to the markdown sibling, if present.
  const md_path = target_path.replace(/\.json$/, ".md");
  if (existsSync(md_path)) {
    try {
      let out = "\n## ✅ Acknowledged\n";
      out += `- **By**: \`${receiver.toUpperCase()}\`\n`;
      out += `- **At**: ${data.acknowledged_at}\n`;
      if (message) {
        out += `- **Note**: ${message}\n`;
      }
      appendFileSync(md_path, out, "utf-8");
    } catch {
      /* best-effort */
    }
  }

  con.print(`✅ Handoff ${data.handoff_id || path.basename(target_path, ".json")} acknowledged by ${receiver.toUpperCase()}.`);
  return target_path;
}

export function list_handoffs(agent: string | null = null): void {
  const con = _make_console();
  const files = get_handoff_files(agent);
  if (!files.length) {
    con.print("No handoff records found.");
    return;
  }

  console.log("🤖 Agent Handoff History");
  console.log("Timestamp         | Agent    | Branch   | Active Goal | Tasks | Status");
  for (const p of files) {
    try {
      const data = JSON.parse(readFileSync(p, "utf-8"));
      const t = data.tasks;
      const total = t.completed.length + t.in_progress.length + t.pending.length;
      const pct = total > 0 ? `${t.completed.length}/${total}` : "0/0";
      const dt = new Date(data.timestamp);
      const pad = (n: number) => String(n).padStart(2, "0");
      const dts = `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())} ${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
      const agent_name = (data.agent || "generic").toUpperCase();
      let status_disp: string;
      if (data.status === "acknowledged") {
        status_disp = `✅ ${(data.acknowledged_by || "?").toUpperCase()}`;
      } else if (data.status === "in_progress") {
        status_disp = "in_progress";
      } else if (data.status === "complete") {
        status_disp = "complete";
      } else if (data.status === "blocked") {
        status_disp = "blocked";
      } else {
        status_disp = "🟡 open";
      }
      console.log(`${dts} | ${agent_name} | ${data.git.branch} | ${data.goal} | ${pct} | ${status_disp}`);
    } catch {
      /* skip malformed */
    }
  }
}

export function show_latest_handoff(agent: string | null = null): void {
  const con = _make_console();
  const files = get_handoff_files(agent);
  if (!files.length) {
    con.print("No handoff records found.");
    return;
  }

  const latest_path = files[0];
  try {
    const data = JSON.parse(readFileSync(latest_path, "utf-8"));
    const git_info = data.git;
    const tasks = data.tasks;
    const agent_name = (data.agent || "generic").toUpperCase();

    let ack_line: string;
    if (data.status === "acknowledged") {
      ack_line = `Status: ✅ acknowledged by ${(data.acknowledged_by || "?").toUpperCase()} at ${data.acknowledged_at || "?"}\n`;
    } else if (["in_progress", "blocked", "complete"].includes(data.status)) {
      const orchestration = data.orchestration || {};
      const checkpoints = orchestration.checkpoints || [];
      ack_line =
        `Status: ${data.status}\n` +
        `Run ID: ${orchestration.run_id || "?"}\n` +
        `Checkpoints: ${checkpoints.length}\n`;
    } else {
      ack_line = "Status: 🟡 OPEN — run `nougen handoff ack` to claim it\n";
    }

    console.log("🤝 Latest Agent Handoff Summary");
    console.log(
      `Timestamp: ${data.timestamp}\n` +
        `Agent: ${agent_name}\n` +
        `Goal: ${data.goal}\n` +
        `Session ID: ${data.session_id}\n` +
        `Notes: ${data.message || "None"}\n` +
        ack_line,
    );

    let checklist = "";
    const total = tasks.completed.length + tasks.in_progress.length + tasks.pending.length;
    if (total > 0) {
      checklist += `Completion Rate: ${tasks.completed.length}/${total} (${((tasks.completed.length / total) * 100).toFixed(1)}%)\n\n`;
    }
    if (tasks.in_progress.length) {
      checklist += "⏳ In Progress:\n";
      for (const t of tasks.in_progress) checklist += `  - ${t}\n`;
    }
    if (tasks.pending.length) {
      checklist += "\n⏹️ Pending:\n";
      for (const t of tasks.pending) checklist += `  - ${t}\n`;
    }
    if (tasks.completed.length) {
      checklist += "\n✅ Completed:\n";
      for (const t of tasks.completed.slice(0, 5)) checklist += `  - ${t}\n`;
      if (tasks.completed.length > 5) {
        checklist += `  ... and ${tasks.completed.length - 5} more.\n`;
      }
    }
    console.log("📋 Task Checklist");
    console.log(checklist || "No tasks defined.");

    let repo = `Active Branch: ${git_info.branch}\n`;
    if (git_info.changes.length) {
      repo += "\n📂 Uncommitted Changes:\n";
      for (const change of git_info.changes) repo += `  - ${change}\n`;
    } else {
      repo += "\n✨ No uncommitted changes.\n";
    }
    if (git_info.commits.length) {
      repo += "\n📜 Recent Commits:\n";
      for (const commit of git_info.commits) repo += `  - ${commit}\n`;
    }
    console.log("🛠️ Repository Status");
    console.log(repo);
  } catch (e) {
    con.print(`Error loading handoff details: ${e}`);
  }
}

// keep tmpdir import used (parity with Python tempfile usage); harmless reference.
void tmpdir;

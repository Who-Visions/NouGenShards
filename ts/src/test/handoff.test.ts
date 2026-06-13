/**
 * Port of tests/test_handoff.py — cross-agent session handoff notes.
 *
 * Isolation strategy (the TS analogue of the Python tmp_path + monkeypatch
 * fixture `setup_handoff_env`):
 *   - handoff.ts resolves HANDOFF_DIR from NOUGEN_HANDOFF_DIR at module-load time,
 *     so we set it to a fresh temp dir BEFORE `await import("../nougen_shards/handoff.js")`.
 *   - isolateEnv() additionally steers homedir() (USERPROFILE/HOME) so the
 *     nougen_context side-channel writes its session.db under the temp root, never
 *     the real ~/.nougen — mirroring the Python monkeypatch of SESSION_DB_PATH.
 *   - node:test runs each file in its own process, so this file-level setup gives
 *     clean per-file isolation.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { isolateEnv, captureStdout } from "./_helpers.js";

// 1) Point HANDOFF_DIR at a fresh temp dir BEFORE importing the module.
const HANDOFF_DIR = mkdtempSync(path.join(tmpdir(), "ngs-handoff-"));
process.env.NOUGEN_HANDOFF_DIR = HANDOFF_DIR;

// handoff.ts freezes HANDOFF_DIR at import (faithful to the Python module const),
// so per-test env reassignment is a no-op. To isolate a test, wipe the shared dir.
function cleanHandoffDir(): void {
  rmSync(HANDOFF_DIR, { recursive: true, force: true });
  mkdirSync(HANDOFF_DIR, { recursive: true });
}
// 2) Isolate home / vault so the nougen_context mirror + brain scan stay in temp.
isolateEnv("ngs-handoff-home-");
// 3) Several Python tests set NOUGEN_AGENT; default it to "claude" (the others
//    override it per-test as needed).
process.env.NOUGEN_AGENT = "claude";
// Make sure we do not accidentally pick up a real Antigravity brain dir.
delete process.env.NOUGEN_HANDOFF_TASKS_DIR;

const handoff = await import("../nougen_shards/handoff.js");
const { createDatabase } = await import("../nougen_shards/_db.js");
const nougen_context = await import("../nougen_shards/nougen_context.js");

const flush = () => new Promise((r) => setTimeout(r, 50));

test("handoff_creation: file exists, json fields + db row", async () => {
  let json_path: string | null = null;
  await captureStdout(() => {
    json_path = handoff.create_handoff("Testing handoff system", "gemini");
  });

  assert.notEqual(json_path, null);
  assert.ok(existsSync(json_path!));

  // Created under the agent subdirectory.
  const subdir_name = handoff.AGENT_FOLDERS["gemini"];
  assert.equal(path.dirname(json_path!), path.join(HANDOFF_DIR, subdir_name));

  // Markdown sibling exists.
  const md_path = json_path!.replace(/\.json$/, ".md");
  assert.ok(existsSync(md_path));

  const data = JSON.parse(readFileSync(json_path!, "utf-8"));
  assert.equal(data.agent, "gemini");
  assert.equal(data.message, "Testing handoff system");
  assert.ok("git" in data);
  assert.ok("tasks" in data);

  const conn = createDatabase(handoff.get_handoff_db_path());
  const row = conn
    .prepare("SELECT agent, status, goal FROM handoff_records WHERE handoff_id = ?")
    .get(data.handoff_id) as any;
  conn.close();
  assert.equal(row.agent, "gemini");
  assert.equal(row.status, "open");
  assert.equal(row.goal, data.goal);
});

test("handoff_creation_generic: generic agent still writes a file", async () => {
  let json_path: string | null = null;
  await captureStdout(() => {
    json_path = handoff.create_handoff("Testing default fallback", "generic");
  });
  assert.notEqual(json_path, null);
  assert.ok(existsSync(json_path!));
});

test("goal passthrough: explicit goal, open status, null ack", async () => {
  let json_path: string | null = null;
  await captureStdout(() => {
    json_path = handoff.create_handoff("x", "claude", "Ship the launcher fix");
  });
  const data = JSON.parse(readFileSync(json_path!, "utf-8"));
  assert.equal(data.goal, "Ship the launcher fix");
  assert.equal(data.status, "open");
  assert.equal(data.acknowledged_by, null);
  assert.ok(data.handoff_id);
});

test("acknowledge flow: flips status to acknowledged, then nothing left", async () => {
  // Wipe the shared (frozen) handoff dir so older open handoffs don't interfere.
  cleanHandoffDir();
  process.env.NOUGEN_AGENT = "claude";

  let acked: string | null = null;
  await captureStdout(() => {
    handoff.create_handoff("please pick up", "gemini", "G");
    acked = handoff.acknowledge_handoff();
  });
  assert.notEqual(acked, null);
  const data = JSON.parse(readFileSync(acked!, "utf-8"));
  assert.equal(data.status, "acknowledged");
  assert.equal(data.acknowledged_by, "claude");
  assert.notEqual(data.acknowledged_at, null);

  // Nothing open left to acknowledge.
  let second: string | null = "x";
  await captureStdout(() => {
    second = handoff.acknowledge_handoff();
  });
  assert.equal(second, null);

  process.env.NOUGEN_HANDOFF_DIR = HANDOFF_DIR;
});

test("start_orchestration claims the open handoff", async () => {
  const dir = mkdtempSync(path.join(tmpdir(), "ngs-handoff-start-"));
  process.env.NOUGEN_HANDOFF_DIR = dir;
  process.env.NOUGEN_AGENT = "codex";

  let created: string | null = null;
  let started: string | null = null;
  await captureStdout(() => {
    created = handoff.create_handoff("ready", "gemini", "G");
    started = handoff.start_orchestration(null, "taking over");
  });
  assert.equal(started, created);
  const data = JSON.parse(readFileSync(started!, "utf-8"));
  assert.equal(data.status, "in_progress");
  assert.equal(data.acknowledged_by, "codex");
  assert.equal(data.orchestration.started_by, "codex");
  assert.equal(data.orchestration.checkpoints[0].state, "started");

  process.env.NOUGEN_HANDOFF_DIR = HANDOFF_DIR;
  process.env.NOUGEN_AGENT = "claude";
});

test("checkpoint + complete orchestration lifecycle", async () => {
  const dir = mkdtempSync(path.join(tmpdir(), "ngs-handoff-cp-"));
  process.env.NOUGEN_HANDOFF_DIR = dir;
  process.env.NOUGEN_AGENT = "codex";

  let started: string | null = null;
  let completed: string | null = null;
  await captureStdout(() => {
    handoff.create_handoff("ready", "gemini", "G");
    started = handoff.start_orchestration(null, "start");
    handoff.checkpoint_orchestration(null, "halfway", null);
  });

  let data = JSON.parse(readFileSync(started!, "utf-8"));
  assert.equal(data.status, "in_progress");
  assert.equal(data.orchestration.checkpoints.at(-1).message, "halfway");

  await captureStdout(() => {
    completed = handoff.complete_orchestration(null, "done");
  });
  assert.equal(completed, started);
  data = JSON.parse(readFileSync(started!, "utf-8"));
  assert.equal(data.status, "complete");
  assert.equal(data.completed_by, "codex");
  assert.equal(data.orchestration.checkpoints.at(-1).state, "complete");

  const conn = createDatabase(handoff.get_handoff_db_path());
  const statusRow = conn
    .prepare("SELECT status FROM handoff_records WHERE handoff_id = ?")
    .get(data.handoff_id) as any;
  const cpRow = conn
    .prepare("SELECT COUNT(*) AS c FROM handoff_checkpoints WHERE handoff_id = ?")
    .get(data.handoff_id) as any;
  conn.close();
  assert.equal(statusRow.status, "complete");
  assert.equal(cpRow.c, 3);

  process.env.NOUGEN_HANDOFF_DIR = HANDOFF_DIR;
  process.env.NOUGEN_AGENT = "claude";
});

test("handoff transitions are mirrored to context mode", async () => {
  const dir = mkdtempSync(path.join(tmpdir(), "ngs-handoff-ctx-"));
  process.env.NOUGEN_HANDOFF_DIR = dir;
  process.env.NOUGEN_AGENT = "codex";

  let created: string | null = null;
  await captureStdout(() => {
    created = handoff.create_handoff("ready", "gemini", "Context mirror");
    handoff.start_orchestration(null, "start");
    handoff.checkpoint_orchestration(null, "halfway");
    handoff.complete_orchestration(null, "done");
  });

  // The context mirror is fire-and-forget (async, no await) — let it flush.
  await flush();

  const data = JSON.parse(readFileSync(created!, "utf-8"));
  const events = nougen_context.search_events(data.handoff_id, 10);
  const event_types = new Set(events.map((e: any) => e.event_type));

  assert.ok(event_types.has("HANDOFF_CREATED"));
  assert.ok(event_types.has("HANDOFF_ORCHESTRATION_STARTED"));
  assert.ok(event_types.has("HANDOFF_ORCHESTRATION_CHECKPOINT"));
  assert.ok(event_types.has("HANDOFF_ORCHESTRATION_COMPLETED"));

  const completed = events.find(
    (e: any) => e.event_type === "HANDOFF_ORCHESTRATION_COMPLETED",
  ) as any;
  const metadata = JSON.parse(completed.metadata);
  assert.equal(metadata.handoff_id, data.handoff_id);
  assert.equal(metadata.state, "complete");

  process.env.NOUGEN_HANDOFF_DIR = HANDOFF_DIR;
  process.env.NOUGEN_AGENT = "claude";
});

test("rebuild_handoff_db reindexes from JSON files", async () => {
  cleanHandoffDir();
  process.env.NOUGEN_AGENT = "claude";

  let createdPath: string | null = null;
  await captureStdout(() => {
    createdPath = handoff.create_handoff("old file", "gemini", "G");
  });

  // Drop the DB (and WAL/SHM siblings) so rebuild starts from JSON only.
  const db_path = handoff.get_handoff_db_path();
  for (const suffix of ["", "-wal", "-shm"]) {
    const candidate = `${db_path}${suffix}`;
    if (existsSync(candidate)) {
      const { rmSync } = await import("node:fs");
      rmSync(candidate, { force: true });
    }
  }
  assert.ok(!existsSync(db_path));

  let count = 0;
  await captureStdout(() => {
    count = handoff.rebuild_handoff_db();
  });
  assert.equal(count, 1);

  const conn = createDatabase(db_path);
  const cRow = conn.prepare("SELECT COUNT(*) AS c FROM handoff_records").get() as any;
  const pRow = conn.prepare("SELECT path FROM handoff_records").get() as any;
  conn.close();
  assert.equal(cRow.c, 1);
  assert.equal(pRow.path, createdPath);

  process.env.NOUGEN_HANDOFF_DIR = HANDOFF_DIR;
});

test("get_handoff_files: count, agent filter, and ordering", async () => {
  cleanHandoffDir();

  await captureStdout(() => {
    handoff.create_handoff("Handoff 1", "gemini");
    handoff.create_handoff("Handoff 2", "claude");
  });

  const files = handoff.get_handoff_files();
  assert.equal(files.length, 2);

  const gemini_files = handoff.get_handoff_files("gemini");
  assert.equal(gemini_files.length, 1);

  // UI output functions must not throw.
  await captureStdout(() => {
    handoff.list_handoffs();
    handoff.show_latest_handoff();
  });

  process.env.NOUGEN_HANDOFF_DIR = HANDOFF_DIR;
});

test("detect_current_agent honours NOUGEN_AGENT override", () => {
  const prev = process.env.NOUGEN_AGENT;
  process.env.NOUGEN_AGENT = "codex";
  assert.equal(handoff.detect_current_agent(), "codex");
  process.env.NOUGEN_AGENT = prev;
});

test("atomic write produces valid JSON with no leftover temp files", async () => {
  const dir = mkdtempSync(path.join(tmpdir(), "ngs-handoff-atomic-"));
  process.env.NOUGEN_HANDOFF_DIR = dir;

  let p: string | null = null;
  await captureStdout(() => {
    p = handoff.create_handoff("integrity", "ollama");
  });
  const data = JSON.parse(readFileSync(p!, "utf-8"));
  assert.ok(data.handoff_id);

  const leftovers = readdirSync(path.dirname(p!)).filter((n) => n.endsWith(".tmp"));
  assert.deepEqual(leftovers, []);

  process.env.NOUGEN_HANDOFF_DIR = HANDOFF_DIR;
});

test("parse_task_md parses checklist states", async () => {
  const dir = mkdtempSync(path.join(tmpdir(), "ngs-handoff-task-"));
  const taskPath = path.join(dir, "task.md");
  const { writeFileSync } = await import("node:fs");
  writeFileSync(
    taskPath,
    ["- [x] done one", "- [/] working two", "- [ ] pending three", "- [ ] pending four", "random line"].join(
      "\n",
    ),
    "utf-8",
  );

  const parsed = handoff.parse_task_md(taskPath);
  assert.deepEqual(parsed.completed, ["done one"]);
  assert.deepEqual(parsed.in_progress, ["working two"]);
  assert.deepEqual(parsed.pending, ["pending three", "pending four"]);

  // Missing file → all empty.
  const missing = handoff.parse_task_md(path.join(dir, "nope.md"));
  assert.deepEqual(missing, { completed: [], in_progress: [], pending: [] });
});

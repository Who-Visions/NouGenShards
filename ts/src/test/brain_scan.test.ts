/**
 * Port of tests/test_brain_scan.py — Brain Scan / Memory Recon engine.
 *
 * Most tests here are pure (classifiers/redaction/parsers operate on strings &
 * temp files, no DB). The import tests reach core.capture, so we call
 * isolateEnv() BEFORE importing — this redirects both the shards DB *and*
 * homedir(), so GLOBAL_ROOTS (registry.ts resolves them from homedir() at load)
 * point at a fresh empty temp dir. That is the TS analogue of the Python autouse
 * `mock_global_roots` fixture (which repointed scanner.GLOBAL_ROOTS at a
 * nonexistent dummy): the global scan finds nothing, so run_import sees only the
 * temp project files.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { isolateEnv } from "./_helpers.js";

isolateEnv("ngs-brain-");

const { classify_file, detect_tool } = await import("../nougen_shards/brain_scan/classifiers.js");
const { redact_content } = await import("../nougen_shards/brain_scan/redaction.js");
const { parse_universal } = await import("../nougen_shards/brain_scan/parsers.js");
const { scan_environment } = await import("../nougen_shards/brain_scan/scanner.js");
const { run_import } = await import("../nougen_shards/brain_scan/importer.js");

/** Fresh temp dir per test (Python tmp_path analogue). */
function tmp(prefix = "ngs-bs-"): string {
  return mkdtempSync(path.join(tmpdir(), prefix));
}

test("test_detect_tool", () => {
  // classifiers take absolute path strings (not pathlib.Path).
  assert.equal(detect_tool("/home/user/.claude/history.jsonl"), "claude");
  assert.equal(detect_tool("/home/user/.cursor/workspace/state.json"), "cursor");
  assert.equal(detect_tool("/home/user/.gemini/settings.json"), "gemini");
  assert.equal(detect_tool("/home/user/my_project/AGENTS.md"), "unknown");
});

test("test_classify_file", () => {
  assert.equal(classify_file("conversation_123.json"), "high");
  assert.equal(classify_file("settings.json"), "medium");
  assert.equal(classify_file("cache_blob.bin"), "low");
  assert.equal(classify_file("node_modules/bla/package.json"), "low");
  assert.equal(classify_file("unknown_file.md"), "medium");
  assert.equal(classify_file("unknown_file.xyz"), "low");
});

test("test_redact_content", () => {
  const content =
    'Here is my key: "sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"\n' +
    "And an openai key: sk-abcdefghijklmnopqrstuvwxyz1234567890\n" +
    "Also a fake token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c";
  const redacted = redact_content(content);
  assert.ok(!redacted.includes("sk-ant-"));
  assert.ok(redacted.includes("<REDACTED_ANTHROPIC_KEY>"));
  assert.ok(redacted.includes("<REDACTED_OPENAI_KEY>"));
  assert.ok(redacted.includes("<REDACTED_JWT>"));
  assert.ok(redacted.includes("Here is my key:"));
});

test("test_redact_db_url_without_path", () => {
  // Regression: a DB URL with no trailing /db must still redact the password.
  const redacted = redact_content("conn = postgres://admin:s3cr3tP@ss@db.internal:5432");
  assert.ok(!redacted.includes("s3cr3tP"));
  assert.ok(redacted.includes("<REDACTED_DB_URL>"));
});

test("test_redact_sk_proj_key", () => {
  // Regression: newer sk-proj-/sk-svcacct- keys contain - and _.
  const redacted = redact_content("OPENAI=sk-proj-abc_DEF-ghi0123456789jklmnopqrstuv");
  assert.ok(!redacted.includes("sk-proj-abc"));
  assert.ok(redacted.includes("<REDACTED_OPENAI_KEY>"));
});

test("test_is_safe_dir", () => {
  // _is_safe_dir is module-private in scanner.ts (not exported), exactly as in
  // Python where it's an underscore helper. Its one consumer is scan_environment,
  // which only emits candidates whose *directory* passed _is_safe_dir. We port the
  // BEHAVIOR by scanning a temp project: a file under a safe `.claude` dir must be
  // picked up, while files under danger/skip dirs (.ssh, .aws, node_modules) are
  // dropped — proving _is_safe_dir(...) returns True/False for those exact parts.
  const proj = tmp();
  // Safe: high-signal file inside .claude (PROJECT_ROOT_NAMES + safe dir)
  const claudeDir = path.join(proj, ".claude");
  mkdirSync(claudeDir, { recursive: true });
  writeFileSync(path.join(claudeDir, "conversations.jsonl"), '{"role":"user","content":"hi"}');
  // Unsafe DANGER_ZONE dirs
  const sshDir = path.join(proj, ".ssh");
  mkdirSync(sshDir, { recursive: true });
  writeFileSync(path.join(sshDir, "conversation.jsonl"), '{"role":"user","content":"x"}');
  const awsDir = path.join(proj, ".aws");
  mkdirSync(awsDir, { recursive: true });
  writeFileSync(path.join(awsDir, "conversation.jsonl"), '{"role":"user","content":"x"}');
  // Unsafe SKIP_DIR
  const nm = path.join(proj, "node_modules", "bla");
  mkdirSync(nm, { recursive: true });
  writeFileSync(path.join(nm, "conversation.jsonl"), '{"role":"user","content":"x"}');

  const cands = scan_environment(proj, true);
  const dirs = cands.map((c) => path.dirname(path.resolve(c.path)));
  // _is_safe_dir(.claude) is True -> present
  assert.ok(dirs.includes(path.resolve(claudeDir)));
  // _is_safe_dir(.ssh/.aws/node_modules) is False -> absent
  assert.ok(!dirs.some((d) => d.includes(`${path.sep}.ssh`)));
  assert.ok(!dirs.some((d) => d.includes(`${path.sep}.aws`)));
  assert.ok(!dirs.some((d) => d.includes("node_modules")));
});

test("test_parse_json", () => {
  const dir = tmp();
  const f = path.join(dir, "chat.json");
  writeFileSync(f, '{"title": "Test Chat", "messages": [{"role": "user", "content": "hi"}]}');
  const records = parse_universal(f, "claude", false);
  assert.equal(records.length, 1);
  assert.equal(records[0].title, "Test Chat");
  assert.ok(records[0].content.includes("messages"));
});

test("test_parse_jsonl", () => {
  const dir = tmp();
  const f = path.join(dir, "history.jsonl");
  writeFileSync(f, '{"role": "user", "content": "hello"}\n{"role": "assistant", "content": "hi"}');
  const records = parse_universal(f, "claude", false);
  assert.equal(records.length, 2);
  assert.equal(records[0].role, "user");
  assert.equal(records[1].role, "assistant");
});

test("test_parse_markdown", () => {
  const dir = tmp();
  const f = path.join(dir, "AGENTS.md");
  writeFileSync(f, "# Agent Rules\nDo this.");
  const records = parse_universal(f, "unknown", true);
  assert.equal(records.length, 1);
  assert.equal(records[0].source_kind, "markdown_document");
  assert.equal(records[0].title, "AGENTS.md");
});

test("test_dry_run_import", () => {
  // Setup a dummy project dir
  const root = tmp();
  const proj = path.join(root, "myproj");
  mkdirSync(proj, { recursive: true });
  writeFileSync(path.join(proj, "CLAUDE.md"), "Rule 1");
  const claudeDir = path.join(proj, ".claude");
  mkdirSync(claudeDir, { recursive: true });
  writeFileSync(path.join(claudeDir, "conversations.jsonl"), '{"role": "user", "content": "hi"}');

  // Positional signature: run_import(project_path, include_unknown, source_filter, redact, confirm)
  const result = run_import(proj, false, null, true, false);
  // Both files should be picked up (CLAUDE.md is PROJECT_FILES, .claude is PROJECT_ROOT_NAMES)
  assert.equal(result.files_scanned, 2);
  // Estimation should be > 0
  assert.ok(result.records_parsed > 0);
  assert.equal(result.shards_created, 0); // Dry run means nothing actually hits DB
});

test("test_confirm_import", () => {
  // Python monkeypatched core.capture -> always True. Here isolateEnv() redirected
  // the shards DB to a temp dir, so the real capture writes to a throwaway DB and
  // returns True for fresh content — same observable outcome, no live DB touched.
  const root = tmp();
  const proj = path.join(root, "myproj2");
  mkdirSync(proj, { recursive: true });
  writeFileSync(path.join(proj, "GEMINI.md"), "Rule 2");

  const result = run_import(proj, false, null, true, true);
  assert.equal(result.files_scanned, 1);
  assert.equal(result.records_parsed, 1);
  assert.equal(result.shards_created, 1);
});

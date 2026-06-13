/**
 * Port of tests/test_cli.py — NouGenShards CLI command coverage.
 *
 * Mechanics adaptation: the Python tests call `cli.cmd_*` directly and patch
 * module internals (`shards.capture`, `federation.federated_retrieve`, ...).
 * In the TS port the `cmd_*` functions are module-private — only `main()`,
 * `parse_args`, and `VERSION` are exported. So each intent is driven through
 * `main()` by setting `process.argv` and capturing stdout, exercising the real
 * core/vault modules against an isolated temp substrate (the `isolateEnv`
 * fixture is the `tmp_path`/monkeypatch analogue; no internal mocking needed).
 *
 * `main()` calls `process.exit(0)` on the no-args banner path, so that test
 * stubs `process.exit` to a throw and catches it (capsys + SystemExit analogue).
 */
import { test, before, afterEach } from "node:test";
import assert from "node:assert/strict";
import { isolateEnv, captureStdout } from "./_helpers.js";

isolateEnv("ngs-cli-");
const cli = await import("../nougen_shards/cli.js");
const shards = await import("../nougen_shards/core.js");

before(() => {
  shards.init_db(1);
});

const ORIG_ARGV = process.argv;

afterEach(() => {
  process.argv = ORIG_ARGV;
});

/** Run `main()` with the given CLI tokens (after the `node script` prefix). */
async function runCli(tokens: string[]): Promise<string> {
  process.argv = ["node", "cli.js", ...tokens];
  return captureStdout(async () => {
    await cli.main();
  });
}

/** Run `main()` capturing both stdout and the exit code from a stubbed exit. */
async function runCliExpectExit(tokens: string[]): Promise<{ out: string; code: number | undefined }> {
  process.argv = ["node", "cli.js", ...tokens];
  const origExit = process.exit;
  let code: number | undefined;
  // stub throws to unwind instead of terminating the process.
  process.exit = ((c?: number) => {
    code = c;
    throw new Error(`__exit__:${c}`);
  }) as typeof process.exit;
  try {
    const out = await captureStdout(async () => {
      try {
        await cli.main();
      } catch (e) {
        if (!(e instanceof Error) || !e.message.startsWith("__exit__:")) throw e;
      }
    });
    return { out, code };
  } finally {
    process.exit = origExit;
  }
}

// 1) init -> banner + IGNITION COMPLETE, calls shards.init_db.
test("cmd_init prints ignition banner", async () => {
  const out = await runCli(["init"]);
  assert.ok(out.includes("Initializing the Metameric Memory Engine..."));
  assert.ok(out.includes("[IGNITION COMPLETE]"));
});

// 2) add -> capture with tags, "Shard captured!".
test("cmd_add captures a shard with tags", async () => {
  const out = await runCli(["add", "Test content alpha", "--tags", "tag1,tag2"]);
  assert.ok(out.includes("✅ Shard captured!"));
  // Verify the real substrate actually persisted it (the capture intent).
  const found = shards.retrieve("Test content alpha");
  assert.ok(found.length >= 1);
  // tags round-trip through the DB as a JSON string column.
  assert.deepEqual(JSON.parse(String(found[0].tags)), ["tag1", "tag2"]);
});

// 3) search -> federated retrieve output with score header.
test("cmd_search prints ranked fabric results", async () => {
  await runCli(["add", "Searchable beacon content", "--tags", "beacon"]);
  const out = await runCli(["search", "beacon"]);
  assert.ok(out.includes("Found"));
  assert.ok(out.includes("records across the fabric"));
  assert.ok(out.includes("Final Score:"));
});

// 4) mark -> usefulness prior adjusted message.
test("cmd_mark updates a shard prior", async () => {
  await runCli(["add", "Markable target shard", "--tags", "mark"]);
  const id = shards.retrieve("Markable target shard")[0].id;
  const out = await runCli(["mark", String(id), "--worked"]);
  assert.ok(out.includes(`Shard #${id} updated`));
});

// 5) status -> substrate status with DB line + size.
test("cmd_status reports substrate stats", async () => {
  await runCli(["add", "Status seed shard", "--tags", "status"]);
  const out = await runCli(["status"]);
  assert.ok(out.includes("NouGenShards Substrate Status:"));
  assert.ok(out.includes("DB #1:"));
  assert.ok(out.includes("MB / 1024 MB"));
  assert.ok(out.includes("Total records in memory:"));
});

// 6) config set -> "Configuration updated".
test("cmd_config set echoes the update", async () => {
  const out = await runCli(["config", "set", "test_key", "test_value"]);
  assert.ok(out.includes("✅ Configuration updated"));
  assert.ok(out.includes("test_key = test_value"));
});

// 7) ingest -> read file + capture, "Ingestion complete".
test("cmd_ingest captures file content", async () => {
  const { mkdtempSync, writeFileSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const path = await import("node:path");
  const dir = mkdtempSync(path.join(tmpdir(), "ngs-ingest-"));
  const file = path.join(dir, "doc.md");
  writeFileSync(file, "ingestible markdown content", "utf-8");

  const out = await runCli(["ingest", file]);
  assert.ok(out.includes(`Ingesting ${file}`));
  assert.ok(out.includes("✅ Ingestion complete"));
});

// 8) main no-args -> banner + exit(0) (SystemExit code 0 analogue).
test("main with no args prints banner and exits 0", async () => {
  const { out, code } = await runCliExpectExit([]);
  assert.equal(code, 0);
  assert.ok(out.includes("🪩 NouGenShards CLI"));
});

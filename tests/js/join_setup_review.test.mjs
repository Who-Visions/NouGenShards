// Regression tests for the review of PR #1031 (2026-11-11): shell injection
// through the account id, and setup destroying a working install before its
// downloads were verified.
import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setupCmd, setupSh, setupArgs } from "../../workers/join/worker.js";

const good = { id: "sample-acct", token: "tok", tunnel: "tun", port: 4500, url: "https://sample-acct.example.test" };

test("an account id that is not a plain folder name never reaches a script", () => {
  for (const id of ["$(touch pwned)", "`id`", "a b", "a'b", "a\"b", "../up", "a/b", "a\\b", "A-Upper", "-lead", "", "x".repeat(64), "a;b", "a\nb"]) {
    assert.throws(() => setupSh({ ...good, id }), /safe folder name/, JSON.stringify(id));
    assert.throws(() => setupCmd({ ...good, id }), /safe folder name/, JSON.stringify(id));
  }
  for (const port of [0, 80, 70000, 4500.5, "4500; rm -rf ~", NaN, undefined]) {
    assert.throws(() => setupSh({ ...good, port }), /port is not usable/, String(port));
    assert.throws(() => setupCmd({ ...good, port }), /port is not usable/, String(port));
  }
  assert.equal(setupArgs({ ...good, port: "4500" }).port, 4500);
});

test("the account folder is single-quoted in sh, so nothing in it can expand", () => {
  const sh = setupSh(good);
  assert.ok(sh.includes(`H="$B"/'sample-acct'`));
  assert.ok(!/H="\$B\/[^"]*sample-acct/.test(sh), "the id must not sit inside double quotes");
});

const order = (text, ...needles) => {
  const at = needles.map((n) => {
    const i = text.indexOf(n);
    assert.ok(i >= 0, "missing: " + n);
    return i;
  });
  for (let i = 1; i < at.length; i++) assert.ok(at[i - 1] < at[i], `"${needles[i - 1]}" must come before "${needles[i]}"`);
};

test("windows: every download is verified before anything running is touched", () => {
  const cmd = setupCmd(good);
  order(cmd,
    "Get-FileHash -Algorithm SHA256 $supNew",       // supervisor verified
    "archive/refs/heads/main.zip",                  // new code downloaded
    "The NouGen download was incomplete",           // ...and checked
    "Set-Content -Path $hold",                      // only now: mark the account as updating
    "Stop-Process -Id $procId",                     // stop this account
    "Remove-Item -Recurse -Force $src",             // remove the old code
    "Move-Item $fresh $src",                        // put the new code in
    "Move-Item -Force $supNew $sup",                // swap the supervisor
    "finally { Remove-Item -Force -ErrorAction SilentlyContinue $hold }",
    "& $sup install");
  assert.ok(cmd.includes("Nothing was changed"), "a failed download must say so");
});

test("windows: the shared supervisor is stopped only when it cannot hold an account", () => {
  const cmd = setupCmd(good);
  const stop = cmd.split("\r\n").find((l) => l.includes("Get-Process nougen-supervisor"));
  assert.ok(stop && stop.trim().startsWith("if (-not $holds)"), "stopping the supervisor must be conditional");
  assert.match(cmd, /127\.0\.0\.1:47411\/status/);
  // Only this account's own folder is matched when stopping processes, not a sibling that starts the same.
  assert.ok(cmd.includes("[regex]::Escape($td + '\\')"));
});

test("unix: every download is verified before anything running is touched", () => {
  const sh = setupSh(good);
  order(sh,
    'if [ "$(sum "$S.download")" != "$W" ]',
    "archive/refs/heads/main.zip",
    "The NouGen download was incomplete",
    ": > updating",
    'pkill -f "$H/NouGenShards"',
    "rm -rf NouGenShards; mv incoming/NouGenShards-main NouGenShards",
    'mv -f "$SN" "$S"',
    "rm -f updating",
    '"$S" install');
  const stop = sh.split("\n").findIndex((l) => l.includes('pkill -f "$B/nougen-supervisor"'));
  assert.ok(sh.split("\n").slice(0, stop).some((l) => l.includes('grep -q \'"holds":true\'')), "stopping the supervisor must be conditional");
  assert.ok(!sh.includes("pkill -x"), "process names are cut to 15 characters; match the full path");
});

const hasSh = spawnSync("sh", ["-c", "exit 0"]).status === 0;

test("unix: the generated script is valid sh", { skip: !hasSh }, () => {
  const dir = mkdtempSync(join(tmpdir(), "ngsetup-"));
  const file = join(dir, "setup.sh");
  writeFileSync(file, setupSh(good));
  execFileSync("sh", ["-n", file]);
});

test("unix: a fingerprint mismatch stops before any account file is touched", { skip: !hasSh }, () => {
  // Run the real script with stand-ins for the network: curl "downloads" a
  // wrong file. The account's existing code must still be there afterwards.
  const home = mkdtempSync(join(tmpdir(), "nghome-"));
  const bin = join(home, "bin");
  const acct = join(home, ".nougen-node", "sample-acct");
  execFileSync("sh", ["-c", `mkdir -p "$1" "$2/NouGenShards" && echo keep > "$2/NouGenShards/app.py"`, "sh", bin, acct]);
  writeFileSync(join(bin, "curl"), `#!/bin/sh\nwhile [ $# -gt 0 ]; do if [ "$1" = "-o" ]; then echo tampered > "$2"; fi; shift; done\nexit 0\n`, { mode: 0o755 });
  for (const tool of ["pkill", "pgrep"]) writeFileSync(join(bin, tool), `#!/bin/sh\necho "$0 $*" >> "${home.replace(/\\/g, "/")}/killed"\nexit 0\n`, { mode: 0o755 });
  const file = join(home, "setup.sh");
  writeFileSync(file, setupSh(good));
  const r = spawnSync("sh", [file], { env: { ...process.env, HOME: home, PATH: bin + (process.platform === "win32" ? ";" : ":") + process.env.PATH }, encoding: "utf8" });
  assert.notEqual(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /did not match its fingerprint\. Nothing was changed/);
  assert.ok(existsSync(join(acct, "NouGenShards", "app.py")), "the working install was removed");
  assert.ok(!existsSync(join(home, "killed")), "something was stopped before the download was verified");
  assert.ok(!existsSync(join(acct, "updating")), "the updating marker was left behind");
});

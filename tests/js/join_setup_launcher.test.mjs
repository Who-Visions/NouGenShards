// The Windows setup file must not carry the flag security products treat as a dropper marker.
import test from "node:test";
import assert from "node:assert/strict";
import { setupCmd } from "../../workers/join/worker.js";

const t = { id: "abc", token: "tok", tunnel: "tun", port: 4500, url: "https://abc.example" };

test("setup.cmd launcher does not ask PowerShell to bypass the execution policy", () => {
  const cmd = setupCmd(t);
  const lines = cmd.split("\r\n");
  const launcher = lines.find((l) => l.startsWith("powershell"));
  assert.ok(launcher, "launcher line present");
  assert.ok(!/executionpolicy/i.test(cmd.split("::PS")[0].replace(/^\s*\/\/.*$/gm, "")),
    "no -ExecutionPolicy flag anywhere in the batch part");
  assert.ok(!/\bbypass\b/i.test(launcher));
});

test("setup.cmd launcher still runs the embedded script from its own file via an env var", () => {
  const cmd = setupCmd(t);
  const launcher = cmd.split("\r\n").find((l) => l.startsWith("powershell"));
  assert.ok(launcher.includes("-NoProfile -Command"));
  assert.ok(launcher.includes("$env:NG_SELF") && launcher.includes("::PS"));
  assert.ok(cmd.includes('set "NG_SELF=%~f0"') && cmd.split("\r\n").includes("::PS"));
});

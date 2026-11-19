// Runs the real generated setup.sh against stand-ins for the network and the
// supervisor, so the Linux / sandbox behaviour is checked end to end:
// logging, retries, autostart fallback, idempotent reruns, the health check
// on the discovered port, the tunnel fallback, and reporting to the Join page.
import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { delimiter } from "node:path";
import { join } from "node:path";
import worker, { setupSh, SUPERVISOR, SETUP_STATES } from "../../workers/join/worker.js";

const hasSh = spawnSync("sh", ["-c", "exit 0"]).status === 0;
const CODE = "C".repeat(24);
const SRC_SHA = "0123456789abcdef0123456789abcdef01234567";
const posix = (p) => p.replace(/\\/g, "/").replace(/^([A-Za-z]):/, (_, d) => "/" + d.toLowerCase());

const STUBS = {
  uname: `case "$1" in -s) echo Linux;; -m) echo x86_64;; *) echo Linux;; esac`,
  sha256sum: `echo "$EXPECT_SHA  $1"`,
  sleep: `exit 0`,
  // Stand-ins so a test run never opens the operator's real browser; calls are logged for the assertion below.
  open: `echo "$*" >> "$T/browser.log"`,
  "xdg-open": `echo "$*" >> "$T/browser.log"`,
  nohup: `exec "$@"`,
  pkill: `echo "pkill $*" >> "$T/killed"; exit 0`,
  // RELAY_RUNNING=1 stands for a helper that started the relay client.
  // Only this account's own relay client counts: the pattern must carry its node.json path.
  // SUP_LINGERS=n makes the old helper look alive for the first n checks after a stop.
  pgrep: `echo "pgrep $*" >> "$T/pgrep.log"
case "$*" in
  *"relay_client run --node-json "*"/.nougen-node/$ACCT_ID/node.json") [ "$RELAY_RUNNING" = 1 ] && exit 0 ;;
  *nougen-supervisor*) n=$(cat "$T/linger" 2>/dev/null || echo "\${SUP_LINGERS:-0}"); [ "$n" -gt 0 ] && { echo $((n-1)) > "$T/linger"; exit 0; } ;;
esac
exit 1`,
  // uv stands in for Python too: the relay probe exits with RELAY_PROBE (default: the relay refuses).
  uvStub: `echo "uv $*" >> "$T/uv.log"; case "$*" in *relay_client*probe*) exit \${RELAY_PROBE:-2};; esac; exit 0`,
  systemctl: `exit 1`,
  curl: `
url=""; out=""; data=""
while [ $# -gt 0 ]; do
  case "$1" in -o) out=$2; shift;; --data) data=$2; shift;; --noproxy) echo "$2" >> "$T/noproxy.log"; shift;; http*) url=$1;; esac; shift
done
echo "$url $data" >> "$T/curl.log"
[ -n "$out" ] && echo "$url -o" >> "$T/downloads.log"
case "$url" in
  *"$DL_FAIL"*) [ -n "$DL_FAIL" ] && { echo "curl: (56) proxy said no" >&2; exit 56; } ;;
esac
case "$url" in
  */health) [ -f "$T/healthy" ] && exit 0; exit 7 ;;
  */ready) case "$READY" in always) exit 0;; fallback) [ -f "$ACCT/tunnel.env" ] && exit 0;; esac; exit 7 ;;
  *47411/status) exit 7 ;;
  *api.github.com*) echo "$SRC_SHA" ;;
esac
[ -n "$out" ] && echo "downloaded $url" > "$out"
exit 0`,
  // The pinned supervisor: install exits with INSTALL_EXIT, like 1.3.1 on a box with no cron.
  supervisor: `echo "$*" >> "$T/supervisor.log"; [ "$1" = install ] && { echo "autostart: crontab exec error" >&2; exit \${INSTALL_EXIT:-0}; }; exit 0`,
};

function box({ port = 4999, id = "sample-acct", relay_url = "" } = {}) {
  const T = mkdtempSync(join(tmpdir(), "nglinux-"));
  const bin = join(T, "bin"), home = join(T, "home"), B = join(home, ".nougen-node"), acct = join(B, id);
  mkdirSync(bin, { recursive: true });
  mkdirSync(join(acct, "NouGenShards"), { recursive: true });
  for (const [name, body] of Object.entries(STUBS)) {
    if (name === "supervisor" || name === "uvStub") continue;
    writeFileSync(join(bin, name), "#!/bin/sh\n" + body + "\n", { mode: 0o755 });
  }
  // Already installed: supervisor (fingerprint matches via the sha256sum stand-in), uv, cloudflared, current source.
  writeFileSync(join(B, "nougen-supervisor"), "#!/bin/sh\n" + STUBS.supervisor + "\n", { mode: 0o755 });
  writeFileSync(join(B, "uv"), "#!/bin/sh\n" + STUBS.uvStub + "\n", { mode: 0o755 });
  writeFileSync(join(acct, "cloudflared"), "#!/bin/sh\nexit 0\n", { mode: 0o755 });
  writeFileSync(join(acct, "NouGenShards", "app.py"), "keep\n");
  writeFileSync(join(acct, ".src-sha"), SRC_SHA + "\n");
  const script = join(T, "setup-nougen.sh");
  writeFileSync(script, setupSh({ id, port, token: "tok", tunnel: "tun", url: `https://${id}.example.test`, code: CODE, origin: "https://join.example.test", relay_url }));
  // PATH without any real uv, so the download path is what gets tested.
  const sysPath = process.env.PATH.split(delimiter).filter((d) => !["uv", "uv.exe"].some((u) => existsSync(join(d, u)))).join(delimiter);
  const run = (env = {}) => spawnSync("sh", [script], {
    encoding: "utf8",
    env: {
      ...process.env, HOME: home, T: posix(T), ACCT: posix(acct), ACCT_ID: id, EXPECT_SHA: SUPERVISOR.sha256["linux-amd64"], SRC_SHA,
      PATH: bin + delimiter + sysPath,
      NOUGEN_MODE: "foreground", NOUGEN_TUNNEL_WAIT: "3", NOUGEN_HEALTH_TRIES: "3", HTTPS_PROXY: "", https_proxy: "", ...env,
    },
  });
  const read = (f) => (existsSync(join(T, f)) ? readFileSync(join(T, f), "utf8") : "");
  return { T, B, acct, run, read, healthy: () => writeFileSync(join(T, "healthy"), "") };
}

const reports = (b) => [...b.read("curl.log").matchAll(/\/report \{"state":"([a-z_]+)"\}/g)].map((m) => m[1]);

test("linux: the script never installs system packages", () => {
  const sh = setupSh({ id: "sample-acct", port: 4445, token: "t", tunnel: "u", url: "https://x.example.test" });
  assert.ok(!/apt-get|apt install|\byum\b|\bdnf\b|\bapk add|\bsudo\b/.test(sh));
});

test("sandbox: runs without autostart, checks the discovered port, prints PASS and the foreground command", { skip: !hasSh }, () => {
  const b = box({ port: 4999 }); b.healthy();
  const r = b.run({ READY: "always" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /NOUGEN SETUP: PASS node=127\.0\.0\.1:4999 tunnel=connected mode=foreground/);
  assert.match(r.stdout, /nougen-supervisor run/);
  assert.match(b.read("curl.log"), /127\.0\.0\.1:4999\/health/);
  assert.match(b.read("supervisor.log"), /^run/m);
  assert.ok(!/install/.test(b.read("supervisor.log")), "sandbox mode must not try to install autostart");
  assert.deepEqual(reports(b), ["started", "node_ok", "ok"]);
  assert.ok(existsSync(join(b.B, "setup.log")));
});

test("autostart unavailable (crontab exec error) is a WARN, not exit 1", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  const r = b.run({ NOUGEN_MODE: "service", INSTALL_EXIT: "1", READY: "always" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /WARN: this computer has no way to start NouGen by itself/);
  assert.match(r.stdout, /NOUGEN SETUP: PASS .* mode=foreground/);
  assert.match(b.read("supervisor.log"), /^install[\s\S]*^run/m);
});

test("a rerun skips every finished step and downloads nothing", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  assert.equal(b.run({ READY: "always" }).status, 0);
  rmSync(join(b.T, "downloads.log"), { force: true });
  const r = b.run({ READY: "always" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.equal(b.read("downloads.log"), "", "a rerun downloaded something again");
  assert.ok(!existsSync(join(b.T, "killed")) || !/NouGenShards/.test(b.read("killed")), "a rerun stopped a current node");
});

test("a PASS opens the node page through the open stand-in; NOUGEN_NO_BROWSER=1 skips it", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  assert.equal(b.run({ READY: "always" }).status, 0);
  assert.match(b.read("browser.log"), /https:\/\/sample-acct\.example\.test/, "the page was not opened through the stand-in");
  rmSync(join(b.T, "browser.log"), { force: true });
  const r = b.run({ READY: "always", NOUGEN_NO_BROWSER: "1" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.equal(b.read("browser.log"), "", "NOUGEN_NO_BROWSER=1 still opened a browser");
});

test("tunnel fallback: retries over http2 (no unsupported edge override), then it connects", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  const r = b.run({ READY: "fallback" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.equal(readFileSync(join(b.acct, "tunnel.env"), "utf8"), "TUNNEL_TRANSPORT_PROTOCOL=http2\n");
  assert.ok(!/TUNNEL_EDGE/.test(setupSh({ id: "sample-acct", port: 4445, token: "t", tunnel: "u", url: "https://x.example.test" }).replace(/^ *#.*$/gm, "")), "TUNNEL_EDGE only works inside Cloudflare");
  assert.match(r.stdout, /NOUGEN SETUP: PASS/);
});

test("local checks bypass any proxy, so a proxy-only box still sees its own node", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  const r = b.run({ READY: "always", http_proxy: "http://proxy.invalid:3128", ALL_PROXY: "http://proxy.invalid:3128" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  const local = b.read("curl.log").split("\n").filter((l) => l.startsWith("http://127.0.0.1")).length;
  assert.ok(local > 0 && b.read("noproxy.log").split("\n").filter(Boolean).length >= local, "a loopback check went without --noproxy");
});

test("no egress for the tunnel: stops cleanly with the plain reason and tells the Join page", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  const r = b.run({ READY: "never" });
  assert.equal(r.status, 3, r.stdout + r.stderr);
  assert.match(r.stdout, /this box can't host a public node: no direct egress for the tunnel/);
  assert.match(r.stdout, /NOUGEN SETUP: FAIL \(no_tunnel_egress\)/);
  assert.deepEqual(reports(b), ["started", "node_ok", "no_tunnel_egress"]);
});

test("node never healthy: FAIL with the last 30 log lines and the log path", { skip: !hasSh }, () => {
  const b = box();
  const r = b.run({ READY: "always" });
  assert.equal(r.status, 1);
  assert.match(r.stdout, /---- last 30 lines of .*setup\.log ----/);
  assert.match(r.stdout, /Full log: .*setup\.log/);
  assert.match(r.stdout, /NOUGEN SETUP: FAIL \(node_failed\)/);
  assert.equal(reports(b).at(-1), "node_failed");
});

test("uv download fails through the proxy: retries with backoff, then fails with the log", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  rmSync(join(b.B, "uv"));
  // pip is the next fallback; here it fails too, the way it does without network.
  for (const py of ["python3", "python"]) writeFileSync(join(b.T, "bin", py), "#!/bin/sh\necho 'pip: could not reach the index' >&2\nexit 1\n", { mode: 0o755 });
  const r = b.run({ DL_FAIL: "astral.sh", NOUGEN_DL_TRIES: "3" });
  assert.equal(r.status, 1, r.stdout + r.stderr);
  assert.equal((b.read("curl.log").match(/astral\.sh\/uv\/install\.sh/g) || []).length, 3, "expected 3 tries");
  assert.match(r.stdout, /proxy said no/, "the real curl error must be in the printed log tail");
  assert.match(r.stdout, /NOUGEN SETUP: FAIL \(uv_failed\)/);
  assert.equal(reports(b).at(-1), "uv_failed");
});

test("an existing uv on PATH is reused instead of downloaded", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  rmSync(join(b.B, "uv"));
  writeFileSync(join(b.T, "bin", "uv"), "#!/bin/sh\nexit 0\n", { mode: 0o755 });
  const r = b.run({ READY: "always" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /Using the uv already on this computer/);
  assert.ok(!/astral\.sh/.test(b.read("curl.log")));
});

test("auto mode treats this container as a sandbox", { skip: !hasSh || process.env.NOUGEN_EXPECT_SANDBOX !== "1" }, () => {
  const b = box(); b.healthy();
  const r = b.run({ NOUGEN_MODE: "", READY: "always" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /mode=foreground/);
});

// ---- Join page side
function kv() {
  const m = new Map();
  return { m, get: async (k, type) => (m.has(k) ? (type === "json" ? JSON.parse(m.get(k)) : m.get(k)) : null), put: async (k, v) => { m.set(k, v); } };
}
const req = (path, init) => worker.fetch(new Request("https://join.example.test" + path, init), { TENANTS: env.TENANTS });
const env = { TENANTS: kv() };
env.TENANTS.m.set("enroll:" + CODE, "someone@example.test");

test("join: setup reports a state and the page reads our words for it", async () => {
  let r = await req(`/j/${CODE}/state`);
  assert.deepEqual(await r.json(), { state: "waiting", message: "" });
  r = await req(`/j/${CODE}/report`, { method: "POST", body: JSON.stringify({ state: "no_tunnel_egress" }) });
  assert.equal(r.status, 200);
  const j = await (await req(`/j/${CODE}/state`)).json();
  assert.equal(j.state, "no_tunnel_egress");
  assert.equal(j.message, SETUP_STATES.no_tunnel_egress);
});

test("join: unknown states, unknown links and wrong methods are refused", async () => {
  assert.equal((await req(`/j/${CODE}/report`, { method: "POST", body: '{"state":"<script>"}' })).status, 400);
  assert.equal((await req(`/j/${CODE}/report`, { method: "POST", body: "not json" })).status, 400);
  assert.equal((await req(`/j/${"D".repeat(24)}/report`, { method: "POST", body: '{"state":"ok"}' })).status, 404);
  assert.equal((await req(`/j/${CODE}/report`)).status, 405);
});

test("join: the generated script reports to the page that served it, and only a valid code and origin", () => {
  const base = { id: "sample-acct", port: 4445, token: "t", tunnel: "u", url: "https://x.example.test" };
  const sh = setupSh({ ...base, code: CODE, origin: "https://join.example.test" });
  assert.ok(sh.includes(`JOIN='https://join.example.test'; CODE='${CODE}'`));
  const bad = setupSh({ ...base, code: "x'; rm -rf ~; '", origin: "https://join.example.test" });
  assert.ok(bad.includes("JOIN=''; CODE=''"));
  assert.ok(setupSh({ ...base, code: CODE, origin: "http://evil.example" }).includes("JOIN=''; CODE=''"));
});

// The relay address is given through the environment: setup rewrites node.json from its own template.
const RELAY = { NOUGEN_RELAY_URL: "https://relay.example.test" };

test("relay: when both tunnel protocols fail and the relay answers, setup switches to it and passes", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  const r = b.run({ READY: "never", RELAY_PROBE: "0", RELAY_RUNNING: "1", ...RELAY });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /Switching to the NouGen relay \(port 443\)/);
  assert.match(r.stdout, /NOUGEN SETUP: PASS .* tunnel=relay /);
  assert.equal(readFileSync(join(b.acct, "transport"), "utf8"), "relay\n");
  assert.match(b.read("uv.log"), /-m nougen_shards\.relay_client probe --node-json /);
  assert.deepEqual(reports(b), ["started", "node_ok", "ok"]);
  // http2 was still tried first: the relay is the third step, not a shortcut.
  assert.equal(readFileSync(join(b.acct, "tunnel.env"), "utf8"), "TUNNEL_TRANSPORT_PROTOCOL=http2\n");
});

test("relay: no relay address for the account means it is not tried and the plain failure stands", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  const r = b.run({ READY: "never", RELAY_PROBE: "0", RELAY_RUNNING: "1" });
  assert.equal(r.status, 3, r.stdout + r.stderr);
  assert.match(r.stdout, /NOUGEN SETUP: FAIL \(no_tunnel_egress\)/);
  assert.ok(!existsSync(join(b.acct, "transport")));
  assert.ok(!/relay_client/.test(b.read("uv.log")), "the relay was probed without an address");
});

test("relay: the relay refusing the token is a failure, with no transport file left behind", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  const r = b.run({ READY: "never", RELAY_PROBE: "2", RELAY_RUNNING: "1", ...RELAY });
  assert.equal(r.status, 3, r.stdout + r.stderr);
  assert.ok(!existsSync(join(b.acct, "transport")));
  assert.deepEqual(reports(b), ["started", "node_ok", "no_tunnel_egress"]);
});

test("relay: a helper too old to run the relay client is a failure, never a PASS", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  const r = b.run({ READY: "never", RELAY_PROBE: "0", RELAY_RUNNING: "0", ...RELAY });
  assert.equal(r.status, 3, r.stdout + r.stderr);
  assert.ok(!/NOUGEN SETUP: PASS/.test(r.stdout));
  assert.ok(!existsSync(join(b.acct, "transport")), "a stale transport file would keep a newer helper off the tunnel");
});

test("relay: a working tunnel never touches the relay", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  const r = b.run({ READY: "always", RELAY_PROBE: "0", RELAY_RUNNING: "1", ...RELAY });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /tunnel=connected /);
  assert.ok(!existsSync(join(b.acct, "transport")));
  assert.ok(!/relay_client/.test(b.read("uv.log")));
});

test("relay: an address that came from the environment is saved for the helper, so it survives a restart", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  const r = b.run({ READY: "never", RELAY_PROBE: "0", RELAY_RUNNING: "1", ...RELAY });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.equal(readFileSync(join(b.acct, "relay_url"), "utf8"), "https://relay.example.test\n");
});

test("relay: the started check names this account's node.json, not any relay client", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  b.run({ READY: "never", RELAY_PROBE: "0", RELAY_RUNNING: "1", ...RELAY });
  const calls = b.read("pgrep.log").split("\n").filter((l) => l.includes("relay_client"));
  assert.ok(calls.length > 0, "the started check never ran");
  for (const c of calls) assert.match(c, /relay_client run --node-json .*sample-acct\/node\.json/);
});

test("relay: a failed switch removes the saved address along with the transport file", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  const r = b.run({ READY: "never", RELAY_PROBE: "0", RELAY_RUNNING: "0", ...RELAY });
  assert.equal(r.status, 3, r.stdout + r.stderr);
  assert.ok(!existsSync(join(b.acct, "relay_url")) && !existsSync(join(b.acct, "transport")));
});

test("relay: an address provisioned into node.json is used with nothing in the environment", { skip: !hasSh }, () => {
  const b = box({ relay_url: "wss://relay.example.test/_relay/connect" }); b.healthy();
  const r = b.run({ READY: "never", RELAY_PROBE: "0", RELAY_RUNNING: "1" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /NOUGEN SETUP: PASS .* tunnel=relay /);
  assert.equal(JSON.parse(readFileSync(join(b.acct, "node.json"), "utf8")).relay_url, "wss://relay.example.test/_relay/connect");
  // The address is already in node.json, so no separate copy is saved for the helper.
  assert.ok(!existsSync(join(b.acct, "relay_url")));
});

for (const bad of ["ws://relay.example.test/_relay/connect", "http://relay.example.test/_relay/connect"]) {
  test(`relay: ${bad.split(":")[0]}:// from the environment is refused before any probe, even if a probe would pass`, { skip: !hasSh }, () => {
    const b = box(); b.healthy();
    const r = b.run({ READY: "never", RELAY_PROBE: "0", RELAY_RUNNING: "1", NOUGEN_RELAY_URL: bad });
    assert.equal(r.status, 3, r.stdout + r.stderr);
    assert.ok(!/relay_client/.test(b.read("uv.log")), "an insecure address reached the probe");
    assert.ok(!existsSync(join(b.acct, "relay_url")) && !existsSync(join(b.acct, "transport")));
    assert.match(readFileSync(join(b.B, "setup.log"), "utf8"), /not wss:\/\/ or https:\/\/, not used/);
  });

  test(`relay: ${bad.split(":")[0]}:// handed to the script builder never reaches node.json`, { skip: !hasSh }, () => {
    const b = box({ relay_url: bad }); b.healthy();
    const r = b.run({ READY: "never", RELAY_PROBE: "0", RELAY_RUNNING: "1" });
    assert.equal(r.status, 3, r.stdout + r.stderr);
    assert.ok(!("relay_url" in JSON.parse(readFileSync(join(b.acct, "node.json"), "utf8"))));
    assert.ok(!/relay_client/.test(b.read("uv.log")));
  });
}

test("restart: setup waits for the old helper to exit before starting it again, at both restarts", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  const r = b.run({ READY: "never", RELAY_PROBE: "0", RELAY_RUNNING: "1", SUP_LINGERS: "2", ...RELAY });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  const checks = b.read("pgrep.log").split("\n").filter((l) => l.includes("nougen-supervisor")).length;
  // Two restarts (http2, then relay). The first sees the helper linger twice and checks a third time.
  assert.ok(checks >= 4, `only ${checks} exit checks for two restarts`);
  assert.ok(b.read("killed").split("\n").filter((l) => l.includes("nougen-supervisor")).length >= 2);
});

test("control: the started check ignores a relay client that belongs to another account", { skip: !hasSh }, () => {
  // The stand-in for pgrep answers only for this account's node.json path, so a
  // check that asked for any relay client would find nothing and fail here.
  const b = box({ id: "other-acct" }); b.healthy();
  const r = b.run({ READY: "never", RELAY_PROBE: "0", RELAY_RUNNING: "1", ACCT_ID: "sample-acct", ...RELAY });
  assert.equal(r.status, 3, r.stdout + r.stderr);
  assert.ok(!/NOUGEN SETUP: PASS/.test(r.stdout));
});

test("restart: this account's running relay client is stopped along with the helper", { skip: !hasSh }, () => {
  const b = box(); b.healthy();
  const r = b.run({ READY: "never", RELAY_PROBE: "0", RELAY_RUNNING: "1", ...RELAY });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  const stops = b.read("killed").split("\n").filter((l) => l.includes("relay_client run --node-json"));
  assert.ok(stops.length >= 2, "a restart left the relay client running");
  for (const s of stops) assert.match(s, /\/\.nougen-node\/sample-acct\/node\.json$/, "the stop must name this account only");
});

test("rerun: an account already on the relay passes at once, without waiting for a tunnel or retrying http2", { skip: !hasSh }, () => {
  const b = box({ relay_url: "wss://relay.example.test/_relay/connect" }); b.healthy();
  writeFileSync(join(b.acct, "transport"), "relay\n");
  const r = b.run({ READY: "never", RELAY_PROBE: "0", RELAY_RUNNING: "1" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /NOUGEN SETUP: PASS .* tunnel=relay /);
  assert.ok(!existsSync(join(b.acct, "tunnel.env")), "the http2 fallback ran for an account that has no tunnel");
  assert.ok(!b.read("curl.log").split("\n").some((l) => l.includes("/ready")), "setup waited on the tunnel's readiness port");
});

test("rerun control: a relay account whose client is not running still goes through the full check", { skip: !hasSh }, () => {
  const b = box({ relay_url: "wss://relay.example.test/_relay/connect" }); b.healthy();
  writeFileSync(join(b.acct, "transport"), "relay\n");
  const r = b.run({ READY: "never", RELAY_PROBE: "2", RELAY_RUNNING: "0" });
  assert.equal(r.status, 3, r.stdout + r.stderr);
  assert.ok(!/NOUGEN SETUP: PASS/.test(r.stdout));
  assert.ok(!existsSync(join(b.acct, "transport")), "a dead relay must not leave the account marked as relay");
});

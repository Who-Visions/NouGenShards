// nougen-join: universal, self-serve NouGen node onboarding at join.<zone>.
//
//   GET  /                 landing: "Continue with Google"
//   GET  /google/start     -> Google consent (openid email), state cookie
//   GET  /google/callback  verified email -> provision (idempotent) -> /j/<code>
//   GET  /j/<code>         one-button page (OS detected)
//   GET  /j/<code>/setup   Windows "Set up NouGen.cmd"
//   GET  /j/<code>/setup.sh  macOS / Linux one-file setup
//   GET  /privacy, /terms, /health
//
// Provisioning mirrors nougen_shards.tenant_onboard: a collision-resistant tunnel
// identity derived from the full normalized email, a proxied CNAME <id>-<hex>.<zone>,
// ingress -> 127.0.0.1:<port>, and KV records allow:/tenant:/tunnel:<email>.
//
// Abuse limits: verified Google email required; at most JOIN_MAX_PER_IP_DAY new
// tenants per client IP per day; links expire (LINK_TTL_DAYS).
//
// Bindings: TENANTS (KV). Secrets: CF_API_TOKEN, GOOGLE_CLIENT_SECRET.
// Vars: CF_ACCOUNT_ID, CF_ZONE_ID, ZONE_NAME, GOOGLE_CLIENT_ID, NODE_PORT,
//       JOIN_MAX_PER_IP_DAY, LINK_TTL_DAYS.

const CF = "https://api.cloudflare.com/client/v4";
const enc = new TextEncoder();

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
// The supervisor keeps every account on a computer online (tools/nougen-supervisor).
// Each file is pinned by SHA-256: setup refuses a download that does not match.
export const SUPERVISOR = {
  version: "1.3.0",
  base: "https://github.com/Who-Visions/NouGenShards/releases/download/supervisor-v1.3.0/",
  sha256: {
    "windows-amd64.exe": "c8aa69a914ad59b018e219f71b56cb4fc568a781a1c329c7302bf2ead340b5e1",
    "darwin-arm64": "50dacae5da2b08ed5032c5f6ae71be5ad83b786e4cb77fb0109f71b6c0bbced2",
    "darwin-amd64": "5b0283e8f79cc7779f143b3d0703721c720db1fd0aff748b8338375ad284f44f",
    "linux-amd64": "68448fa713e5bf18f04c4685d33b0963e28d221ea8e45033b25af34957fd999a",
    "linux-arm64": "7af22c9547d5e95f91f012c12f883002e205a42d1a5dede3faddcc8adb135496",
  },
};
// What the supervisor reads for one account. One line of JSON, so it can sit
// inside a literal here-string or heredoc without any escaping rules applying.
export const nodeJson = (t) => JSON.stringify({ id: String(t.id), port: Number(t.port), token: String(t.token), tunnel: String(t.tunnel || ""), url: String(t.url || "") });
const psq = (s) => String(s).replace(/'/g, "''");
const shq = (s) => String(s).replace(/'/g, "'\\''");
const rand = (n) => { const b = crypto.getRandomValues(new Uint8Array(n)); return btoa(String.fromCharCode(...b)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); };
const hex = (n) => [...crypto.getRandomValues(new Uint8Array(n))].map((b) => b.toString(16).padStart(2, "0")).join("");
const slug = (s) => (String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 20) || "node");

async function sha256Hex(s) {
  const buf = await crypto.subtle.digest("SHA-256", enc.encode(String(s)));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function emailTenantId(email) {
  const norm = String(email || "").trim().toLowerCase();
  const [local] = norm.split("@");
  const digest = (await sha256Hex(norm)).slice(0, 10);
  return `${slug(local).slice(0, 21)}-${digest}`;
}

export function tunnelIdFromToken(tok) {
  try {
    const b64 = String(tok || "").replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(b64)).t || null;
  } catch {
    return null;
  }
}

// ------------------------------------------------------------------ pages
// BEGIN GENERATED NOUGEN-CORE CSS
const JOIN_CSS = ":root {\n  --accent: #e8b86d;\n  --accent-2: #e8b86d;\n  --accent-green: #a9c79b;\n  --accent-purple: #c8bfad;\n  --accent-rgb: 232, 184, 109;\n  --bg: #141414;\n  --bg-gradient: var(--bg);\n  --cluster-gap: 1.25rem;\n  --control-ink: #141414;\n  --danger: #ffb4ab;\n  --fleet-card-min: 23rem;\n  --focus: #e8b86d;\n  --font-main: system-ui, sans-serif;\n  --font-mono: Consolas, monospace;\n  --line: #777777;\n  --line-body: 1.65;\n  --line-glow: #777777;\n  --motion-ease: ease-out;\n  --motion-fast: 120ms;\n  --muted: #bdb8ad;\n  --panel: #202020;\n  --panel-2: #282828;\n  --panel-hover: #333333;\n  --panel-solid: #202020;\n  --radius-lg: 4px;\n  --radius-md: 3px;\n  --radius-sm: 2px;\n  --reading-measure: 65ch;\n  --space-1: 0.25rem;\n  --space-2: 0.5rem;\n  --space-3: 0.75rem;\n  --space-4: 1rem;\n  --space-5: 1.5rem;\n  --space-6: 2rem;\n  --status-conflict-bg: rgba(255, 180, 171, 0.12);\n  --status-conflict-border: #ffb4ab;\n  --status-conflict-text: #ffb4ab;\n  --status-offline-bg: rgba(189, 184, 173, 0.10);\n  --status-offline-border: #777777;\n  --status-offline-text: #bdb8ad;\n  --status-pending-bg: rgba(232, 184, 109, 0.12);\n  --status-pending-border: #e8b86d;\n  --status-pending-text: #e8b86d;\n  --status-sim-bg: rgba(189, 184, 173, 0.10);\n  --status-sim-border: #777777;\n  --status-sim-text: #bdb8ad;\n  --status-verified-bg: rgba(169, 199, 155, 0.12);\n  --status-verified-border: #a9c79b;\n  --status-verified-text: #a9c79b;\n  --target-min: 1.5rem;\n  --target-touch: 2.75rem;\n  --text: #f2eee6;\n  --type-body: 1rem;\n  --type-meta: 0.8125rem;\n  --warn: #e8b86d;\n  --workbench-width: 87.5rem;\n}\n:root[data-theme=\"dark\"] {\n\n}\n:root[data-theme=\"light\"] {\n  --accent: #765013;\n  --accent-2: #765013;\n  --bg: #f5f1e8;\n  --control-ink: #ffffff;\n  --danger: #a62520;\n  --focus: #765013;\n  --line: #76716a;\n  --muted: #555047;\n  --panel: #ffffff;\n  --panel-2: #eee9df;\n  --panel-hover: #e1dbce;\n  --panel-solid: #ffffff;\n  --status-conflict-bg: rgba(166, 37, 32, 0.10);\n  --status-conflict-border: #a62520;\n  --status-conflict-text: #a62520;\n  --status-offline-bg: rgba(85, 80, 71, 0.08);\n  --status-offline-border: #76716a;\n  --status-offline-text: #555047;\n  --status-pending-bg: rgba(118, 80, 19, 0.10);\n  --status-pending-border: #765013;\n  --status-pending-text: #765013;\n  --status-sim-bg: rgba(85, 80, 71, 0.08);\n  --status-sim-border: #76716a;\n  --status-sim-text: #555047;\n  --status-verified-bg: rgba(20, 90, 50, 0.10);\n  --status-verified-border: #145a32;\n  --status-verified-text: #145a32;\n  --text: #202020;\n}\n\n:where(a, button, input, select, textarea, [tabindex]):focus-visible {\n  outline: 2px solid var(--focus);\n  outline-offset: 3px;\n}\n@media (prefers-reduced-motion: reduce) {\n  *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }\n}\n\n:root:not([data-theme=\"light\"]) {\n  --bg: #0A0A0A;\n  --bg-gradient: var(--bg);\n  --panel: #121212;\n  --panel-2: #1a1a1a;\n  --panel-hover: #1f1f1f;\n  --panel-solid: #121212;\n  --line: #262626;\n  --line-glow: #262626;\n  --join-cta-bg: #EDEDED;\n  --join-cta-ink: #0A0A0A;\n  --join-cta-hover: #d4d4d4;\n}\n\n* {\n  box-sizing: border-box;\n}\n\nbody {\n  min-height: 100vh;\n  margin: 0;\n  display: flex;\n  flex-direction: column;\n  justify-content: space-between;\n  gap: var(--space-5);\n  padding: var(--space-5) var(--space-4);\n  font-family: var(--font-main);\n  font-size: var(--type-body);\n  line-height: var(--line-body);\n  color: var(--text);\n  background: var(--bg);\n}\n\n.join-bar {\n  width: 100%;\n  max-width: 30rem;\n  margin: 0 auto;\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  gap: var(--space-3);\n  font-size: var(--type-meta);\n  color: var(--muted);\n}\n\n.join-wordmark {\n  color: var(--text);\n  font-weight: 600;\n  letter-spacing: -0.02em;\n  text-decoration: none;\n}\n\n.join-pill {\n  display: inline-flex;\n  align-items: center;\n  padding: var(--space-1) var(--space-3);\n  border: 1px solid var(--line);\n  border-radius: var(--radius-sm);\n  background: var(--panel);\n  font-family: var(--font-mono);\n  font-size: var(--type-meta);\n  color: var(--muted);\n}\n\n.join-card {\n  width: 100%;\n  max-width: 30rem;\n  margin: auto;\n  padding: var(--space-6) var(--space-5);\n  background: var(--panel);\n  border: 1px solid var(--line);\n  border-radius: var(--radius-lg);\n}\n\n.join-eyebrow {\n  margin: 0 0 var(--space-2);\n  font-family: var(--font-mono);\n  font-size: var(--type-meta);\n  text-transform: uppercase;\n  letter-spacing: 0.08em;\n  color: var(--muted);\n}\n\nh1 {\n  font-size: 1.75rem;\n  font-weight: 600;\n  letter-spacing: -0.02em;\n  line-height: 1.15;\n  margin: 0 0 var(--space-3);\n}\n\n.join-lead {\n  margin: 0 0 var(--space-5);\n  color: var(--muted);\n}\n\n.join-action {\n  width: 100%;\n  display: inline-flex;\n  align-items: center;\n  justify-content: center;\n  gap: var(--space-3);\n  min-height: var(--target-touch);\n  padding: var(--space-3) var(--space-5);\n  background: var(--join-cta-bg, var(--text));\n  color: var(--join-cta-ink, var(--bg));\n  border: 1px solid var(--join-cta-bg, var(--text));\n  border-radius: var(--radius-md);\n  text-decoration: none;\n  font-weight: 600;\n  font-size: 1rem;\n  transition: background-color var(--motion-fast) var(--motion-ease);\n}\n\n.join-action:hover {\n  background: var(--join-cta-hover, var(--muted));\n}\n\n.join-host {\n  display: inline-block;\n  margin: 0 0 var(--space-4);\n  padding: var(--space-1) var(--space-3);\n  border: 1px solid var(--line);\n  border-radius: var(--radius-sm);\n  background: var(--panel-2);\n  font-family: var(--font-mono);\n  font-size: var(--type-meta);\n  overflow-wrap: anywhere;\n}\n\n.join-steps {\n  margin: var(--space-5) 0 0;\n  padding: var(--space-4) 0 0;\n  border-top: 1px solid var(--line);\n  list-style: none;\n  display: grid;\n  grid-template-columns: repeat(3, 1fr);\n  gap: var(--space-3);\n}\n\n.join-step {\n  display: flex;\n  flex-direction: column;\n  align-items: flex-start;\n  gap: var(--space-2);\n  font-size: var(--type-meta);\n  color: var(--muted);\n  padding-top: var(--space-3);\n  border-top: 2px solid var(--line);\n}\n\n.join-step-num {\n  width: 1.375rem;\n  height: 1.375rem;\n  display: inline-flex;\n  align-items: center;\n  justify-content: center;\n  border: 1px solid var(--line);\n  border-radius: var(--radius-sm);\n  font-family: var(--font-mono);\n  color: var(--text);\n}\n\n.join-step strong {\n  display: block;\n  color: var(--text);\n  font-weight: 600;\n}\n\n@media (max-width: 30rem) {\n  .join-steps { grid-template-columns: 1fr; }\n}\n\n.join-meta,\nsmall {\n  color: var(--muted);\n  font-size: var(--type-meta);\n}\n\n.join-meta a {\n  color: var(--muted);\n}\n\n.join-meta a:hover {\n  color: var(--text);\n}\n\n.join-hint {\n  margin: var(--space-3) 0 0;\n  color: var(--muted);\n  font-size: var(--type-meta);\n}\n\ncode {\n  font-family: var(--font-mono);\n  font-size: var(--type-meta);\n  background: var(--panel-2);\n  border: 1px solid var(--line);\n  border-radius: var(--radius-sm);\n  padding: 0.125rem var(--space-1);\n  overflow-wrap: anywhere;\n}";
// END GENERATED NOUGEN-CORE CSS

export const shell = (title, body) => new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(title)}</title>
<style>${JOIN_CSS}</style></head><body>
<header class="join-bar"><a class="join-wordmark" href="https://nougenai.com">NouGenAI</a><span class="join-pill" id="os-pill">Windows · Mac · Linux</span></header>
<main class="join-card">${body}</main>
<footer class="join-bar join-meta"><span>Your memory stays on your computer</span><span><a href="/privacy">Privacy</a> · <a href="/terms">Terms</a></span></footer>
<script>(function(){var u=navigator.userAgent||"",o=/Windows/i.test(u)?"Windows":/Mac/i.test(u)?"macOS":/Linux/i.test(u)?"Linux":"";var e=document.getElementById("os-pill");if(o&&e)e.textContent="Detected: "+o;})();</script>
</body></html>`,
  { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });

// Official multi-color Google "G" (Google sign-in branding guidelines).
const GOOGLE_G = `<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/><path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/><path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"/><path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/></svg>`;

const step = (n, title, text) => `<li class="join-step"><span class="join-step-num">${n}</span><span><strong>${title}</strong>: ${text}</span></li>`;

const LANDING = `<p class="join-eyebrow">Your own private memory</p>
<h1>Join NouGen</h1>
<p class="join-lead">Sign in with Google and your computer becomes your own NouGen node: a private memory your AI assistants can use. No passwords to create, nothing to set up by hand.</p>
<a class="join-action" href="/google/start">${GOOGLE_G}<span>Continue with Google</span></a>
<ol class="join-steps" aria-label="What happens next">
${step(1, "Sign in", "we read only your email address, and create your private address on nougenai.com.")}
${step(2, "Run one file", "you download one setup file and open it. It installs everything and starts your node, then opens your page.")}
${step(3, "Use it", "connect Claude or ChatGPT to https://shards.nougenai.com/mcp and sign in with the same Google account.")}
</ol>`;

const PRIVACY = `<h1>Privacy</h1><p>We use your Google sign-in only to read your email address, which names your node and lets you sign in again. We store your email, your node's address and its connection keys. We do not read your mail, contacts or files, and we do not sell or share your information.</p><p>To remove your node and its records, sign in again and use the delete option, or contact the operator.</p>`;
const TERMS = `<h1>Terms</h1><p>NouGen nodes are provided as-is, without warranty. Do not use your node for anything unlawful or abusive; nodes used that way are removed. Unused nodes that never connect may be removed after the setup link expires.</p>`;

const linkPage = (name, code, host) => shell("NouGen setup", `<p class="join-eyebrow">Step 2 of 3</p>
<h1>Hi ${esc(name)}</h1>
${host ? `<p class="join-host">${esc(host)}</p>` : ""}
<p class="join-lead">Press the button, then open the file it saves. It sets everything up by itself and opens your page when it's done.</p>
<a class="join-action" id="go" href="/j/${code}/setup">Download and run setup</a>
<p class="join-hint" id="hint">If Windows says it protected your PC, click <b>More info</b>, then <b>Run anyway</b>.</p>
<ol class="join-steps" aria-label="What happens next">
${step(1, "Signed in", "your private address is ready.")}
${step(2, "Run the file", "it takes a few minutes the first time and starts by itself after that.")}
${step(3, "Use it", "connect your AI to https://shards.nougenai.com/mcp with this Google account.")}
</ol>
<script>if(!/Windows/i.test(navigator.userAgent)){var g=document.getElementById('go');g.href='/j/${code}/setup.sh';g.download='setup-nougen.sh';
document.getElementById('hint').innerHTML='On Mac or Linux: open Terminal and run <code>sh ~/Downloads/setup-nougen.sh</code>';}</script>`);

// ------------------------------------------------------------------ setup files
export function setupCmd(t) {
  return ["@echo off", `rem NouGen setup for ${t.id}. Private: contains this computer's keys.`,
    // The file path reaches PowerShell through an env var, never as source text: a
    // folder like O'Connor (or a crafted name) must not be able to break out.
    `set "NG_SELF=%~f0"`,
    `powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(Get-Content -Raw -LiteralPath $env:NG_SELF) -split '(?m)^::PS\\s*$',2; iex $s[1]"`,
    "exit /b", "::PS",
    "$ErrorActionPreference = 'Stop'", "$ProgressPreference = 'SilentlyContinue'",
    "[Net.ServicePointManager]::SecurityProtocol = 'Tls12'",
    "$home_ = Join-Path $env:LOCALAPPDATA 'NouGen'",
    `$td = Join-Path $home_ '${psq(t.id)}'`, "New-Item -ItemType Directory -Force $td | Out-Null",
    "Write-Host 'Setting up NouGen on this computer. This takes a few minutes and needs nothing from you.'",
    // The supervisor would restart the node mid-update; stop it first. Other accounts' nodes keep running.
    "Get-Process nougen-supervisor -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue",
    "$escTd = [regex]::Escape($td)",
    "$procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { ($_.ExecutablePath -and $_.ExecutablePath -match $escTd) -or ($_.CommandLine -and $_.CommandLine -match $escTd) })",
    "$targetPids = @($procs | Select-Object -ExpandProperty ProcessId)",
    "if ($targetPids.Count -gt 0) { $kids = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $targetPids -contains $_.ParentProcessId } | Select-Object -ExpandProperty ProcessId); foreach ($procId in ($kids + $targetPids | Select-Object -Unique)) { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue }; Start-Sleep -Milliseconds 500 }",
    "function Get-File($url, $out) { if (-not (Test-Path $out)) { Invoke-WebRequest -UseBasicParsing $url -OutFile $out } }",
    "$uv = Join-Path $home_ 'uv.exe'",
    "if (-not (Test-Path $uv)) { $z = Join-Path $home_ 'uv.zip'; Get-File 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' $z; Expand-Archive -Force $z $home_; Remove-Item $z }",
    "$cf = Join-Path $td 'cloudflared.exe'",
    "Get-File 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' $cf",
    "$src = Join-Path $td 'NouGenShards'; $z = Join-Path $td 'src.zip'",
    "Invoke-WebRequest -UseBasicParsing 'https://github.com/Who-Visions/NouGenShards/archive/refs/heads/main.zip' -OutFile $z",
    "if (Test-Path $src) { Remove-Item -Recurse -Force $src }",
    "Expand-Archive -Force $z $td; Remove-Item $z; Move-Item (Join-Path $td 'NouGenShards-main') $src",
    // The account is described by node.json; the supervisor starts and watches it.
    "$nj = Join-Path $td 'node.json'", "@'", nodeJson(t), "'@ | Set-Content -Encoding UTF8 $nj",
    "Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $td 'run.ps1')",
    "$sup = Join-Path $home_ 'nougen-supervisor.exe'",
    `$want = '${SUPERVISOR.sha256["windows-amd64.exe"]}'`,
    "if (-not ((Test-Path $sup) -and ((Get-FileHash -Algorithm SHA256 $sup).Hash -eq $want))) {",
    "  $dl = \"$sup.download\"",
    `  Invoke-WebRequest -UseBasicParsing '${SUPERVISOR.base}nougen-supervisor-windows-amd64.exe' -OutFile $dl`,
    "  if ((Get-FileHash -Algorithm SHA256 $dl).Hash -ne $want) { Remove-Item -Force $dl; throw 'The NouGen download did not match its fingerprint. Nothing was installed. Try the link again.' }",
    "  Move-Item -Force $dl $sup",
    "}",
    "& $sup install | Out-Null",
    "if ($LASTEXITCODE -ne 0) { throw 'NouGen could not start its background helper.' }",
    "Write-Host 'Starting... (first start downloads Python once)'",
    "$ok = $false",
    `for ($i = 0; $i -lt 90; $i++) { try { Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:${t.port}/health' -TimeoutSec 3 | Out-Null; $ok = $true; break } catch { Start-Sleep 5 } }`,
    `if ($ok) { Start-Process '${psq(t.url)}'; Write-Host 'Done. NouGen is on and will start by itself whenever this computer starts.' }`,
    "else { Write-Host 'NouGen did not start yet. Restart the computer once; it starts by itself. If it still does not, send a photo of this window to the person who sent you the link.' -ForegroundColor Yellow }",
    "Start-Sleep 15", ""].join("\r\n");
}

export function setupSh(t) {
  return `#!/bin/sh
# NouGen setup for ${t.id} (macOS / Linux). Private: contains this computer's keys.
set -e
B="$HOME/.nougen-node"; H="$B/${shq(t.id)}"; mkdir -p "$H"; cd "$H"
echo "Setting up NouGen on this computer. This takes a few minutes and needs nothing from you."
OS=$(uname -s); ARCH=$(uname -m)
pkill -x nougen-supervisor 2>/dev/null || true
pkill -f "$H/NouGenShards" 2>/dev/null || true
pkill -f "$H/cloudflared" 2>/dev/null || true
[ -x "$B/uv" ] || { curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$B" UV_NO_MODIFY_PATH=1 sh >/dev/null; }
if [ ! -x "$H/cloudflared" ]; then
  case "$OS-$ARCH" in
    Darwin-arm64) U=cloudflared-darwin-arm64.tgz;; Darwin-*) U=cloudflared-darwin-amd64.tgz;;
    Linux-aarch64|Linux-arm64) U=cloudflared-linux-arm64;; *) U=cloudflared-linux-amd64;;
  esac
  curl -LsSf "https://github.com/cloudflare/cloudflared/releases/latest/download/$U" -o cf.dl
  case "$U" in *.tgz) tar -xzf cf.dl && rm cf.dl;; *) mv cf.dl cloudflared;; esac; chmod +x cloudflared
fi
rm -rf NouGenShards src.zip; curl -LsSf https://github.com/Who-Visions/NouGenShards/archive/refs/heads/main.zip -o src.zip
"$B/uv" run --python 3.11 python -c "import zipfile;zipfile.ZipFile('src.zip').extractall('.')" && mv NouGenShards-main NouGenShards && rm src.zip
cat > node.json <<'NODE'
${nodeJson(t)}
NODE
chmod 600 node.json; rm -f run.sh
case "$OS-$ARCH" in
  Darwin-arm64) A=darwin-arm64; W='${SUPERVISOR.sha256["darwin-arm64"]}';; Darwin-*) A=darwin-amd64; W='${SUPERVISOR.sha256["darwin-amd64"]}';;
  Linux-aarch64|Linux-arm64) A=linux-arm64; W='${SUPERVISOR.sha256["linux-arm64"]}';; *) A=linux-amd64; W='${SUPERVISOR.sha256["linux-amd64"]}';;
esac
sum() { if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }
S="$B/nougen-supervisor"
if [ ! -x "$S" ] || [ "$(sum "$S")" != "$W" ]; then
  curl -LsSf "${SUPERVISOR.base}nougen-supervisor-$A" -o "$S.download"
  if [ "$(sum "$S.download")" != "$W" ]; then rm -f "$S.download"; echo "The NouGen download did not match its fingerprint. Nothing was installed. Try the link again."; exit 1; fi
  chmod 700 "$S.download"; mv -f "$S.download" "$S"
fi
"$S" install >/dev/null
echo "Starting... (first start downloads Python once)"
ok=0; i=0; while [ $i -lt 90 ]; do curl -fs "http://127.0.0.1:${t.port}/health" >/dev/null 2>&1 && { ok=1; break; }; sleep 5; i=$((i+1)); done
if [ $ok = 1 ]; then
  (command -v open >/dev/null && open '${shq(t.url)}') || (command -v xdg-open >/dev/null && xdg-open '${shq(t.url)}') || true
  echo "Done. NouGen is on and will start by itself whenever this computer starts."
else
  echo "NouGen did not start yet. Restart the computer once; details are in $H/node.log"; exit 1
fi
`;
}

// ------------------------------------------------------------------ Cloudflare
async function cf(env, method, path, body) {
  const r = await fetch(CF + path, { method, headers: { Authorization: "Bearer " + env.CF_API_TOKEN, "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!j.success) throw new Error(`cloudflare ${method} ${path.split("?")[0]}: ${JSON.stringify(j.errors || r.status)}`);
  return j.result;
}

export async function provision(env, email) {
  email = String(email || "").trim().toLowerCase();
  const kv = env.TENANTS;
  const tenant = await kv.get("tenant:" + email, "json");
  const tun = await kv.get("tunnel:" + email, "json");
  if (tenant && tenant.token && tun && tun.tunnel_token) return { tenant, tun, created: false };

  const acct = env.CF_ACCOUNT_ID, zone = env.CF_ZONE_ID;
  const port = (tenant && tenant.port) || await portFor(env, email);
  const id = (tenant && tenant.tenant_id) || await emailTenantId(email);
  const host = (tun && tun.hostname) || `${id}-${hex(2)}.${env.ZONE_NAME}`;
  const name = "tenant-" + id;
  let t = null;
  const knownId = tunnelIdFromToken(tun && tun.tunnel_token);
  if (knownId) {
    try {
      const got = await cf(env, "GET", `/accounts/${acct}/cfd_tunnel/${encodeURIComponent(knownId)}`);
      if (got && !got.deleted_at) t = got;
    } catch {
      t = null;
    }
  }
  // Recover a tunnel created by an earlier attempt that failed before the tenant
  // records were written. Its id goes to the coordinator (strongly consistent,
  // transactional) the moment it exists; never looked up by name.
  const pendingId = !t ? await coord(env, { op: "tunnel-get", email }) : null;
  if (pendingId) {
    try {
      const got = await cf(env, "GET", `/accounts/${acct}/cfd_tunnel/${encodeURIComponent(pendingId)}`);
      if (got && !got.deleted_at) t = got;
    } catch {
      t = null;
    }
  }
  // A creation that succeeded but whose id never reached the coordinator: the
  // coordinator holds a begin-marker (name + time) written BEFORE the POST, so the
  // lookup is by that exact name AND created after that moment, never by name alone.
  if (!t) {
    const begun = await coord(env, { op: "tunnel-begun", email });
    if (begun && begun.name === name) {
      const list = (await cf(env, "GET", `/accounts/${acct}/cfd_tunnel?name=${encodeURIComponent(name)}&is_deleted=false`)) || [];
      t = list.find((x) => x.name === name && Date.parse(x.created_at || 0) >= begun.at - 60000) || null;
      if (t) await coord(env, { op: "tunnel-set", email, id: t.id });
    }
  }
  if (!t) {
    await coord(env, { op: "tunnel-begin", email, name, at: Date.now() });
    t = await cf(env, "POST", `/accounts/${acct}/cfd_tunnel`, { name, config_src: "cloudflare", tunnel_secret: btoa(rand(32)) });
    await coord(env, { op: "tunnel-set", email, id: t.id });
  }
  await cf(env, "PUT", `/accounts/${acct}/cfd_tunnel/${t.id}/configurations`,
    { config: { ingress: [{ hostname: host, service: `http://127.0.0.1:${port}` }, { service: "http_status:404" }] } });
  const tunnelToken = String(await cf(env, "GET", `/accounts/${acct}/cfd_tunnel/${t.id}/token`)).replace(/"/g, "").trim();
  const target = `${t.id}.cfargotunnel.com`;
  const existing = await cf(env, "GET", `/zones/${zone}/dns_records?name=${encodeURIComponent(host)}`);
  const rec = { type: "CNAME", name: host, content: target, proxied: true };
  if (existing[0]) { if (existing[0].content !== target) await cf(env, "PUT", `/zones/${zone}/dns_records/${existing[0].id}`, rec); }
  else await cf(env, "POST", `/zones/${zone}/dns_records`, rec);

  const nt = { ...(tenant || {}), tenant_id: id, token: (tenant && tenant.token) || rand(32), node_url: "https://" + host, port,
    source: (tenant && tenant.source) || "join", joined: (tenant && tenant.joined) || new Date().toISOString() };
  const ntun = { tunnel_token: tunnelToken, hostname: host };
  await kv.put("allow:" + email, "1");
  await kv.put("tenant:" + email, JSON.stringify(nt));
  await kv.put("tunnel:" + email, JSON.stringify(ntun));
  return { tenant: nt, tun: ntun, created: true };
}

// ------------------------------------------------------------------ coordinator
// Everything that must be atomic (signup quota, port reservation, tunnel-id record)
// goes through ONE Durable Object instance: its storage is strongly consistent and
// transactional, and it serializes every operation through its own lock as well, so
// two concurrent sign-ups can never both pass a quota check or claim one port.
// KV stays for the tenant records the connector reads.
export class JoinCoordinator {
  constructor(state) {
    this.storage = state.storage;
    this.chain = Promise.resolve();
  }
  run(fn) {
    const next = this.chain.then(fn, fn);
    this.chain = next.catch(() => {});
    return next;
  }
  async fetch(req) {
    const body = await req.json();
    const out = await this.run(() => this.handle(body));
    return new Response(JSON.stringify(out), { headers: { "content-type": "application/json" } });
  }
  async handle(b) {
    const s = this.storage;
    if (b.op === "rate") {
      const key = `rate:${b.day}:${b.ip}`;
      const n = (await s.get(key)) || 0;
      if (n >= b.limit) return { ok: false, n };
      await s.put(key, n + 1);
      return { ok: true, n: n + 1 };
    }
    if (b.op === "port") {
      const mine = await s.get("portof:" + b.email);
      if (mine) return { port: mine };
      for (let i = 0; i < 64; i++) {
        const p = 4445 + ((b.base + i) % 20000);
        const owner = await s.get("port:" + p);
        if (!owner) {
          await s.put({ ["port:" + p]: b.email, ["portof:" + b.email]: p });
          return { port: p };
        }
      }
      return { error: "no free local port" };
    }
    if (b.op === "reserve-port") { // seed existing tenants' ports (operator migration)
      const owner = await s.get("port:" + b.port);
      if (owner && owner !== b.email) return { error: `port ${b.port} already owned` };
      await s.put({ ["port:" + b.port]: b.email, ["portof:" + b.email]: b.port });
      return { port: b.port };
    }
    if (b.op === "seeded") return { seeded: Boolean(await s.get("seeded")) };
    if (b.op === "mark-seeded") { await s.put("seeded", true); return { seeded: true }; }
    if (b.op === "tunnel-get") return { id: (await s.get("tunnel:" + b.email)) || null };
    if (b.op === "tunnel-set") {
      await s.put("tunnel:" + b.email, b.id);
      await s.delete("tbegin:" + b.email);
      return { id: b.id };
    }
    if (b.op === "tunnel-begin") { await s.put("tbegin:" + b.email, { name: b.name, at: b.at }); return { id: null }; }
    if (b.op === "tunnel-begun") return { begun: (await s.get("tbegin:" + b.email)) || null };
    return { error: "unknown op" };
  }
}

async function coord(env, body) {
  if (!env.COORD) throw new Error("join coordinator not bound");
  const stub = env.COORD.get(env.COORD.idFromName("global"));
  const r = await stub.fetch("https://coord/op", { method: "POST", body: JSON.stringify(body) });
  const j = await r.json();
  if (j.error) throw new Error(j.error);
  if (body.op === "tunnel-begun") return j.begun;
  return body.op.startsWith("tunnel") ? j.id : j;
}

// Every tenant gets its own local port so several accounts can run on one computer.
// The email picks a starting point (spreads tenants out); the coordinator reserves
// atomically and probes on collision.
async function portFor(env, email) {
  const d = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(email)));
  const base = ((d[0] << 16) | (d[1] << 8) | d[2]) % 20000;
  // One-time import of ports reserved before the coordinator existed (KV port:<n>),
  // so a newcomer can never be handed a port an existing tenant already listens on.
  if (!(await coord(env, { op: "seeded" })).seeded && typeof env.TENANTS.list === "function") {
    let cursor;
    do {
      const page = await env.TENANTS.list({ prefix: "port:", cursor });
      for (const k of page.keys) {
        const owner = await env.TENANTS.get(k.name);
        if (owner) await coord(env, { op: "reserve-port", email: owner, port: Number(k.name.slice(5)) });
      }
      cursor = page.list_complete ? null : page.cursor;
    } while (cursor);
    await coord(env, { op: "mark-seeded" });
  }
  return (await coord(env, { op: "port", email, base })).port;
}

async function mintLink(env, email) {
  const code = rand(24);
  await env.TENANTS.put("enroll:" + code, email, { expirationTtl: 86400 * parseInt(env.LINK_TTL_DAYS || "14", 10) });
  return code;
}

async function underIpLimit(env, ip) {
  // Burst gate (Rate Limiting binding) in front of the atomic daily cap (coordinator).
  if (env.JOIN_RL && typeof env.JOIN_RL.limit === "function") {
    const { success } = await env.JOIN_RL.limit({ key: "join:" + ip });
    if (!success) return false;
  }
  const day = new Date().toISOString().slice(0, 10);
  const r = await coord(env, { op: "rate", ip, day, limit: parseInt(env.JOIN_MAX_PER_IP_DAY || "5", 10) });
  return r.ok;
}

// ------------------------------------------------------------------ Google
// OAuth state is SIGNED, not stored: KV is eventually consistent, so a state written
// at /google/start might not be readable yet at /google/callback in another location,
// failing real sign-ins. state = nonce.issuedAt.hmac(secret, nonce.issuedAt); valid
// 10 minutes and only together with the matching __Host- cookie (which no tenant
// subdomain can set), so a forged or replayed state from elsewhere fails.
async function hmacB64(secret, msg) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(msg)));
  return btoa(String.fromCharCode(...sig)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
async function makeState(env) {
  const body = `${rand(16)}.${Date.now()}`;
  return `${body}.${await hmacB64(env.GOOGLE_CLIENT_SECRET || "", "join-state:" + body)}`;
}
async function stateValid(env, state) {
  const parts = String(state || "").split(".");
  if (parts.length !== 3 || !env.GOOGLE_CLIENT_SECRET) return false;
  const [nonce, issued, sig] = parts;
  const age = Date.now() - Number(issued);
  if (!(age >= 0 && age < 600000)) return false;
  const want = await hmacB64(env.GOOGLE_CLIENT_SECRET, `join-state:${nonce}.${issued}`);
  const [a, b] = await Promise.all([crypto.subtle.digest("SHA-256", enc.encode(sig)), crypto.subtle.digest("SHA-256", enc.encode(want))]);
  return crypto.subtle.timingSafeEqual ? crypto.subtle.timingSafeEqual(a, b)
    : new Uint8Array(a).every((x, i) => x === new Uint8Array(b)[i]);
}

async function googleStart(env, url) {
  const state = await makeState(env);
  const q = new URLSearchParams({ client_id: env.GOOGLE_CLIENT_ID, redirect_uri: `${url.origin}/google/callback`,
    response_type: "code", scope: "openid email", state, prompt: "select_account" });
  return new Response(null, { status: 302, headers: { location: "https://accounts.google.com/o/oauth2/v2/auth?" + q,
    "set-cookie": `__Host-nj_state=${state}; Path=/; Max-Age=600; HttpOnly; Secure; SameSite=Lax` } });
}

async function googleEmail(env, url, req) {
  const state = url.searchParams.get("state"), code = url.searchParams.get("code");
  // __Host- cookies cannot be set by any subdomain (tenants control *.nougenai.com hosts),
  // and the state must carry our own signature and be under 10 minutes old.
  const cookie = (req.headers.get("cookie") || "").match(/(?:^|;\s*)__Host-nj_state=([^;]+)/);
  if (!code || !state || !cookie || cookie[1] !== state) throw new Error("sign-in expired; start again");
  if (!(await stateValid(env, state))) throw new Error("sign-in expired; start again");
  const r = await fetch("https://oauth2.googleapis.com/token", { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ code, client_id: env.GOOGLE_CLIENT_ID, client_secret: env.GOOGLE_CLIENT_SECRET,
      redirect_uri: `${url.origin}/google/callback`, grant_type: "authorization_code" }) });
  const j = await r.json();
  if (!j.id_token) throw new Error("Google did not confirm the sign-in");
  // Received directly from Google's token endpoint over TLS, so the payload is trusted (OIDC 3.1.3.7).
  const p = JSON.parse(atob(j.id_token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
  if (p.aud !== env.GOOGLE_CLIENT_ID || !p.email || p.email_verified !== true) throw new Error("that Google account has no verified email");
  return String(p.email).toLowerCase();
}

// ------------------------------------------------------------------ links
async function lookup(env, code) {
  if (!/^[A-Za-z0-9_-]{24,}$/.test(code)) return null;
  const email = await env.TENANTS.get("enroll:" + code);
  if (!email) return null;
  const tenant = await env.TENANTS.get("tenant:" + email, "json");
  const tun = await env.TENANTS.get("tunnel:" + email, "json");
  if (!tenant || !tun || !tenant.token || !tun.tunnel_token) return null;
  return { id: tenant.tenant_id || email.split("@")[0], token: tenant.token, tunnel: tun.tunnel_token,
    port: tenant.port || 4444, url: tenant.node_url || "https://" + tun.hostname, name: (tenant.name || tenant.tenant_id || email).split(/[ .@-]/)[0] };
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url), path = url.pathname;
    try {
      if (path === "/health") return new Response("ok");
      if (path === "/") return shell("Join NouGen", LANDING);
      if (path === "/privacy") return shell("Privacy", PRIVACY);
      if (path === "/terms") return shell("Terms", TERMS);
      if (path === "/google/start") return googleStart(env, url);
      if (path === "/google/callback") {
        const email = await googleEmail(env, url, req);
        const known = await env.TENANTS.get("tenant:" + email);
        if (!known && !(await underIpLimit(env, req.headers.get("cf-connecting-ip") || "?")))
          return shell("Try later", "<h1>Too many sign-ups</h1><p>This network has created several nodes today. Try again tomorrow.</p>");
        await provision(env, email);
        return Response.redirect(`${url.origin}/j/${await mintLink(env, email)}`, 302);
      }
      const m = path.match(/^\/j\/([^/]+)(\/setup(\.sh)?)?\/?$/);
      if (m) {
        const t = await lookup(env, m[1]);
        if (!t) return shell("Link expired", `<h1>This link has expired</h1><p><a class="join-action" href="/">Start again</a></p>`);
        if (!m[2]) return linkPage(t.name, m[1], String(t.url || "").replace(/^https:\/\//, ""));
        const sh = !!m[3];
        return new Response(sh ? setupSh(t) : setupCmd(t), { headers: { "content-type": "application/octet-stream", "cache-control": "no-store",
          "content-disposition": `attachment; filename="${sh ? "setup-nougen.sh" : "Set up NouGen.cmd"}"` } });
      }
      return new Response("Not found", { status: 404 });
    } catch (e) {
      return shell("Something went wrong", `<h1>Something went wrong</h1><p>${esc(e.message || e)}</p><p><a class="join-action" href="/">Try again</a></p>`);
    }
  },
};

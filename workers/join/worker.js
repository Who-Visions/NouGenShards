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
const JOIN_CSS = ":root {\n  --accent: #e8b86d;\n  --accent-2: #e8b86d;\n  --accent-green: #a9c79b;\n  --accent-purple: #c8bfad;\n  --accent-rgb: 232, 184, 109;\n  --bg: #141414;\n  --bg-gradient: var(--bg);\n  --cluster-gap: 1.25rem;\n  --control-ink: #141414;\n  --danger: #ffb4ab;\n  --fleet-card-min: 23rem;\n  --focus: #e8b86d;\n  --font-main: system-ui, sans-serif;\n  --font-mono: Consolas, monospace;\n  --line: #777777;\n  --line-body: 1.65;\n  --line-glow: #777777;\n  --motion-ease: ease-out;\n  --motion-fast: 120ms;\n  --muted: #bdb8ad;\n  --panel: #202020;\n  --panel-2: #282828;\n  --panel-hover: #333333;\n  --panel-solid: #202020;\n  --radius-lg: 4px;\n  --radius-md: 3px;\n  --radius-sm: 2px;\n  --reading-measure: 65ch;\n  --space-1: 0.25rem;\n  --space-2: 0.5rem;\n  --space-3: 0.75rem;\n  --space-4: 1rem;\n  --space-5: 1.5rem;\n  --space-6: 2rem;\n  --status-conflict-bg: rgba(255, 180, 171, 0.12);\n  --status-conflict-border: #ffb4ab;\n  --status-conflict-text: #ffb4ab;\n  --status-offline-bg: rgba(189, 184, 173, 0.10);\n  --status-offline-border: #777777;\n  --status-offline-text: #bdb8ad;\n  --status-pending-bg: rgba(232, 184, 109, 0.12);\n  --status-pending-border: #e8b86d;\n  --status-pending-text: #e8b86d;\n  --status-sim-bg: rgba(189, 184, 173, 0.10);\n  --status-sim-border: #777777;\n  --status-sim-text: #bdb8ad;\n  --status-verified-bg: rgba(169, 199, 155, 0.12);\n  --status-verified-border: #a9c79b;\n  --status-verified-text: #a9c79b;\n  --target-min: 1.5rem;\n  --target-touch: 2.75rem;\n  --text: #f2eee6;\n  --type-body: 1rem;\n  --type-meta: 0.8125rem;\n  --warn: #e8b86d;\n  --workbench-width: 87.5rem;\n}\n:root[data-theme=\"dark\"] {\n\n}\n:root[data-theme=\"light\"] {\n  --accent: #765013;\n  --accent-2: #765013;\n  --bg: #f5f1e8;\n  --control-ink: #ffffff;\n  --danger: #a62520;\n  --focus: #765013;\n  --line: #76716a;\n  --muted: #555047;\n  --panel: #ffffff;\n  --panel-2: #eee9df;\n  --panel-hover: #e1dbce;\n  --panel-solid: #ffffff;\n  --status-conflict-bg: rgba(166, 37, 32, 0.10);\n  --status-conflict-border: #a62520;\n  --status-conflict-text: #a62520;\n  --status-offline-bg: rgba(85, 80, 71, 0.08);\n  --status-offline-border: #76716a;\n  --status-offline-text: #555047;\n  --status-pending-bg: rgba(118, 80, 19, 0.10);\n  --status-pending-border: #765013;\n  --status-pending-text: #765013;\n  --status-sim-bg: rgba(85, 80, 71, 0.08);\n  --status-sim-border: #76716a;\n  --status-sim-text: #555047;\n  --status-verified-bg: rgba(20, 90, 50, 0.10);\n  --status-verified-border: #145a32;\n  --status-verified-text: #145a32;\n  --text: #202020;\n}\n\n:where(a, button, input, select, textarea, [tabindex]):focus-visible {\n  outline: 2px solid var(--focus);\n  outline-offset: 3px;\n}\n@media (prefers-reduced-motion: reduce) {\n  *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }\n}\n\nbody {\n  font-family: var(--font-main);\n  font-size: var(--type-body);\n  line-height: var(--line-body);\n  max-width: var(--reading-measure);\n  margin: 10vh auto;\n  padding: 0 var(--space-4);\n  color: var(--text);\n  background: var(--bg);\n}\n\nh1 {\n  font-size: 1.875rem;\n  line-height: 1.2;\n  margin: 0 0 var(--space-3);\n}\n\n.join-action {\n  display: inline-flex;\n  align-items: center;\n  justify-content: center;\n  min-height: var(--target-touch);\n  padding: var(--space-3) var(--space-5);\n  background: var(--accent);\n  color: var(--control-ink);\n  border: 1px solid var(--accent);\n  border-radius: var(--radius-md);\n  text-decoration: none;\n  font-weight: 600;\n  font-size: 1.125rem;\n  transition: background-color var(--motion-fast) var(--motion-ease);\n}\n\n.join-action:hover {\n  background: var(--accent-2);\n}\n\n.join-meta,\nsmall {\n  color: var(--muted);\n  font-size: var(--type-meta);\n}\n\n.join-meta a {\n  color: var(--muted);\n}\n\n.join-footer {\n  margin-top: var(--space-6);\n  padding-top: var(--space-4);\n  border-top: 1px solid var(--line);\n}\n\ncode {\n  font-family: var(--font-mono);\n  font-size: var(--type-meta);\n  background: var(--panel);\n  border: 1px solid var(--line);\n  border-radius: var(--radius-sm);\n  padding: 0.125rem var(--space-1);\n  overflow-wrap: anywhere;\n}";
// END GENERATED NOUGEN-CORE CSS

export const shell = (title, body) => new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(title)}</title>
<style>${JOIN_CSS}</style></head><body><main class="join-shell">${body}
<footer class="join-meta join-footer"><a href="/privacy">Privacy</a> · <a href="/terms">Terms</a></footer></main></body></html>`,
  { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });

const LANDING = `<h1>Join NouGen</h1><p>Sign in with Google and your computer becomes your own NouGen node. No passwords to create, nothing to install by hand.</p>
<p><a class="join-action" href="/google/start">Continue with Google</a></p>`;

const PRIVACY = `<h1>Privacy</h1><p>We use your Google sign-in only to read your email address, which names your node and lets you sign in again. We store your email, your node's address and its connection keys. We do not read your mail, contacts or files, and we do not sell or share your information.</p><p>To remove your node and its records, sign in again and use the delete option, or contact the operator.</p>`;
const TERMS = `<h1>Terms</h1><p>NouGen nodes are provided as-is, without warranty. Do not use your node for anything unlawful or abusive; nodes used that way are removed. Unused nodes that never connect may be removed after the setup link expires.</p>`;

const linkPage = (name, code) => shell("NouGen setup", `<h1>Hi ${esc(name)}</h1>
<p>Press the button, then open the file it saves. It sets everything up by itself and opens your page when it's done.</p>
<p><a class="join-action" id="go" href="/j/${code}/setup">Set up this computer</a></p>
<p class="join-meta" id="hint">If Windows asks "Do you want to run this file?", choose <b>Run</b>.</p>
<script>if(!/Windows/i.test(navigator.userAgent)){var g=document.getElementById('go');g.href='/j/${code}/setup.sh';g.download='setup-nougen.sh';
document.getElementById('hint').innerHTML='On Mac or Linux: open Terminal and run <code>sh ~/Downloads/setup-nougen.sh</code>';}</script>`);

// ------------------------------------------------------------------ setup files
export function setupCmd(t) {
  return ["@echo off", `rem NouGen setup for ${t.id}. Private: contains this computer's keys.`,
    `powershell -NoProfile -ExecutionPolicy Bypass -Command "$f='%~f0'; $s=(Get-Content -Raw $f) -split '(?m)^::PS\\s*$',2; iex $s[1]"`,
    "exit /b", "::PS",
    "$ErrorActionPreference = 'Stop'", "$ProgressPreference = 'SilentlyContinue'",
    "[Net.ServicePointManager]::SecurityProtocol = 'Tls12'",
    "$home_ = Join-Path $env:LOCALAPPDATA 'NouGen'",
    `$td = Join-Path $home_ '${psq(t.id)}'`, "New-Item -ItemType Directory -Force $td | Out-Null",
    "Write-Host 'Setting up NouGen on this computer. This takes a few minutes and needs nothing from you.'",
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
    "$run = Join-Path $td 'run.ps1'", "@'",
    `$env:NGS_NODE_TOKEN = '${psq(t.token)}'`,
    `$env:NGS_HUD_USER = '${psq(t.id)}'`,
    `$env:NGS_HUD_PASSWORD = '${psq(t.token)}'`,
    `$env:NGS_PORT = '${t.port}'`,
    "$h = Join-Path $env:LOCALAPPDATA 'NouGen'",
    `$t = Join-Path $h '${psq(t.id)}'`,
    "$env:NOUGEN_VAULT_DIR = Join-Path $t 'shards'; $env:NOUGEN_HOME = $t",
    "$srcDir = Join-Path $t 'NouGenShards'",
    "Start-Process -WindowStyle Hidden -WorkingDirectory $srcDir -FilePath (Join-Path $h 'uv.exe') -ArgumentList 'run','--python','3.11',(Join-Path $srcDir 'app.py')",
    `Start-Process -WindowStyle Hidden -FilePath (Join-Path $t 'cloudflared.exe') -ArgumentList 'tunnel','--no-autoupdate','run','--token','${psq(t.tunnel)}'`,
    "'@ | Set-Content -Encoding UTF8 $run",
    "$launch = \"conhost.exe --headless powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `\"$run`\"\"",
    `Set-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run' -Name 'NouGen-${psq(t.id)}' -Value $launch`,
    "& powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $run",
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
cat > run.sh <<'RUN'
#!/bin/sh
B="$HOME/.nougen-node"; H="$B/${shq(t.id)}"
export NGS_NODE_TOKEN='${shq(t.token)}' NGS_HUD_USER='${shq(t.id)}' NGS_HUD_PASSWORD='${shq(t.token)}' NGS_PORT='${t.port}' NOUGEN_VAULT_DIR="$H/shards" NOUGEN_HOME="$H"
(cd "$H/NouGenShards" && nohup "$B/uv" run --python 3.11 "$H/NouGenShards/app.py" >"$H/node.log" 2>&1 &)
nohup "$H/cloudflared" tunnel --no-autoupdate run --token '${shq(t.tunnel)}' >"$H/tunnel.log" 2>&1 &
RUN
chmod 700 run.sh
if [ "$OS" = Darwin ]; then
  P="$HOME/Library/LaunchAgents/com.nougen.node.${shq(t.id)}.plist"; mkdir -p "$(dirname "$P")"
  printf '<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict><key>Label</key><string>com.nougen.node.${shq(t.id)}</string><key>ProgramArguments</key><array><string>/bin/sh</string><string>%s</string></array><key>RunAtLoad</key><true/></dict></plist>' "$H/run.sh" > "$P"
else
  (crontab -l 2>/dev/null | grep -v "$H/run.sh"; echo "@reboot $H/run.sh") | crontab - 2>/dev/null || true
fi
sh "$H/run.sh"
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
  const port = (tenant && tenant.port) || await nextPort(env);
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
  if (!t) t = await cf(env, "POST", `/accounts/${acct}/cfd_tunnel`, { name, config_src: "cloudflare", tunnel_secret: btoa(rand(32)) });
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

// Every tenant gets its own local port so several accounts can run on one computer.
async function nextPort(env) {
  const n = parseInt((await env.TENANTS.get("portseq")) || "0", 10) + 1;
  await env.TENANTS.put("portseq", String(n));
  return 4444 + (n % 20000);
}

async function mintLink(env, email) {
  const code = rand(24);
  await env.TENANTS.put("enroll:" + code, email, { expirationTtl: 86400 * parseInt(env.LINK_TTL_DAYS || "14", 10) });
  return code;
}

async function underIpLimit(env, ip) {
  const day = new Date().toISOString().slice(0, 10), key = `joinrate:${day}:${ip}`;
  const n = parseInt((await env.TENANTS.get(key)) || "0", 10);
  if (n >= parseInt(env.JOIN_MAX_PER_IP_DAY || "5", 10)) return false;
  await env.TENANTS.put(key, String(n + 1), { expirationTtl: 172800 });
  return true;
}

// ------------------------------------------------------------------ Google
async function googleStart(env, url) {
  const state = rand(18);
  const q = new URLSearchParams({ client_id: env.GOOGLE_CLIENT_ID, redirect_uri: `${url.origin}/google/callback`,
    response_type: "code", scope: "openid email", state, prompt: "select_account" });
  return new Response(null, { status: 302, headers: { location: "https://accounts.google.com/o/oauth2/v2/auth?" + q,
    "set-cookie": `nj_state=${state}; Path=/google; Max-Age=600; HttpOnly; Secure; SameSite=Lax` } });
}

async function googleEmail(env, url, req) {
  const state = url.searchParams.get("state"), code = url.searchParams.get("code");
  const cookie = (req.headers.get("cookie") || "").match(/(?:^|;\s*)nj_state=([^;]+)/);
  if (!code || !state || !cookie || cookie[1] !== state) throw new Error("sign-in expired; start again");
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
        if (!m[2]) return linkPage(t.name, m[1]);
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

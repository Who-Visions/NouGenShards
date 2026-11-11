// nougen-join: the tenant's one link. GET /j/<code> serves a page with one button;
// GET /j/<code>/setup serves that tenant's "Set up NouGen.cmd", rendered from the
// records tenant_onboard already wrote to the TENANTS KV (enroll:<code> -> email,
// tenant:<email>, tunnel:<email>). Isolated from nougen-fleet-mcp on purpose: no
// shared code, no shared routes, so it cannot break the connector surface.
// Codes are 32+ random url-safe chars and expire via KV TTL (set at mint time).

const PAGE = (name, url) => `<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>NouGen setup</title>
<style>body{font:18px/1.5 system-ui,sans-serif;max-width:560px;margin:12vh auto;padding:0 20px;color:#111;background:#fff}
a.b{display:inline-block;background:#1a56db;color:#fff;padding:16px 28px;border-radius:10px;text-decoration:none;font-weight:600;font-size:20px}
p.s{color:#555;font-size:15px}@media(prefers-color-scheme:dark){body{background:#111;color:#eee}p.s{color:#aaa}}</style></head>
<body><h1>Hi ${name}</h1><p>Press the button, then open the file it saves. That's it. It sets everything up by itself and opens your page when it's done.</p>
<p><a class="b" href="${url}">Set up this computer</a></p>
<p class="s">If Windows asks "Do you want to run this file?", choose <b>Run</b>.</p></body></html>`;

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const psq = (s) => String(s).replace(/'/g, "''");

function setupCmd(tid, token, tunnel, port, nodeUrl) {
  return [
    "@echo off",
    `rem NouGen setup for ${tid}. Private: contains this computer's keys.`,
    `powershell -NoProfile -ExecutionPolicy Bypass -Command "$f='%~f0'; $s=(Get-Content -Raw $f) -split '(?m)^::PS\\s*$',2; iex $s[1]"`,
    "exit /b",
    "::PS",
    "$ErrorActionPreference = 'Stop'",
    "$ProgressPreference = 'SilentlyContinue'",
    "[Net.ServicePointManager]::SecurityProtocol = 'Tls12'",
    "$home_ = Join-Path $env:LOCALAPPDATA 'NouGen'",
    "New-Item -ItemType Directory -Force $home_ | Out-Null",
    "Write-Host 'Setting up NouGen on this computer. This takes a few minutes and needs nothing from you.'",
    "function Get-File($url, $out) { if (-not (Test-Path $out)) { Invoke-WebRequest -UseBasicParsing $url -OutFile $out } }",
    "$uv = Join-Path $home_ 'uv.exe'",
    "if (-not (Test-Path $uv)) { $z = Join-Path $home_ 'uv.zip'; Get-File 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' $z; Expand-Archive -Force $z $home_; Remove-Item $z }",
    "$cf = Join-Path $home_ 'cloudflared.exe'",
    "Get-File 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' $cf",
    "$src = Join-Path $home_ 'NouGenShards'; $z = Join-Path $home_ 'src.zip'",
    "Invoke-WebRequest -UseBasicParsing 'https://github.com/Who-Visions/NouGenShards/archive/refs/heads/main.zip' -OutFile $z",
    "if (Test-Path $src) { Remove-Item -Recurse -Force $src }",
    "Expand-Archive -Force $z $home_; Remove-Item $z; Move-Item (Join-Path $home_ 'NouGenShards-main') $src",
    "$run = Join-Path $home_ 'run.ps1'",
    "@'",
    `$env:NGS_NODE_TOKEN = '${psq(token)}'`,
    `$env:NGS_PORT = '${port}'`,
    "$h = Join-Path $env:LOCALAPPDATA 'NouGen'",
    "Start-Process -WindowStyle Hidden -WorkingDirectory (Join-Path $h 'NouGenShards') -FilePath (Join-Path $h 'uv.exe') -ArgumentList 'run','--python','3.11','app.py'",
    `Start-Process -WindowStyle Hidden -FilePath (Join-Path $h 'cloudflared.exe') -ArgumentList 'tunnel','--no-autoupdate','run','--token','${psq(tunnel)}'`,
    "'@ | Set-Content -Encoding UTF8 $run",
    "$launch = \"conhost.exe --headless powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `\"$run`\"\"",
    "Set-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run' -Name 'NouGen' -Value $launch",
    "Get-Process cloudflared -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $cf } | Stop-Process -Force",
    "& powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $run",
    "Write-Host 'Starting... (first start downloads Python once)'",
    `for ($i = 0; $i -lt 90; $i++) { try { Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:${port}/health' -TimeoutSec 3 | Out-Null; break } catch { Start-Sleep 5 } }`,
    `Start-Process '${psq(nodeUrl)}'`,
    "Write-Host 'Done. NouGen is on and will start by itself whenever this computer starts.'",
    "Start-Sleep 5",
    "",
  ].join("\r\n");
}

async function lookup(env, code) {
  if (!/^[A-Za-z0-9_-]{24,}$/.test(code)) return null;
  const email = await env.TENANTS.get("enroll:" + code);
  if (!email) return null;
  const tenant = await env.TENANTS.get("tenant:" + email, "json");
  const tunnel = await env.TENANTS.get("tunnel:" + email, "json");
  if (!tenant || !tunnel || !tenant.token || !tunnel.tunnel_token) return null;
  return { email, tenant, tunnel };
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const m = url.pathname.match(/^\/j\/([^/]+)(\/setup)?\/?$/);
    if (url.pathname === "/health") return new Response("ok");
    if (!m) return new Response("Not found", { status: 404 });
    const rec = await lookup(env, m[1]);
    if (!rec) return new Response("This setup link is not valid or has expired. Ask for a new one.", { status: 404 });
    const tid = rec.tenant.tenant_id || rec.email.split("@")[0];
    if (!m[2]) {
      const name = esc((rec.tenant.name || tid).split(/[ .@]/)[0]);
      return new Response(PAGE(name, `/j/${m[1]}/setup`), { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
    }
    const body = setupCmd(tid, rec.tenant.token, rec.tunnel.tunnel_token, rec.tenant.port || 4444, rec.tenant.node_url || "https://" + rec.tunnel.hostname);
    return new Response(body, { headers: {
      "content-type": "application/octet-stream", "cache-control": "no-store",
      "content-disposition": 'attachment; filename="Set up NouGen.cmd"' } });
  },
};

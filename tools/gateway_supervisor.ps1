<#
  gateway_supervisor.ps1 - keep the outpost shard bridge self-healing.

  The fragile link in the whole chain is the quick tunnel: its hostname is
  random and changes every time cloudflared restarts, but the fleet worker has
  that hostname baked into SHARD_GATEWAY_URL. Reboot the box and the worker
  points at a dead URL - gates shut, silently.

  This supervisor closes that gap. On a loop it:
    1. ensures the node lane is up      (node_lane.ps1 start)
    2. ensures a tunnel is up           (restarts cloudflared if the URL is gone)
    3. detects the CURRENT tunnel URL   (from cloudflared's own log)
    4. if it differs from what the worker holds, pushes the new URL into the
       worker's SHARD_GATEWAY_URL var via wrangler and redeploys - so the
       gateway re-points itself with nobody touching a dashboard.

  Nothing here needs a login: quick tunnels are anonymous, wrangler is already
  authenticated on this box, and the node token is read from the vault.

  Run in the foreground to watch it:   .\tools\gateway_supervisor.ps1
  Run once (no loop, for a scheduled task tick):  -Once
#>
param(
    [switch]$Once,
    [int]$IntervalSec = 60
)

$ErrorActionPreference = 'Stop'
$Root       = Split-Path -Parent $PSScriptRoot
$Python     = Join-Path $Root '.venv\Scripts\python.exe'
$NodeLane   = Join-Path $PSScriptRoot 'node_lane.ps1'
$WorkerDir  = Join-Path (Split-Path -Parent $Root) 'nougen-fleet-mcp'
$RunDir     = Join-Path $Root '.node'
$Cloudflared = Join-Path $PSScriptRoot 'bin\cloudflared.exe'
$TunnelLog  = Join-Path $RunDir 'tunnel.log'
$TunnelPid  = Join-Path $RunDir 'tunnel.pid'
$StateFile  = Join-Path $RunDir 'gateway_url.txt'
$Port       = if ($env:NGS_PORT) { $env:NGS_PORT } else { '4444' }
$env:PYTHONPATH = Join-Path $Root 'src'
$env:NOUGEN_VAULT_DIR = Join-Path $env:USERPROFILE '.nougen\shards'
$env:NOUGEN_SECRETS_VAULT_DIR = Join-Path $env:USERPROFILE '.nougen\secrets'

function Log($m) { "{0}  {1}" -f (Get-Date -Format 'HH:mm:ss'), $m }

function Get-TunnelUrl {
    if (-not (Test-Path $TunnelLog)) { return $null }
    $m = Select-String -Path $TunnelLog -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue |
         Select-Object -Last 1
    if ($m) { return $m.Matches[-1].Value }
    return $null
}

function Test-TunnelAlive($url) {
    if (-not $url) { return $false }
    try { (Invoke-WebRequest "$url/health" -TimeoutSec 8 -UseBasicParsing).StatusCode -eq 200 }
    catch { $false }
}

function Start-Tunnel {
    # kill any stale process we own
    if (Test-Path $TunnelPid) {
        $old = (Get-Content $TunnelPid -Raw).Trim()
        if ($old) { Stop-Process -Id ([int]$old) -Force -ErrorAction SilentlyContinue }
    }
    Remove-Item $TunnelLog -ErrorAction SilentlyContinue
    $p = Start-Process -FilePath $Cloudflared `
        -ArgumentList 'tunnel', '--url', "http://127.0.0.1:$Port" `
        -WindowStyle Hidden -PassThru -RedirectStandardError $TunnelLog
    Set-Content $TunnelPid $p.Id -Encoding utf8
    foreach ($i in 1..40) {
        Start-Sleep -Milliseconds 500
        $u = Get-TunnelUrl
        if ($u -and (Test-TunnelAlive $u)) { return $u }
    }
    return (Get-TunnelUrl)
}

function Sync-Worker($url) {
    # Only touch the worker when the URL actually changed - deploys aren't free.
    $known = if (Test-Path $StateFile) { (Get-Content $StateFile -Raw).Trim() } else { '' }
    if ($known -eq $url) { return $false }

    Log "URL changed: '$known' -> '$url'  (updating worker)"
    Push-Location $WorkerDir
    try {
        # SHARD_GATEWAY_URL is a var in wrangler.jsonc; rewrite it in place so
        # source and live stay identical, then deploy.
        $wf = Join-Path $WorkerDir 'wrangler.jsonc'
        $raw = [System.IO.File]::ReadAllText($wf)
        $raw = $raw -replace '("SHARD_GATEWAY_URL":\s*")[^"]*(")', "`${1}$url`${2}"
        [System.IO.File]::WriteAllText($wf, $raw, (New-Object System.Text.UTF8Encoding $false))
        & npx --yes wrangler@latest deploy 2>&1 | Select-Object -Last 1 | ForEach-Object { Log $_ }
        Set-Content $StateFile $url -Encoding utf8

        # Re-pointing the URL is not the same as the gateway working. /health is
        # UNAUTHENTICATED, so shards_status reads green while every real call
        # 401s -- that false green hid a drifted SHARD_GATEWAY_TOKEN for hours on
        # 2026-08-15. Prove an AUTHENTICATED call succeeds, and if it does not,
        # re-put the token from the vault (the usual cause) and say so loudly.
        $probe = & $Python (Join-Path $PSScriptRoot 'gateway_probe.py') 2>&1 | Select-Object -Last 1
        Log "post-deploy probe: $probe"
        if ($probe -notmatch '^OK') {
            Log "authenticated call FAILED after re-point - re-putting SHARD_GATEWAY_TOKEN from vault"
            $tok = Get-NodeToken
            $tok | & npx --yes wrangler@latest secret put SHARD_GATEWAY_TOKEN --name nougen-fleet-mcp 2>&1 |
                Select-Object -Last 1 | ForEach-Object { Log $_ }
            $probe2 = & $Python (Join-Path $PSScriptRoot 'gateway_probe.py') 2>&1 | Select-Object -Last 1
            Log "probe after token re-put: $probe2"
        }
    } finally { Pop-Location }
    return $true
}

function Tick {
    # 1. node
    & $NodeLane start | Out-Null

    # 2/3. tunnel + its URL
    $url = Get-TunnelUrl
    if (-not (Test-TunnelAlive $url)) {
        Log "tunnel down - (re)starting"
        $url = Start-Tunnel
    }
    if (-not $url) { Log "no tunnel URL yet"; return }

    # 4. keep the worker pointed at it
    if (-not (Sync-Worker $url)) { Log "healthy - node up, tunnel up, worker current ($url)" }
}

if ($Once) { Tick; return }

Log "supervisor start (interval ${IntervalSec}s)"
while ($true) {
    try { Tick } catch { Log "tick error: $($_.Exception.Message)" }
    Start-Sleep -Seconds $IntervalSec
}

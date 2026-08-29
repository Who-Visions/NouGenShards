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

# Write-Host, NOT a bare string: a bare string lands in the function's OUTPUT
# stream, so any function that logs returns those log lines as part of its
# return value. That made `if (Assert-GatewayAuth)` truthy on the failure path -
# it logged "authenticated call FAILED" and the caller still printed AUTHENTICATED.
function Log($m) { Write-Host ("{0}  {1}" -f (Get-Date -Format 'HH:mm:ss'), $m) }

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

    } finally { Pop-Location }
    Assert-GatewayAuth -Context 'post-deploy'
    return $true
}

function Assert-GatewayAuth {
    # Re-pointing the URL is not the same as the gateway working. /health is
    # UNAUTHENTICATED, so shards_status reads green while every real call
    # 401s -- that false green hid a drifted SHARD_GATEWAY_TOKEN for hours on
    # 2026-08-15. Prove an AUTHENTICATED call succeeds, and if it does not,
    # re-put the token from the vault (the usual cause) and say so loudly.
    #
    # This USED to live inside Sync-Worker, after its "URL unchanged -> return"
    # early exit, so it only ran on the rare tick where the tunnel hostname
    # moved. Every other tick logged "healthy" without ever proving auth -- the
    # same false green the comment above was written to kill. On 2026-08-29 that
    # let a drifted token read as healthy while shards_search returned [] over
    # 178k shards. It now runs on EVERY tick.
    param([string]$Context = 'tick')

    $probe = & $Python (Join-Path $PSScriptRoot 'gateway_probe.py') 2>&1 | Select-Object -Last 1
    if ($probe -match '^OK') { return 'ok' }

    # AUTH-OK-NO-DATA means the whole OAuth chain passed and the node behind the
    # gateway came back empty. The gateway is the one component that just proved
    # it works, so re-putting its token would be fixing the wrong thing.
    if ($probe -match '^AUTH-OK-NO-DATA') {
        Log "$Context probe: $probe"
        Log "gateway AUTHENTICATES - the node behind it is empty or down; not touching SHARD_GATEWAY_TOKEN"
        return 'nodata'
    }

    # "cannot verify" is NOT "auth is broken", and conflating them is just the
    # false green wearing the other mask. gateway_probe.py authenticates with
    # FLEET_KEY_OUTPOST - the OUTPOST host's fleet key. On any other box that key
    # is legitimately absent, so the probe fails for a reason that says nothing
    # about the gateway. Report that as unverified and do NOT touch the worker's
    # token over it.
    if ($probe -match '^SKIPPED|FLEET_KEY_OUTPOST missing|vault unreadable') {
        Log "$Context probe cannot run here: $probe"
        Log "gateway auth UNVERIFIED from this host (probe needs the Outpost fleet key) - not touching SHARD_GATEWAY_TOKEN"
        return 'unverified'
    }

    Log "$Context probe: $probe"
    Log "authenticated call FAILED - re-putting SHARD_GATEWAY_TOKEN from vault"
    $tok = $null
    try {
        # Resolve the node token from the DPAPI-backed keymaker vault. The key
        # NAME is env-resolvable so a host that names it differently does not
        # need a code change; the VALUE is never logged or echoed.
        $keyName = if ($env:NGS_NODE_TOKEN_KEY) { $env:NGS_NODE_TOKEN_KEY } else { 'SHARD_GATEWAY_TOKEN' }
        $tok = & $Python -c "from nougen_shards import keymaker as k; print(k.get_secret('$keyName') or '')"
        $tok = ($tok | Select-Object -Last 1).Trim()
    } catch {
        $tok = $null
    }
    if (-not $tok) {
        # Distinct from a drifted token: re-putting cannot fix a key that is not
        # there, so name the key instead of retrying into the same wall.
        Log "CANNOT re-put: '$keyName' is absent from the keymaker vault on this host"
        return 'failed'
    }
    Push-Location $WorkerDir
    try {
        $tok | & npx --yes wrangler@latest secret put SHARD_GATEWAY_TOKEN --name nougen-fleet-mcp 2>&1 |
            Select-Object -Last 1 | ForEach-Object { Log $_ }
    } finally { Pop-Location }
    $probe2 = & $Python (Join-Path $PSScriptRoot 'gateway_probe.py') 2>&1 | Select-Object -Last 1
    Log "probe after token re-put: $probe2"
    if ($probe2 -match '^OK') { return 'ok' } else { return 'failed' }
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
    if (-not (Sync-Worker $url)) {
        # URL unchanged is NOT the same as working: verify auth before claiming health.
        switch (Assert-GatewayAuth) {
            'ok'         { Log "healthy - node up, tunnel up, worker current and AUTHENTICATED ($url)" }
            'unverified' { Log "node up, tunnel up, worker current ($url) - auth UNVERIFIED from this host" }
            'nodata'     { Log "gateway AUTHENTICATED but its node returned no data - worker current ($url)" }
            default      { Log "DEGRADED - node up, tunnel up, worker points at $url but authenticated calls FAIL" }
        }
    }
}

if ($Once) { Tick; return }

Log "supervisor start (interval ${IntervalSec}s)"
while ($true) {
    try { Tick } catch { Log "tick error: $($_.Exception.Message)" }
    Start-Sleep -Seconds $IntervalSec
}

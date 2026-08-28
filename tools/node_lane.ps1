<#
  node_lane.ps1 - run this box as a replica of the shared NouGen shard lane.

  The node serves the REST API (/health, /search, /capture, /sync/*), the
  token-gated MCP endpoint at /mcp. Blade and Who-Art use the same lane token;
  the named Cloudflare tunnel is only the highway between that lane and clients.

  The write token is never hardcoded - it is read at start time from the
  keymaker vault under NGS_NODE_TOKEN.

  Usage:
    .\tools\node_lane.ps1 start
    .\tools\node_lane.ps1 status
    .\tools\node_lane.ps1 stop
    .\tools\node_lane.ps1 token     # prints only a non-reversible fingerprint
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'status', 'token')]
    [string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'

$Root      = Split-Path -Parent $PSScriptRoot          # ...\Outpost\NouGen
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$Python    = if (Test-Path $VenvPython) {
    $VenvPython
} else {
    (Get-Command python -ErrorAction Stop).Source
}
$RunDir    = Join-Path $Root '.node'
$PidFile   = Join-Path $RunDir 'node.pid'
$OutLog    = Join-Path $RunDir 'node.out.log'
$ErrLog    = Join-Path $RunDir 'node.err.log'
$VaultDir  = Join-Path $env:USERPROFILE '.nougen\shards'   # shard substrate
# Secrets moved to their own vault upstream (~/.nougen/secrets). Pointing
# keymaker at the shard cluster made init_vault icacls 40+ DBs and time out.
$SecretsDir = Join-Path $env:USERPROFILE '.nougen\secrets'
$Port      = if ($env:NGS_PORT) { $env:NGS_PORT } else { '4444' }
$BaseUrl   = "http://127.0.0.1:$Port"
$SecretKey = 'NGS_NODE_TOKEN'
# Shared with start_grid.py's NODE_LOCK_PATH (same default path) so this
# script and the --watch watchdog never race to spawn a competing server.
# 2026-08-27 incident: a manual restart here and the watchdog's own restart
# fired within the same second, stacking 4 uvicorn/ngs_node_serve processes
# on :4444 - Windows silently routed traffic to whichever bound last, so a
# PID check reported "up" while the port actually served nothing.
$LockPath  = if ($env:NOUGEN_NODE_LOCK) { $env:NOUGEN_NODE_LOCK } else { Join-Path $env:USERPROFILE '.nougen\bin\node_lane.lock' }

function Enter-NodeLock {
    try {
        return [System.IO.File]::Open($LockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    } catch [System.IO.IOException] {
        return $null
    }
}

function Get-NodeToken {
    $env:PYTHONPATH = Join-Path $Root 'src'
    $env:NOUGEN_VAULT_DIR = $VaultDir
    $env:NOUGEN_SECRETS_VAULT_DIR = $SecretsDir
    $tok = & $Python -c "from nougen_shards import keymaker as k; print(k.get_secret('$SecretKey') or '')"
    $tok = ($tok | Select-Object -Last 1).Trim()
    if (-not $tok) { throw "$SecretKey not found in the canonical secrets vault. Ingest the shared lane token before starting." }
    return $tok
}

function Get-NodePid {
    if (-not (Test-Path $PidFile)) { return $null }
    $id = (Get-Content $PidFile -Raw).Trim()
    if (-not $id) { return $null }
    try { $p = Get-Process -Id ([int]$id) -ErrorAction Stop } catch { return $null }
    # Guard against PID reuse by a non-python process.
    if ($p.ProcessName -notlike 'python*') { return $null }
    return [int]$id
}

function Get-ListenerPid {
    $listener = Get-NetTCPConnection -State Listen -LocalPort ([int]$Port) `
        -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener) { return $null }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    if (-not $proc -or $proc.Name -notlike 'python*' -or
        $proc.CommandLine -notmatch '-m uvicorn app:app') {
        throw "port $Port is owned by an unexpected process; refusing to manage it"
    }
    return [int]$listener.OwningProcess
}

switch ($Action) {

    'token' {
        $token = Get-NodeToken
        $bytes = [Text.Encoding]::UTF8.GetBytes($token)
        $sha = [Security.Cryptography.SHA256]::Create()
        try {
            $fp = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').Substring(0, 12).ToLowerInvariant()
        } finally {
            $sha.Dispose()
        }
        "node token configured (fp=$fp)"
        break
    }

    'start' {
        $listener = Get-ListenerPid
        if ($listener) { "node already running (listener pid $listener) on $BaseUrl"; break }

        $lockHandle = Enter-NodeLock
        if (-not $lockHandle) {
            "another launcher is already starting the node (lock held); standing down"
            break
        }
        try {
            # Re-check after acquiring the lock - the watchdog (or another
            # invocation of this script) may have finished while we waited.
            $listener = Get-ListenerPid
            if ($listener) { "node came up while waiting for the lock (listener pid $listener) on $BaseUrl"; break }

            $running = Get-NodePid
            if ($running) {
                Stop-Process -Id $running -Force -Confirm:$false -ErrorAction SilentlyContinue
                Remove-Item $PidFile -ErrorAction SilentlyContinue
            }

            if (-not (Test-Path $RunDir)) { New-Item -ItemType Directory -Path $RunDir | Out-Null }

            $token = Get-NodeToken

            # The child inherits these. ngs_node_serve resolves the shared token,
            # binds the token-gated data surface, and deliberately leaves the HUD
            # unmounted when network exposed.
            $env:NGS_NODE_TOKEN   = $token
            $env:NGS_PORT         = $Port
            $env:NGS_BIND_HOST    = if ($env:NGS_BIND_HOST) { $env:NGS_BIND_HOST } else { '0.0.0.0' }
            $env:NOUGEN_VAULT_DIR = $VaultDir
            $env:NOUGEN_SECRETS_VAULT_DIR = $SecretsDir
            $env:PYTHONPATH       = Join-Path $Root 'src'

            $proc = Start-Process -FilePath $Python -ArgumentList 'tools\ngs_node_serve.py' `
                -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
                -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog
            Set-Content -Path $PidFile -Value $proc.Id -Encoding utf8

            # Uvicorn + gradio import takes a few seconds; poll rather than sleep blind.
            $ready = $false
            foreach ($i in 1..30) {
                try {
                    $h = Invoke-RestMethod -Uri "$BaseUrl/health" -TimeoutSec 2
                    $ready = $true
                    break
                } catch { Start-Sleep -Milliseconds 500 }
            }
            if ($ready) {
                # ngs_node_serve spawns uvicorn as a child, so the launcher PID
                # we just wrote is not the process that owns the port. Re-write
                # the pidfile with the actual listener once health is up, so
                # stop/status act on the real server (drift observed 2026-08-27:
                # pidfile said 29824 while 43568 held the port).
                $actualListener = Get-ListenerPid
                if ($actualListener) { Set-Content -Path $PidFile -Value $actualListener -Encoding utf8 }
                "node up  launcher=$($proc.Id) listener=$actualListener  $BaseUrl  shards=$($h.total_shards)  token_configured=$($h.node_token_configured)"
            } else {
                "node did NOT answer /health within 15s - see $ErrLog"
                exit 1
            }
        } finally {
            $lockHandle.Close()
        }
        break
    }

    'stop' {
        $running = Get-NodePid
        $listener = Get-ListenerPid
        if (-not $running -and -not $listener) { 'node not running'; break }
        if ($listener) {
            Stop-Process -Id $listener -Force -Confirm:$false
        }
        if ($running -and $running -ne $listener) {
            Stop-Process -Id $running -Force -Confirm:$false -ErrorAction SilentlyContinue
        }
        # The listener is a child of ngs_node_serve; killing only the pair
        # tracked above can leave a parent (or a stray from another launcher)
        # alive to respawn or re-bind. Reap every process that is verifiably
        # OUR node shape on OUR port - scoped by command line, never by name.
        Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object {
            $_.CommandLine -match 'ngs_node_serve\.py' -or
            ($_.CommandLine -match '-m uvicorn app:app' -and $_.CommandLine -match "--port +$Port")
        } | ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -Confirm:$false -ErrorAction SilentlyContinue
            "  reaped stray node process pid $($_.ProcessId)"
        }
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        "node stopped (launcher=$running listener=$listener)"
        break
    }

    'status' {
        $running = Get-NodePid
        $listener = Get-ListenerPid
        try {
            $h = Invoke-RestMethod -Uri "$BaseUrl/health" -TimeoutSec 3
            "UP    launcher=$running listener=$listener  $BaseUrl  shards=$($h.total_shards)  token=$($h.node_token_configured)  public_ready=$($h.public_ready)"
        } catch {
            "DOWN  launcher=$running listener=$listener  $BaseUrl unreachable"
        }
        break
    }
}

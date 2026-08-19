<#
  node_lane.ps1 - run the NouGenShards node (app.py) as this box's own shard lane.

  The node serves the REST API (/health, /search, /capture, /sync/*), the
  token-gated MCP endpoint at /mcp, and the Cortex HUD at /. It is independent
  of blade's lane: its own token, its own port, same local shard substrate at
  %USERPROFILE%\.nougen\shards.

  The write token is never hardcoded - it is read at start time from the
  keymaker vault under NGS_NODE_TOKEN_OUTPOST.

  Usage:
    .\tools\node_lane.ps1 start
    .\tools\node_lane.ps1 status
    .\tools\node_lane.ps1 stop
    .\tools\node_lane.ps1 token     # prints the token (for wiring a client)
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'status', 'token')]
    [string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'

$Root      = Split-Path -Parent $PSScriptRoot          # ...\Outpost\NouGen
$Python    = Join-Path $Root '.venv\Scripts\python.exe'
$RunDir    = Join-Path $Root '.node'
$PidFile   = Join-Path $RunDir 'node.pid'
$OutLog    = Join-Path $RunDir 'node.out.log'
$ErrLog    = Join-Path $RunDir 'node.err.log'
$VaultDir  = (Join-Path $env:USERPROFILE '.nougen\shards')   # shard substrate
# Secrets moved to their own vault upstream (~/.nougen/secrets). Pointing
# keymaker at the shard cluster made init_vault icacls 40+ DBs and time out.
$SecretsDir = (Join-Path $env:USERPROFILE '.nougen\secrets')
$Port      = if ($env:NGS_PORT) { $env:NGS_PORT } else { '4444' }
$BaseUrl   = "http://127.0.0.1:$Port"
$SecretKey = 'NGS_NODE_TOKEN_OUTPOST'

function Get-NodeToken {
    $env:PYTHONPATH = Join-Path $Root 'src'
    $env:NOUGEN_VAULT_DIR = $VaultDir
    $env:NOUGEN_SECRETS_VAULT_DIR = $SecretsDir
    $tok = & $Python -c "from nougen_shards import keymaker as k; print(k.get_secret('$SecretKey') or '')"
    $tok = ($tok | Select-Object -Last 1).Trim()
    if (-not $tok) { throw "$SecretKey not found in vault $VaultDir. Mint it before starting the lane." }
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

switch ($Action) {

    'token' { Get-NodeToken; break }

    'start' {
        $running = Get-NodePid
        if ($running) { "node already running (pid $running) on $BaseUrl"; break }

        if (-not (Test-Path $RunDir)) { New-Item -ItemType Directory -Path $RunDir | Out-Null }

        $token = Get-NodeToken

        # The child inherits these; app.py appends <cwd>\src to sys.path, so the
        # working directory must be the repo root.
        $env:NGS_NODE_TOKEN   = $token
        $env:NGS_PORT         = $Port
        $env:NOUGEN_VAULT_DIR = $VaultDir
    $env:NOUGEN_SECRETS_VAULT_DIR = $SecretsDir
        $env:PYTHONPATH       = Join-Path $Root 'src'
        # HUD basic-auth: without these the vault UI mounts open on loopback,
        # which becomes a public hole the moment a tunnel points at this port.
        $env:PYTHONPATH       = Join-Path $Root 'src'
        $env:NGS_HUD_USER     = (& $Python -c "from nougen_shards import keymaker as k; print(k.get_secret('NGS_HUD_USER') or '')" | Select-Object -Last 1).Trim()
        $env:NGS_HUD_PASSWORD = (& $Python -c "from nougen_shards import keymaker as k; print(k.get_secret('NGS_HUD_PASSWORD') or '')" | Select-Object -Last 1).Trim()

        $proc = Start-Process -FilePath $Python -ArgumentList 'app.py' `
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
            "node up  pid $($proc.Id)  $BaseUrl  shards=$($h.total_shards)  token_configured=$($h.node_token_configured)"
        } else {
            "node did NOT answer /health within 15s - see $ErrLog"
            exit 1
        }
        break
    }

    'stop' {
        $running = Get-NodePid
        if (-not $running) { 'node not running'; break }
        Stop-Process -Id $running -Force -Confirm:$false
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        "node stopped (pid $running)"
        break
    }

    'status' {
        $running = Get-NodePid
        try {
            $h = Invoke-RestMethod -Uri "$BaseUrl/health" -TimeoutSec 3
            "UP    pid=$running  $BaseUrl  shards=$($h.total_shards)  token=$($h.node_token_configured)  public_ready=$($h.public_ready)"
        } catch {
            "DOWN  pid=$running  $BaseUrl unreachable"
        }
        break
    }
}

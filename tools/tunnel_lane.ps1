<#
  tunnel_lane.ps1 - attach this host to the shared NouGen shard highway.

  The named Cloudflare tunnel is transport, not storage. Every connector on it
  must serve the same synchronized shard lane before it is started. The tunnel
  token is read from the DPAPI-backed keymaker vault and passed through the
  child environment; it is never printed or placed in the command line.

  Usage:
    .\tools\tunnel_lane.ps1 start
    .\tools\tunnel_lane.ps1 status
    .\tools\tunnel_lane.ps1 stop
    .\tools\tunnel_lane.ps1 token
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'status', 'token')]
    [string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'

$Root       = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$Python     = if (Test-Path $VenvPython) { $VenvPython } else { (Get-Command python -ErrorAction Stop).Source }
$RunDir     = Join-Path $Root '.node'
$PidFile    = Join-Path $RunDir 'tunnel.pid'
$OutLog     = Join-Path $RunDir 'tunnel.out.log'
$ErrLog     = Join-Path $RunDir 'tunnel.err.log'
$VaultDir   = Join-Path $env:USERPROFILE '.nougen\shards'
$SecretsDir = Join-Path $env:USERPROFILE '.nougen\secrets'
$SecretKey  = 'CLOUDFLARED_NGS_TUNNEL_TOKEN'

function Get-Cloudflared {
    $found = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
    foreach ($candidate in @(
        (Join-Path $env:USERPROFILE '.nougen\bin\cloudflared.exe'),
        'C:\Program Files (x86)\cloudflared\cloudflared.exe',
        'C:\Program Files\cloudflared\cloudflared.exe'
    )) {
        if (Test-Path $candidate) { return $candidate }
    }
    throw 'cloudflared is not installed.'
}

function Get-TunnelToken {
    $env:PYTHONPATH = Join-Path $Root 'src'
    $env:NOUGEN_VAULT_DIR = $VaultDir
    $env:NOUGEN_SECRETS_VAULT_DIR = $SecretsDir
    $tok = & $Python -c "from nougen_shards import keymaker as k; print(k.get_secret('$SecretKey') or '')"
    $tok = ($tok | Select-Object -Last 1).Trim()
    if (-not $tok) { throw "$SecretKey not found in the canonical secrets vault." }
    return $tok
}

function Get-TunnelPid {
    if (-not (Test-Path $PidFile)) { return $null }
    $id = (Get-Content $PidFile -Raw).Trim()
    if (-not $id) { return $null }
    try { $p = Get-Process -Id ([int]$id) -ErrorAction Stop } catch { return $null }
    if ($p.ProcessName -ne 'cloudflared') { return $null }
    return [int]$id
}

function Get-Fingerprint([string]$Value) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)))).Replace('-', '').Substring(0, 12).ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

switch ($Action) {
    'token' {
        $token = Get-TunnelToken
        "tunnel token configured (fp=$(Get-Fingerprint $token))"
        break
    }

    'start' {
        $running = Get-TunnelPid
        if ($running) { "tunnel already running (pid $running)"; break }

        $nodeHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:4444/health' -TimeoutSec 5
        if (-not $nodeHealth.node_token_configured -or -not $nodeHealth.substrate.recall_trustworthy) {
            throw 'local shard node is not ready; refusing to attach an inconsistent origin to the highway.'
        }

        if (-not (Test-Path $RunDir)) { New-Item -ItemType Directory -Path $RunDir | Out-Null }
        $cloudflared = Get-Cloudflared
        $token = Get-TunnelToken
        $previousToken = $env:TUNNEL_TOKEN
        try {
            $env:TUNNEL_TOKEN = $token
            $proc = Start-Process -FilePath $cloudflared -ArgumentList 'tunnel --no-autoupdate run' `
                -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
                -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog
        } finally {
            $env:TUNNEL_TOKEN = $previousToken
        }
        Set-Content -Path $PidFile -Value $proc.Id -Encoding utf8
        "tunnel replica started (pid $($proc.Id)); token fp=$(Get-Fingerprint $token)"
        break
    }

    'stop' {
        $running = Get-TunnelPid
        if (-not $running) { 'tunnel not running'; break }
        Stop-Process -Id $running -Force -Confirm:$false
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        "tunnel stopped (pid $running)"
        break
    }

    'status' {
        $running = Get-TunnelPid
        if ($running) { "UP    pid=$running" } else { 'DOWN  no managed tunnel process' }
        break
    }
}

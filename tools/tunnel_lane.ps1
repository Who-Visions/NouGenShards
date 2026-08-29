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
# The named highway tunnel and the quick tunnel (gateway_supervisor.ps1) are two
# distinct processes. They MUST NOT share a pid file: sharing one made this lane
# report UP for whichever cloudflared happened to be alive, so `start` short
# circuited and blade.nougenai.com sat at 530 with nothing bound to it.
$PidName    = if ($env:NGS_TUNNEL_PID_NAME) { $env:NGS_TUNNEL_PID_NAME } else { 'named_tunnel.pid' }
$PidFile    = Join-Path $RunDir $PidName
$OutLog     = Join-Path $RunDir ([IO.Path]::ChangeExtension($PidName, $null) + 'out.log')
$ErrLog     = Join-Path $RunDir ([IO.Path]::ChangeExtension($PidName, $null) + 'err.log')
$NodePort   = if ($env:NGS_PORT) { $env:NGS_PORT } else { '4444' }
$NodeHealth = if ($env:NGS_NODE_HEALTH_URL) { $env:NGS_NODE_HEALTH_URL } else { "http://127.0.0.1:$NodePort/health" }
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

        $health = Invoke-RestMethod -Uri $NodeHealth -TimeoutSec 5
        if (-not $health.node_token_configured) {
            throw "local shard node at $NodeHealth has no node token; refusing to attach it to the highway."
        }
        # substrate/recall_trustworthy was dropped from /health at some point, which
        # made this gate throw unconditionally and kept the highway down. Probe for
        # the field instead of assuming it: enforce it when present, warn when the
        # payload no longer carries it, and let NGS_TUNNEL_REQUIRE_SUBSTRATE=1 make
        # its absence fatal again once the endpoint exposes it.
        $substrate = $health.PSObject.Properties['substrate']
        if ($substrate -and $null -ne $substrate.Value) {
            if (-not $substrate.Value.recall_trustworthy) {
                throw 'local shard node reports recall is not trustworthy; refusing to attach an inconsistent origin to the highway.'
            }
        } elseif ($env:NGS_TUNNEL_REQUIRE_SUBSTRATE -eq '1') {
            throw "health payload from $NodeHealth carries no substrate block and NGS_TUNNEL_REQUIRE_SUBSTRATE=1; refusing to attach."
        } else {
            Write-Warning "health payload from $NodeHealth carries no substrate block; attaching on node_token + ignited status only."
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

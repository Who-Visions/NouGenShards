<#
  Keep the public tunnel's Who-Art connector on Blade's canonical write node.

  Cloudflare's remotely-managed route targets 127.0.0.1:4444 on every replica.
  Who-Art therefore forwards that loopback port over authenticated SSH to
  Blade's loopback node. The local synchronized standby stays on :4445.
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'status')]
    [string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$RunDir = Join-Path $Root '.node'
$PidFile = Join-Path $RunDir 'primary-proxy.pid'
$OutLog = Join-Path $RunDir 'primary-proxy.out.log'
$ErrLog = Join-Path $RunDir 'primary-proxy.err.log'
$BaseUrl = 'http://127.0.0.1:4444'
$Forward = '127.0.0.1:4444:127.0.0.1:4444'

function Get-ProxyPid {
    if (-not (Test-Path $PidFile)) { return $null }
    $id = (Get-Content -Raw -LiteralPath $PidFile).Trim()
    if (-not $id) { return $null }
    try { $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$id" } catch { return $null }
    if (-not $proc -or $proc.Name -notlike 'ssh*' -or
        $proc.CommandLine -notmatch [regex]::Escape($Forward)) { return $null }
    return [int]$id
}

switch ($Action) {
    'start' {
        $running = Get-ProxyPid
        if ($running) { "primary proxy already running (pid $running)"; break }
        if (Get-NetTCPConnection -State Listen -LocalPort 4444 -ErrorAction SilentlyContinue) {
            throw 'port 4444 is already occupied; refusing to shadow the tunnel origin'
        }
        if (-not (Test-Path $RunDir)) { New-Item -ItemType Directory -Path $RunDir | Out-Null }
        $ssh = (Get-Command ssh -ErrorAction Stop).Source
        $args = @(
            '-N', '-T', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
            '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3',
            '-L', $Forward, 'blade'
        )
        $proc = Start-Process -FilePath $ssh -ArgumentList $args -WindowStyle Hidden `
            -PassThru -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog
        Set-Content -LiteralPath $PidFile -Value $proc.Id -Encoding utf8
        $ready = $false
        foreach ($i in 1..30) {
            try {
                $health = Invoke-RestMethod -Uri "$BaseUrl/health" -TimeoutSec 2
                $ready = $health.substrate.recall_trustworthy
                if ($ready) { break }
            } catch { Start-Sleep -Milliseconds 500 }
        }
        if (-not $ready) {
            Stop-Process -Id $proc.Id -Force -Confirm:$false -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $PidFile -ErrorAction SilentlyContinue
            throw "primary proxy failed readiness; see $ErrLog"
        }
        "primary proxy up (pid $($proc.Id), shards=$($health.total_shards))"
        break
    }

    'stop' {
        $running = Get-ProxyPid
        if (-not $running) { 'primary proxy not running'; break }
        Stop-Process -Id $running -Force -Confirm:$false
        Remove-Item -LiteralPath $PidFile -ErrorAction SilentlyContinue
        "primary proxy stopped (pid $running)"
        break
    }

    'status' {
        $running = Get-ProxyPid
        if (-not $running) { 'DOWN  primary proxy not running'; break }
        try {
            $health = Invoke-RestMethod -Uri "$BaseUrl/health" -TimeoutSec 3
            "UP    pid=$running shards=$($health.total_shards) trust=$($health.substrate.recall_trustworthy)"
        } catch {
            "DOWN  pid=$running primary unreachable"
        }
        break
    }
}

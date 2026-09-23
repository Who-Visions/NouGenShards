<#
.SYNOPSIS
  Keep the local Ollama API actually serving on 11434, across reboots.

.WHY
  On 2026-09-23 the whole local lane was dark on WhoArt: the tray process
  `ollama app` (PID 5796) was running, so every process-based check said Ollama
  was fine, but nothing was listening on 11434. /api/tags threw WebException,
  `coach check` reported ollama:false, and two separate agent sessions each
  burned time concluding "local models are unavailable" and reaching for a paid
  cloud route -- which Rule 0.3 forbids.

  The lesson is the invariant this script enforces: A RUNNING TRAY PROCESS IS NOT
  EVIDENCE THE API IS UP. Probe the port, never the process name.

.NOTES
  Idempotent and safe to run on a schedule. Takes no action when the API answers.
  Exits non-zero only when it tried to start the server and the port still did
  not come up -- so a scheduled-task "last result" of 0 genuinely means healthy.
#>
[CmdletBinding()]
param(
    [int]    $Port         = 11434,
    [int]    $TimeoutSec   = 4,
    [int]    $StartWaitSec = 30,
    [string] $LogPath      = "$env:USERPROFILE\.nougen\ollama_guard.log",
    [switch] $Quiet
)

$ErrorActionPreference = 'Stop'

function Write-Log {
    param([string]$Level, [string]$Message)
    # Store UTC (fleet convention); render Eastern for Dave when read back.
    $line = '{0} [{1}] {2}' -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $Level, $Message
    try {
        $dir = Split-Path -Parent $LogPath
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        Add-Content -Path $LogPath -Value $line -Encoding utf8
    } catch { }
    if (-not $Quiet) { Write-Output $line }
}

function Test-OllamaApi {
    # The ONLY honest health check: a real HTTP response from the API.
    # Not Get-Process, not Test-NetConnection alone -- a listening socket that
    # never answers would still fail every real caller.
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/tags" -TimeoutSec $TimeoutSec
        return @{ Up = $true; Models = @($r.models).Count }
    } catch {
        return @{ Up = $false; Models = 0 }
    }
}

function Get-OllamaExe {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @(
        "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
        "$env:ProgramFiles\Ollama\ollama.exe"
    )) { if (Test-Path $p) { return $p } }
    return $null
}

$probe = Test-OllamaApi
if ($probe.Up) {
    Write-Log 'OK' "api healthy on $Port ($($probe.Models) models); no action"
    exit 0
}

$exe = Get-OllamaExe
if (-not $exe) {
    Write-Log 'FAIL' 'ollama.exe not found -- cannot start. Is Ollama installed?'
    exit 2
}

Write-Log 'WARN' "api DOWN on $Port (tray process presence is irrelevant); starting: $exe serve"
try {
    Start-Process -FilePath $exe -ArgumentList 'serve' -WindowStyle Hidden
} catch {
    Write-Log 'FAIL' "start threw: $($_.Exception.Message)"
    exit 3
}

$deadline = (Get-Date).AddSeconds($StartWaitSec)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 700
    $probe = Test-OllamaApi
    if ($probe.Up) {
        Write-Log 'RECOVERED' "api up on $Port ($($probe.Models) models)"
        exit 0
    }
}

Write-Log 'FAIL' "started serve but api did not answer on $Port within ${StartWaitSec}s"
exit 4

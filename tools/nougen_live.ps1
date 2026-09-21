<#
  nougen_live.ps1 - one front door for this box's LIVE local lanes.

  Lanes covered:
    shard node   127.0.0.1:4444   (delegated to node_lane.ps1)
    msg bus      127.0.0.1:8766   (tools/nougenmsg_node.py - NouGenMsg receiver)
    cc-msg       \\.\pipe\LOCAL\cc-msg-*   (READ ONLY - see note below)
    codex pipe   (delegated to start_codex_pipe.ps1, needs a thread id)

  cc-msg pipes are created by the Claude Code sessions themselves, not by this
  script. "allow incoming" for cc-msg means a live session is running with its
  pipe open - this script can report the pipes, it cannot conjure one. Starting
  the msg bus IS the part that makes this box addressable from other nodes.

  Local only. This never starts a tunnel, deploys a Worker, or touches any
  billed cloud service (GM billing directive: services stay OFF unless asked).

  Usage:
    .\tools\nougen_live.ps1              # status (default, changes nothing)
    .\tools\nougen_live.ps1 start
    .\tools\nougen_live.ps1 stop
    .\tools\nougen_live.ps1 peers        # discovered pipes + reachable nodes
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet('status', 'start', 'stop', 'peers')]
    [string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'

$Root       = Split-Path -Parent $PSScriptRoot              # ...\Outpost\NouGen
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
if (Test-Path $VenvPython) { $Python = $VenvPython } else { $Python = (Get-Command python -ErrorAction Stop).Source }

$RunDir   = Join-Path $Root '.node'
$LogDir   = Join-Path $env:USERPROFILE '.nougen\logs'
$MsgNode  = Join-Path $PSScriptRoot 'nougenmsg_node.py'
$NodeLane = Join-Path $PSScriptRoot 'node_lane.ps1'
$MsgPid   = Join-Path $RunDir 'msgnode.pid'

if ($env:NOUGEN_AGY_MSG_PORT) { $MsgPort = $env:NOUGEN_AGY_MSG_PORT } else { $MsgPort = '8766' }
if ($env:NGS_PORT)            { $NodePort = $env:NGS_PORT }            else { $NodePort = '4444' }

function Test-Listening {
    param([int]$Port)
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        return [bool]$conn
    } catch {
        return $false
    }
}

function Get-CcMsgPipes {
    # Enumerating \\.\pipe\ is the only reliable discovery path on Windows.
    try {
        return @([System.IO.Directory]::GetFiles('\\.\pipe\') | Where-Object { $_ -match 'cc-msg|claude' })
    } catch {
        return @()
    }
}

function Get-TrackedProcess {
    # Returns the process ONLY if the pid file points at something that is
    # still genuinely our script - a recycled pid must never be killed.
    param([string]$PidFile, [string]$MustContain)
    if (-not (Test-Path -LiteralPath $PidFile)) { return $null }
    $raw = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    $procId = 0
    if (-not [int]::TryParse($raw, [ref]$procId)) { return $null }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $procId" -ErrorAction SilentlyContinue
    if (-not $proc) { return $null }
    if (-not $proc.CommandLine -or -not $proc.CommandLine.Contains($MustContain)) { return $null }
    return $proc
}

function Show-Status {
    Write-Output ''
    Write-Output "NouGen live lanes - $env:COMPUTERNAME  ($(Get-Date -Format 'h:mm tt') local)"
    Write-Output ('-' * 62)

    if (Test-Listening -Port ([int]$NodePort)) { $nodeState = "LISTENING" } else { $nodeState = "down" }
    Write-Output ("  shard node   127.0.0.1:{0,-6} {1}" -f $NodePort, $nodeState)

    if (Test-Listening -Port ([int]$MsgPort)) { $msgState = "LISTENING" } else { $msgState = "down" }
    $msgProc = Get-TrackedProcess -PidFile $MsgPid -MustContain 'nougenmsg_node.py'
    if ($msgProc) { $msgState = "$msgState (pid $($msgProc.ProcessId))" }
    Write-Output ("  msg bus      127.0.0.1:{0,-6} {1}" -f $MsgPort, $msgState)

    $pipes = Get-CcMsgPipes
    Write-Output ("  cc-msg       {0} pipe(s) open" -f $pipes.Count)
    foreach ($p in $pipes) { Write-Output "                 - $p" }

    Write-Output ''
    if ($msgState -like 'down*') {
        Write-Output "  incoming from other nodes: BLOCKED (msg bus down) - run: .\tools\nougen_live.ps1 start"
    } else {
        # Listening is not reachable: a 127.0.0.1 bind refuses every LAN peer.
        $binds = @(Get-NetTCPConnection -LocalPort ([int]$MsgPort) -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty LocalAddress -Unique)
        $lanBind = $binds | Where-Object { $_ -ne '127.0.0.1' -and $_ -ne '::1' }
        if ($lanBind) {
            Write-Output ("  incoming from other nodes: OPEN on LAN (bind {0})" -f ($binds -join ', '))
        } else {
            Write-Output "  incoming from other nodes: LOCAL ONLY (bind 127.0.0.1) - LAN peers are refused;"
            Write-Output "    they reach this box via ssh fallback. Do not rebind to 0.0.0.0 while auth=open(unlatched)."
        }
    }
    Write-Output ''
}

function Start-Lanes {
    New-Item -ItemType Directory -Path $RunDir -Force | Out-Null
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

    $existing = Get-TrackedProcess -PidFile $MsgPid -MustContain 'nougenmsg_node.py'
    if ($existing) {
        Write-Output "  msg bus already up (pid $($existing.ProcessId)) - leaving it alone."
    } elseif (Test-Listening -Port ([int]$MsgPort)) {
        # Something else holds the port. Do not fight it, do not kill it.
        Write-Output "  port $MsgPort is already in use by a process this script did not start."
        Write-Output "  Refusing to start a second receiver. Investigate before forcing."
    } else {
        if (-not (Test-Path -LiteralPath $MsgNode)) { throw "Receiver missing: $MsgNode" }
        $proc = Start-Process -FilePath $Python `
            -ArgumentList @(('"' + $MsgNode + '"')) `
            -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $LogDir 'msgnode.stdout.log') `
            -RedirectStandardError  (Join-Path $LogDir 'msgnode.stderr.log')
        Set-Content -LiteralPath $MsgPid -Value $proc.Id -Encoding ascii

        $ready = $false
        for ($i = 0; $i -lt 40; $i++) {
            Start-Sleep -Milliseconds 150
            if ($proc.HasExited) { throw "msg bus exited on startup; see $LogDir\msgnode.stderr.log" }
            if (Test-Listening -Port ([int]$MsgPort)) { $ready = $true; break }
        }
        if ($ready) {
            Write-Output "  msg bus up on 127.0.0.1:$MsgPort (pid $($proc.Id))"
        } else {
            throw "msg bus did not begin listening on $MsgPort; see $LogDir\msgnode.stderr.log"
        }
    }

    if (Test-Listening -Port ([int]$NodePort)) {
        Write-Output "  shard node already listening on $NodePort."
    } elseif (Test-Path -LiteralPath $NodeLane) {
        Write-Output "  shard node is down. Start it deliberately:  .\tools\node_lane.ps1 start"
    }

    Show-Status
}

function Stop-Lanes {
    $proc = Get-TrackedProcess -PidFile $MsgPid -MustContain 'nougenmsg_node.py'
    if (-not $proc) {
        Write-Output "  no msg bus started by this script is running; nothing to stop."
        Write-Output "  (a receiver started another way is left untouched on purpose)"
        return
    }
    Stop-Process -Id $proc.ProcessId
    Remove-Item -LiteralPath $MsgPid -ErrorAction SilentlyContinue
    Write-Output "  msg bus stopped (pid $($proc.ProcessId)). Inbox files are preserved."
    Write-Output "  shard node left running - stop it with .\tools\node_lane.ps1 stop if you meant to."
}

function Show-Peers {
    $env:PYTHONPATH = Join-Path $Root 'src'
    $peers = Join-Path $Root '..\NouGenMsg\tools\nougenmsg.py'
    if (Test-Path -LiteralPath $peers) {
        & $Python $peers --peers
    } else {
        Write-Output "  NouGenMsg CLI not found at $peers"
        $pipes = Get-CcMsgPipes
        Write-Output ("  cc-msg pipes: {0}" -f $pipes.Count)
        foreach ($p in $pipes) { Write-Output "    - $p" }
    }
}

switch ($Action) {
    'status' { Show-Status }
    'start'  { Start-Lanes }
    'stop'   { Stop-Lanes }
    'peers'  { Show-Peers }
}

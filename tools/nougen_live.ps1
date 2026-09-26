<#
  nougen_live.ps1 - one front door for this box's LIVE local lanes.

  Lanes covered:
    shard node   127.0.0.1:4444   (delegated to node_lane.ps1)
    msg bus      127.0.0.1:8766   (tools/nougenmsg_node.py - NouGenMsg receiver)
    ollama       OLLAMA_HOST or 127.0.0.1:11434 (ensured + model warmed on start)
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

# --- Ollama lane (native to live startup) -----------------------------------
# Endpoint/model resolve env -> probe; constants are logged fallbacks only.
if ($env:OLLAMA_HOST) {
    $OllamaBase = $env:OLLAMA_HOST
    if ($OllamaBase -notmatch '^https?://') { $OllamaBase = 'http://' + $OllamaBase }
    $OllamaBase = $OllamaBase.TrimEnd('/')
    $OllamaBase = $OllamaBase -replace '://0\.0\.0\.0', '://127.0.0.1'
    if ($OllamaBase -notmatch '://[^/]+:\d+') {
        $OllamaBase = $OllamaBase + ':11434'   # ollama's documented default port
        Write-Verbose "OLLAMA_HOST has no port; fallback $OllamaBase"
    }
} else {
    $OllamaBase = 'http://127.0.0.1:11434'
    Write-Verbose "OLLAMA_HOST unset; fallback $OllamaBase"
}
if ($env:NOUGEN_OLLAMA_WAIT_S) { $OllamaWaitS = [int]$env:NOUGEN_OLLAMA_WAIT_S } else { $OllamaWaitS = 60 }
# Custom fleet families (Rule 0.4). Override with NOUGEN_FLEET_MODELS=a,b,c
if ($env:NOUGEN_FLEET_MODELS) { $FleetFamilies = $env:NOUGEN_FLEET_MODELS.Split(',') | ForEach-Object { $_.Trim().ToLower() } }
else { $FleetFamilies = @('dav1d', 'sol-ai', 'kaedra', 'iris-ai', 'rhea-noir', 'griot', 'davos', 'mrs-b') }

function Get-OllamaTags {
    try {
        $r = Invoke-RestMethod -Uri "$OllamaBase/api/tags" -TimeoutSec 5 -ErrorAction Stop
        return @($r.models | ForEach-Object { $_.name })
    } catch { return $null }
}

function Test-ModelAllowed {
    param([string]$Name)
    $n = $Name.ToLower()
    if ($n -match '(^|[:\-])(12b|27b|31b)') { return $false }   # banned class
    if ($n -match '-cloud$|:cloud') { return $false }
    if ($n -match 'embed') { return $false }
    return $true
}

function Select-OllamaModel {
    param([string[]]$Tags)
    if (-not $Tags) { return $null }
    $pref = $env:NOUGEN_OLLAMA_MODEL
    if ($pref -and ($Tags -contains $pref) -and (Test-ModelAllowed $pref)) { return $pref }
    $custom = @($Tags | Where-Object {
        (Test-ModelAllowed $_) -and ($FleetFamilies -contains ($_.Split(':')[0].ToLower())) -and ($_ -notmatch '-prev$|-pre-')
    })
    $small = @($custom | Where-Object { $_ -match ':(e2b|e4b)$' })
    if ($small) { return ($small | Sort-Object { $FleetFamilies.IndexOf($_.Split(':')[0].ToLower()) })[0] }
    if ($custom) { return ($custom | Sort-Object { $FleetFamilies.IndexOf($_.Split(':')[0].ToLower()) })[0] }
    $g = @($Tags | Where-Object { $_ -match '^gemma4:(e2b|e4b)' })
    if ($g) { return $g[0] }
    return $null
}

function Start-OllamaLane {
    $tags = Get-OllamaTags
    if ($null -ne $tags) {
        Write-Output "  ollama already serving at $OllamaBase ($($tags.Count) tags) - leaving it alone."
    } else {
        $exe = $env:NOUGEN_OLLAMA_EXE
        if (-not $exe) { $cmd = Get-Command ollama -ErrorAction SilentlyContinue; if ($cmd) { $exe = $cmd.Source } }
        if (-not $exe) {
            $exe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
            Write-Output "  ollama not on PATH; fallback $exe"
        }
        if (-not (Test-Path -LiteralPath $exe)) { Write-Output "  ollama: executable not found ($exe) - lane DOWN"; return }
        # No duplicate servers: if a 'serve' is already running but not yet answering, wait for it.
        $serving = @(Get-CimInstance Win32_Process -Filter "Name = 'ollama.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match '\bserve\b' })
        if ($serving) {
            Write-Output "  ollama serve already running (pid $($serving[0].ProcessId)); waiting for it."
        } else {
            Start-Process -FilePath $exe -ArgumentList 'serve' -WindowStyle Hidden `
                -RedirectStandardOutput (Join-Path $LogDir 'ollama.stdout.log') `
                -RedirectStandardError  (Join-Path $LogDir 'ollama.stderr.log') | Out-Null
            Write-Output "  ollama serve started hidden."
        }
        $deadline = (Get-Date).AddSeconds($OllamaWaitS)
        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Milliseconds 500
            $tags = Get-OllamaTags
            if ($null -ne $tags) { break }
        }
        if ($null -eq $tags) { Write-Output "  ollama: /api/tags not answering after ${OllamaWaitS}s - lane DOWN"; return }
        Write-Output "  ollama up at $OllamaBase ($($tags.Count) tags)."
    }
    $model = Select-OllamaModel -Tags $tags
    if (-not $model) { Write-Output "  ollama: no allowed custom/gemma4 e2b|e4b model served - warm skipped."; return }
    try {
        $body = @{ model = $model; prompt = 'ok'; stream = $false; options = @{ num_predict = 1 } } | ConvertTo-Json -Compress
        $sw = [Diagnostics.Stopwatch]::StartNew()
        Invoke-RestMethod -Uri "$OllamaBase/api/generate" -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 180 -ErrorAction Stop | Out-Null
        Write-Output ("  ollama model warm: {0} ({1:N1}s)" -f $model, $sw.Elapsed.TotalSeconds)
    } catch {
        Write-Output "  ollama model warm FAILED for ${model}: $($_.Exception.Message)"
    }
}

function Show-OllamaStatus {
    $tags = Get-OllamaTags
    if ($null -eq $tags) { Write-Output ("  ollama       {0,-22} down" -f $OllamaBase); return }
    $loaded = @()
    try { $loaded = @((Invoke-RestMethod -Uri "$OllamaBase/api/ps" -TimeoutSec 5).models | ForEach-Object { $_.name }) } catch { }
    Write-Output ("  ollama       {0,-22} UP ({1} tags) pick={2} loaded=[{3}]" -f $OllamaBase, $tags.Count, (Select-OllamaModel -Tags $tags), ($loaded -join ', '))
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
    Show-OllamaStatus

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

function Set-MsgAuthEnv {
    # A LAN bind with no token lets any peer POST /msg or drain GET /pop. When
    # the bind is not loopback, resolve the token from keymaker into THIS
    # process env only (Start-Process inherits it; it is never persisted or
    # printed) and latch auth. The latch is set even if the token does not
    # resolve: the receiver then refuses mutations instead of silently
    # accepting everyone (fail closed - see AUTH_LATCH in nougenmsg_node.py).
    $bind = $env:NOUGEN_AGY_MSG_BIND
    if (-not $bind -or $bind -eq '127.0.0.1' -or $bind -eq '::1') { return }
    $env:NOUGEN_AGY_MSG_AUTH = '1'
    if ($env:NOUGEN_AGY_MSG_TOKEN) { return }
    $code = "import sys; sys.path.insert(0, r'$Root\src'); from nougen_shards import keymaker; sys.stdout.write((keymaker.get_secret('NOUGEN_AGY_MSG_TOKEN') or '').strip())"
    try { $tok = & $Python -c $code 2>$null } catch { $tok = '' }
    if ($tok) {
        $env:NOUGEN_AGY_MSG_TOKEN = "$tok".Trim()
        Write-Output "  msg bus auth: token resolved from keymaker, latched."
    } else {
        Write-Output "  msg bus auth: LATCHED WITHOUT TOKEN (keymaker miss) - LAN mutations will be refused."
    }
}

function Start-Lanes {
    New-Item -ItemType Directory -Path $RunDir -Force | Out-Null
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

    if ($env:NOUGEN_LIVE_SKIP_OLLAMA -ne '1') { Start-OllamaLane }

    $existing = Get-TrackedProcess -PidFile $MsgPid -MustContain 'nougenmsg_node.py'
    if ($existing) {
        Write-Output "  msg bus already up (pid $($existing.ProcessId)) - leaving it alone."
    } elseif (Test-Listening -Port ([int]$MsgPort)) {
        # Something else holds the port. Do not fight it, do not kill it.
        Write-Output "  port $MsgPort is already in use by a process this script did not start."
        Write-Output "  Refusing to start a second receiver. Investigate before forcing."
    } else {
        if (-not (Test-Path -LiteralPath $MsgNode)) { throw "Receiver missing: $MsgNode" }
        Set-MsgAuthEnv
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
    # Ollama is shared by every lane on this box; stop reports it, never kills it.
    Show-OllamaStatus
    Write-Output "  ollama left running (shared by other lanes) - quit it from the tray if you meant to."
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

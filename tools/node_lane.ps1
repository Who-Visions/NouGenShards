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

function Get-NodeToken {
    $env:PYTHONPATH = Join-Path $Root 'src'
    $env:NOUGEN_VAULT_DIR = $VaultDir
    $env:NOUGEN_SECRETS_VAULT_DIR = $SecretsDir
    $tok = & $Python -c "from nougen_shards import keymaker as k; print(k.get_secret('$SecretKey') or '')"
    $tok = ($tok | Select-Object -Last 1).Trim()
    if (-not $tok) { throw "$SecretKey not found in the canonical secrets vault. Ingest the shared lane token before starting." }
    return $tok
}

function Set-RheaLaneEnv {
    # Fill OPENROUTER_API_KEY and NGS_INFERENCE_TOKENS from the keymaker when
    # the operator has not set them. Label and patterns are env-overridable
    # (same knobs as start_grid.py); the store path follows NOUGEN_SECRETS_DB.
    if ($env:OPENROUTER_API_KEY -and $env:NGS_INFERENCE_TOKENS) { 'rhea lanes: both set by env'; return }
    $env:PYTHONPATH = Join-Path $Root 'src'
    $py = @'
import os, sys
from pathlib import Path
home = Path(os.environ.get("NOUGEN_ROOT") or (Path.home() / ".nougen"))
sys.path.insert(0, str(home / "bin"))
import keymaker_peel as kp
db = Path(os.environ.get("NOUGEN_SECRETS_DB") or (home / "secrets" / "shards_secrets.db"))
out = []
if not os.environ.get("OPENROUTER_API_KEY"):
    try:
        # OPENROUTER_KEY_NOUGENAI (start_grid.py's default) exists in neither
        # blade store; OPENROUTER_API_KEY is the label actually ingested.
        rows = kp.load(os.environ.get("NOUGEN_OPENROUTER_KEY_LABEL", "OPENROUTER_API_KEY"), db=db)
    except Exception as exc:
        rows = []
        print(f"rhea free lane: keymaker lookup failed ({type(exc).__name__})", file=sys.stderr)
    if rows:
        label, value, _ = rows[0]
        out.append("OPENROUTER_API_KEY=" + value)
        print(f"rhea free lane: openrouter key {label} fp={kp.fingerprint(value)}", file=sys.stderr)
    else:
        print("rhea free lane: no openrouter key found (agent lane degraded)", file=sys.stderr)
if not os.environ.get("NGS_INFERENCE_TOKENS"):
    toks = {}
    pats = [p for p in os.environ.get("NOUGEN_HF_TOKEN_PATTERNS", "%HF_%,%HUGGING%").split(",") if p]
    for pat in pats:
        for store in (db, None):
            try:
                rows = kp.load(pat, db=store, min_len=20)
            except Exception:
                continue
            for _label, value, _rot in rows:
                if value.startswith("hf_"):
                    toks[kp.fingerprint(value)] = value
    if toks:
        out.append("NGS_INFERENCE_TOKENS=" + ",".join(toks.values()))
        print(f"rhea kimi lane: {len(toks)} fleet hf token(s) wired", file=sys.stderr)
    else:
        print("rhea kimi lane: no hf tokens found", file=sys.stderr)
sys.stdout.write("\n".join(out))
'@
    # Feed the script over stdin: a multi-line `-c` argument is re-quoted by
    # PowerShell's native-command marshalling and reached Python mangled
    # (SyntaxError, 2026-10-29). Fingerprint lines arrive on stderr; under
    # $ErrorActionPreference='Stop' they would abort the start, so relax it
    # for this call only - a missing key degrades Rhea, it must not stop the node.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $lines = $py | & $Python - 2>&1 } finally { $ErrorActionPreference = $prevEap }
    foreach ($line in $lines) {
        $s = ([string]$line).TrimStart([char]0xFEFF)
        if ($s -match '^(OPENROUTER_API_KEY|NGS_INFERENCE_TOKENS)=(.+)$') {
            Set-Item -Path ("Env:" + $Matches[1]) -Value $Matches[2]
        } elseif ($line -is [System.Management.Automation.ErrorRecord] -and $s) {
            # Echo stderr only (fingerprints / counts). A stdout line that misses
            # the regex is dropped, never printed: it could carry a value.
            $s
        }
    }
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
        $running = Get-NodePid
        $listener = Get-ListenerPid
        if ($listener) { "node already running (listener pid $listener) on $BaseUrl"; break }
        if ($running) {
            # A launcher with no listener yet is usually still importing/warming
            # (~120s on blade). Killing it restarted the warm-up every time this
            # ran on a timer: 2026-09-24 blade churned ~20 minutes after one
            # restart. Spare it inside the warm-up window; only replace a
            # launcher that has had its full window and still is not listening.
            $warmS = if ($env:NGS_NODE_WARMUP_S) { [int]$env:NGS_NODE_WARMUP_S } else { 300 }
            $age = [int]((Get-Date) - (Get-Process -Id $running).StartTime).TotalSeconds
            if ($age -lt $warmS) { "node warming up (launcher pid $running, ${age}s of ${warmS}s); not restarting"; break }
            Stop-Process -Id $running -Force -Confirm:$false -ErrorAction SilentlyContinue
            Remove-Item $PidFile -ErrorAction SilentlyContinue
        }

        # Synchronize with start_grid.py via shared cross-process lock (Defect O6)
        $lockFile = if ($env:NOUGEN_NODE_LOCK) {
            $env:NOUGEN_NODE_LOCK
        } else {
            Join-Path $env:USERPROFILE '.nougen\bin\node_lane.lock'
        }
        $lockDir = Split-Path -Parent $lockFile
        if (-not (Test-Path $lockDir)) { New-Item -ItemType Directory -Path $lockDir -Force | Out-Null }
        
        $lockStream = $null
        try {
            $lockStream = [System.IO.File]::Open($lockFile, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
        } catch {
            "another launcher is currently starting the node (lock held at $lockFile); standing down"
            break
        }

        try {
            # Re-check listener inside the lock
            $listener = Get-ListenerPid
            if ($listener) { "node already running (listener pid $listener) on $BaseUrl"; break }

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
        # Recall latency bounds (2026-09-20): a query embed stalled by GPU contention with a
        # resident generation model burned the full 6s default and a matrix-build wait burned 5s.
        if (-not $env:NOUGEN_QUERY_EMBED_TIMEOUT)   { $env:NOUGEN_QUERY_EMBED_TIMEOUT   = '2.5' }
        if (-not $env:NOUGEN_VECTOR_CACHE_WAIT_S)   { $env:NOUGEN_VECTOR_CACHE_WAIT_S   = '1' }
        # Rhea's inference lanes (2026-10-29): a node started here carried no
        # OPENROUTER_API_KEY / NGS_INFERENCE_TOKENS, so rhea_noir raised "no
        # inference lane available (free + kimi both down)" and ask_xoah came
        # back brain=none. start_grid.py already wires both from the keymaker;
        # mirror it so the two launchers agree. Env wins; values travel
        # python -> this process -> child env, same as Get-NodeToken, and only
        # fingerprints/counts are ever printed.
        Set-RheaLaneEnv
        $env:PYTHONPATH       = Join-Path $Root 'src'

        $proc = Start-Process -FilePath $Python -ArgumentList 'tools\ngs_node_serve.py' `
            -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog
        Set-Content -Path $PidFile -Value $proc.Id -Encoding utf8

        # Uvicorn + gradio import plus recall warm-up can take two minutes
        # (2026-09-14 on blade: ~40s warm-up, ~120s to the first /health 200), so
        # the old fixed 15s gate reported healthy starts as failures. Poll until
        # a deadline taken from env, and stop early if the node process dies.
        $WaitS = 180
        $waitSource = 'fallback'
        if ($env:NGS_HEALTH_WAIT_S) { $WaitS = [int]$env:NGS_HEALTH_WAIT_S; $waitSource = 'NGS_HEALTH_WAIT_S' }
        $deadline = (Get-Date).AddSeconds($WaitS)
        $ready = $false
        while ((Get-Date) -lt $deadline) {
            if ($proc.HasExited) { break }
            try {
                $h = Invoke-RestMethod -Uri "$BaseUrl/health" -TimeoutSec 2
                $ready = $true
                break
            } catch { Start-Sleep -Seconds 1 }
        }
        if ($ready) {
            "node up  pid $($proc.Id)  $BaseUrl  shards=$($h.total_shards)  token_configured=$($h.node_token_configured)"
        } elseif ($proc.HasExited) {
            "node process exited (code $($proc.ExitCode)) before answering /health - see $ErrLog"
            exit 1
        } else {
            "node did NOT answer /health within ${WaitS}s (wait source: $waitSource) - see $ErrLog"
            exit 1
        }
        } finally {
            if ($lockStream) {
                $lockStream.Close()
                $lockStream.Dispose()
            }
        }
        break
    }

    'stop' {
        # Stop EVERY uvicorn listener on the port and its ngs_node_serve launcher.
        # 2026-10-13: two listeners shared 4444 (one from 10/12); stopping only the
        # first left the stale one serving old code after a "successful" restart.
        $running = Get-NodePid
        $stopped = @()
        $conns = Get-NetTCPConnection -State Listen -LocalPort ([int]$Port) -ErrorAction SilentlyContinue
        foreach ($owner in ($conns | Select-Object -ExpandProperty OwningProcess -Unique)) {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$owner"
            if (-not $proc -or $proc.Name -notlike 'python*' -or $proc.CommandLine -notmatch '-m uvicorn app:app') {
                throw "port $Port is owned by an unexpected process (pid $owner); refusing to manage it"
            }
            $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.ParentProcessId)"
            Stop-Process -Id $owner -Force -Confirm:$false -ErrorAction SilentlyContinue
            $stopped += $owner
            if ($parent -and $parent.CommandLine -match 'ngs_node_serve\.py') {
                Stop-Process -Id $parent.ProcessId -Force -Confirm:$false -ErrorAction SilentlyContinue
                $stopped += $parent.ProcessId
            }
        }
        if ($running -and ($stopped -notcontains $running)) {
            Stop-Process -Id $running -Force -Confirm:$false -ErrorAction SilentlyContinue
            $stopped += $running
        }
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        if (-not $stopped) { 'node not running'; break }
        $deadline = (Get-Date).AddSeconds(15)
        while ((Get-Date) -lt $deadline -and (Get-NetTCPConnection -State Listen -LocalPort ([int]$Port) -ErrorAction SilentlyContinue)) { Start-Sleep -Milliseconds 500 }
        if (Get-NetTCPConnection -State Listen -LocalPort ([int]$Port) -ErrorAction SilentlyContinue) {
            "node stop INCOMPLETE: port $Port still has a listener after stopping $($stopped -join ',')"
            exit 1
        }
        "node stopped (pids $($stopped -join ','))"
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

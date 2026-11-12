<#
NouGen tenant nodes on this computer: status and safe restarts.

  powershell -NoProfile -ExecutionPolicy Bypass -File nodes.ps1 status
  ... nodes.ps1 restart-supervisor     # restart the Go supervisor detached from any shell (via WMI)
  ... nodes.ps1 restart <name>         # stop one node (root or an account handle); the supervisor restarts it
  ... nodes.ps1 log [lines]            # tail the supervisor log

Nodes are discovered the same way the supervisor does it: %LOCALAPPDATA%\NouGen\run.ps1 and
%LOCALAPPDATA%\NouGen\<handle>\run.ps1 (port from NGS_PORT), with public.txt holding the URL.
Never prints tokens.
#>
param([Parameter(Position = 0)][string]$Command = 'status', [Parameter(Position = 1)][string]$Arg)

$H = Join-Path $env:LOCALAPPDATA 'NouGen'
$Exe = Join-Path $H 'nougen-supervisor.exe'

function Get-Nodes {
    $files = @(Join-Path $H 'run.ps1') + @(Get-ChildItem $H -Directory | ForEach-Object { Join-Path $_.FullName 'run.ps1' })
    foreach ($f in $files) {
        if (-not (Test-Path $f)) { continue }
        $t = Get-Content -Raw $f
        if ($t -notmatch "NGS_PORT\s*=\s*'(\d+)'") { continue }
        $port = [int]$Matches[1]
        $dir = Split-Path $f
        $name = if ($dir -eq $H) { 'root' } else { Split-Path $dir -Leaf }
        $pubFile = Join-Path $dir 'public.txt'
        $pub = if (Test-Path $pubFile) { (Get-Content $pubFile -Raw).Trim().TrimEnd('/') } else { '' }
        [pscustomobject]@{ Name = $name; Port = $port; Public = $pub }
    }
}

function Test-Url($u) {
    try { (Invoke-WebRequest -UseBasicParsing $u -TimeoutSec 8).StatusCode -eq 200 } catch { $false }
}

function Start-SupervisorDetached {
    # WMI starts it outside the caller's job object, so closing Claude/a terminal can't kill it.
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = "`"$Exe`""; CurrentDirectory = $H }
    "supervisor started (pid $($r.ProcessId))"
}

switch ($Command) {
    'status' {
        $sup = Get-Process nougen-supervisor -ErrorAction SilentlyContinue
        $ver = try { (Invoke-RestMethod 'http://127.0.0.1:4499/status' -TimeoutSec 3).version } catch { '?' }
        "supervisor: " + $(if ($sup) { "running (pid $($sup.Id -join ','), version $ver)" } else { 'NOT running' })
        $run = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -ErrorAction SilentlyContinue).'NouGen-Supervisor'
        "autostart:  " + $(if ($run) { 'on' } else { 'OFF' })
        foreach ($n in Get-Nodes) {
            $l = if (Test-Url "http://127.0.0.1:$($n.Port)/health") { 'up' } else { 'DOWN' }
            $p = if ($n.Public) { if (Test-Url "$($n.Public)/health") { 'up' } else { 'DOWN' } } else { 'n/a' }
            "{0,-8} port {1}  local {2,-4}  public {3,-4}  {4}" -f $n.Name, $n.Port, $l, $p, $n.Public
        }
    }
    'restart-supervisor' {
        Get-Process nougen-supervisor -ErrorAction SilentlyContinue | Stop-Process -Force
        Start-Sleep 1
        Start-SupervisorDetached
    }
    'restart' {
        $n = Get-Nodes | Where-Object Name -eq $Arg
        if (-not $n) { "unknown node '$Arg' (try: $((Get-Nodes).Name -join ', '))"; exit 1 }
        $c = Get-NetTCPConnection -State Listen -LocalPort $n.Port -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($c) { Stop-Process -Id $c.OwningProcess -Force; "stopped $Arg (pid $($c.OwningProcess)); the supervisor restarts it within ~1 min" }
        else { "$Arg wasn't running; the supervisor will start it" }
        if (-not (Get-Process nougen-supervisor -ErrorAction SilentlyContinue)) { Start-SupervisorDetached }
    }
    'log' {
        $lines = if ($Arg) { [int]$Arg } else { 20 }
        Get-Content (Join-Path $H 'supervisor.log') -Tail $lines
    }
    default { "usage: nodes.ps1 status | restart-supervisor | restart <name> | log [lines]"; exit 1 }
}

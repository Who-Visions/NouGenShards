# Windows low-disk guard: the Windows twin of tools/launchd/disk_guard.sh (Phoebus).
# Run by the "NouGen Disk Guard" scheduled task every 15 minutes (install with -Install).
#
# Below the threshold (default 20 GB free on the system drive):
#   1. log which folders hold the space (top regenerable caches + user-profile giants),
#   2. clear ONLY caches that rebuild themselves,
#   3. write ~/.nougen/state/disk_guard.json so host_health_gate and lanes can read it.
# Never touches repos, worktrees, models, vaults, shards, secrets or user documents.
#
# Blade hit 100% (0.19 GB free) on 2026-11-19 with no warning; every agent on the box
# stalled. The Phoebus guard already existed; this closes the gap on Windows nodes.
[CmdletBinding()]
param(
    [double]$ThresholdGB = 20,
    [switch]$Install,
    [switch]$DryRun
)
$ErrorActionPreference = 'Continue'
$Home_ = $env:USERPROFILE
$State = Join-Path $Home_ '.nougen\state'
$LogDir = Join-Path $Home_ '.nougen\logs'
New-Item -ItemType Directory -Force -Path $State, $LogDir | Out-Null
$Log = Join-Path $LogDir 'disk_guard.log'
# Keep the log bounded: roll it once it passes 5 MB (one previous copy kept).
if ((Test-Path $Log) -and (Get-Item $Log).Length -gt 5MB) { Move-Item $Log "$Log.1" -Force }

if ($Install) {
    $exe = (Get-Command powershell.exe).Source
    $arg = "-NoProfile -WindowStyle Hidden -ExecutionPolicy RemoteSigned -File `"$PSCommandPath`" -ThresholdGB $ThresholdGB"
    $action = New-ScheduledTaskAction -Execute 'conhost.exe' -Argument "--headless `"$exe`" $arg"
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15)
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName 'NouGen Disk Guard' -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    "installed: NouGen Disk Guard (every 15 min, threshold $ThresholdGB GB)"
    exit 0
}

# Windows\Temp is left out on purpose: the task runs as the installing user, who cannot clear it.
function Get-FreeGB { [math]::Round((Get-PSDrive ($env:SystemDrive.TrimEnd(':')) -ErrorAction Stop).Free / 1GB, 2) }
function Get-SizeGB($p) {
    if (-not (Test-Path $p)) { return 0 }
    [math]::Round(((Get-ChildItem $p -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum) / 1GB, 2)
}

# Caches that rebuild themselves on next use. Nothing here is source, state or user data.
$Caches = @(
    "$Home_\AppData\Local\npm-cache",
    "$Home_\AppData\Local\pip\cache",
    "$Home_\AppData\Local\uv\cache",
    "$Home_\.bun\install\cache",
    "$Home_\AppData\Local\Yarn\Cache",
    "$Home_\.gradle\caches",
    "$Home_\.gradle\daemon",
    "$Home_\.cache\codex-runtimes",
    "$Home_\AppData\Local\CrashDumps",
    "$Home_\AppData\Local\Microsoft\Windows\INetCache"
)

$free = Get-FreeGB
$status = [ordered]@{ checked = (Get-Date).ToString('o'); host = $env:COMPUTERNAME; free_gb = $free; threshold_gb = $ThresholdGB; state = 'ok'; freed_gb = 0; holders = @() }
if ($free -ge $ThresholdGB) {
    $status | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $State 'disk_guard.json') -Encoding utf8
    exit 0
}

$stamp = Get-Date -Format 'yyyy-MM-dd hh:mm tt'
Add-Content $Log "== $stamp free=${free}G (threshold ${ThresholdGB}G)$(if ($DryRun) {' DRY RUN'})"
$holders = foreach ($c in $Caches) { [pscustomobject]@{ path = $c; gb = (Get-SizeGB $c) } }
$holders | Sort-Object gb -Descending | Where-Object gb -gt 0 | ForEach-Object { Add-Content $Log ("   {0,7:N2} GB  {1}" -f $_.gb, $_.path) }

if (-not $DryRun) {
    $failed = 0
    foreach ($c in $Caches) {
        if (Test-Path $c) {
            Get-ChildItem $c -Force -ErrorAction SilentlyContinue | ForEach-Object {
                try { Remove-Item $_.FullName -Recurse -Force -ErrorAction Stop } catch { $failed++ }   # locked files are expected
            }
        }
    }
    # User temp: only files untouched for 2+ days, so running jobs keep their scratch.
    Get-ChildItem $env:TEMP -Recurse -Force -File -ErrorAction SilentlyContinue | Where-Object LastWriteTime -lt (Get-Date).AddDays(-2) | ForEach-Object {
        try { Remove-Item $_.FullName -Force -ErrorAction Stop } catch { $failed++ }
    }
    if ($failed) { Add-Content $Log "   $failed item(s) could not be removed (locked or access denied)" }
}

$after = Get-FreeGB
$status.free_gb = $after
$status.freed_gb = [math]::Round($after - $free, 2)
$status.state = if ($after -lt 5) { 'critical' } elseif ($after -lt $ThresholdGB) { 'low' } else { 'recovered' }
$status.holders = @($holders | Sort-Object gb -Descending | Select-Object -First 8)
Add-Content $Log "   after: free=${after}G freed=$($status.freed_gb)G state=$($status.state)"
$status | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $State 'disk_guard.json') -Encoding utf8

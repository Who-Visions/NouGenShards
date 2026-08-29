<##
  Install/update a lightweight authenticated gateway probe task.

  The task performs one OAuth + MCP recall call on a cadence. It writes
  %USERPROFILE%/.nougen/state/gateway_probe.json and leaves a
  gateway_probe.alert marker on failure; Task Scheduler also records the
  non-zero exit code. No model or GPU is started.
#>
[CmdletBinding()]
param(
    [int]$IntervalMinutes = 5,
    [switch]$Disable
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Probe = Join-Path $PSScriptRoot 'gateway_probe.py'
$Python = if ($env:NOUGEN_PROBE_PYTHON -and (Test-Path $env:NOUGEN_PROBE_PYTHON)) {
    $env:NOUGEN_PROBE_PYTHON
} elseif (Test-Path (Join-Path $Root '.venv\Scripts\python.exe')) {
    Join-Path $Root '.venv\Scripts\python.exe'
} elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
    (Get-Command python.exe).Source
} else {
    throw 'python.exe not found for authenticated gateway probe'
}
$TaskName = if ($env:NOUGEN_PROBE_TASK_NAME) { $env:NOUGEN_PROBE_TASK_NAME } else {
    'NouGen Shards Authenticated Probe'
}

if (-not (Test-Path -LiteralPath $Probe -PathType Leaf)) { throw "probe missing: $Probe" }
if ($IntervalMinutes -lt 1) { throw 'IntervalMinutes must be >= 1' }

$action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Probe`""
$start = (Get-Date).AddMinutes(1)
$durationDays = if ($env:NOUGEN_PROBE_DURATION_DAYS) {
    [int]$env:NOUGEN_PROBE_DURATION_DAYS
} else { 3650 }
$trigger = New-ScheduledTaskTrigger -Once -At $start `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days $durationDays)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description 'Authenticated NouGen Shards gateway probe; no model/GPU work.'
Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
if ($Disable) {
    Disable-ScheduledTask -TaskName $TaskName | Out-Null
    Write-Output "disabled: $TaskName"
} else {
    Enable-ScheduledTask -TaskName $TaskName | Out-Null
    Write-Output "installed: $TaskName every $IntervalMinutes minute(s) using $Probe"
}

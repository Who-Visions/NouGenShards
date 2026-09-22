<#
  Install/update the "NouGen NGS Node" scheduled task definition.

  Root cause this fixes (code-health W4, heartbeat stale 2026-09-13T22:34Z ->
  2026-09-14T23:xx): the task only had a LogonTrigger. start_grid.py --watch
  is a long-lived loop (tools/start_grid.py), and Windows Task Scheduler's
  RestartOnFailure only fires when the task's own action process exits with a
  failure code -- not when it is killed, the machine sleeps without a fresh
  interactive logon, or (absent an explicit ExecutionTimeLimit) the scheduler's
  default execution time limit ends it. With only a LogonTrigger, a watcher
  that dies any other way stays dead until the next real logon.

  watch() already makes re-invocation while a healthy instance is running a
  safe no-op (own file lock, see tools/start_grid.py:watch, "another --watch
  supervisor already holds the watch lock; exiting (not an error)"), so the
  fix is simply to make the task fire periodically too, not just at logon,
  and to remove the implicit time limit. Re-running this installer (e.g. from
  ngs_node_boot.cmd on every boot, mirroring install_grid_supervisor.ps1's own
  self-resync pattern) keeps the task definition from drifting silently.

  Safe to re-run: registering a task definition does not touch an
  already-running instance the task previously launched, and this script
  never starts, stops, or signals tools/start_grid.py itself.
#>
[CmdletBinding()]
param(
    [string]$TaskName = "NouGen NGS Node",
    [int]$RetriggerMinutes = 0
)

# PowerShell 5.1 has no ?? operator (this repo's house rule: PS 5.1 syntax only).
if ($RetriggerMinutes -le 0) {
    $RetriggerMinutes = if ($env:NOUGEN_NGS_TASK_RETRIGGER_MINS) { [int]$env:NOUGEN_NGS_TASK_RETRIGGER_MINS } else { 15 }
}

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$BootCmd = Join-Path $PSScriptRoot 'ngs_node_boot.cmd'
if (-not (Test-Path -LiteralPath $BootCmd -PathType Leaf)) {
    throw "boot entry missing: $BootCmd"
}
$RunHiddenVbs = Join-Path $env:USERPROFILE '.nougen\bin\run_hidden.vbs'
if (-not (Test-Path -LiteralPath $RunHiddenVbs -PathType Leaf)) {
    throw "run_hidden.vbs missing: $RunHiddenVbs (expected already installed at runtime)"
}
if ($RetriggerMinutes -lt 1) { throw "RetriggerMinutes must be >= 1, got $RetriggerMinutes" }

# Whoever is running this (the logged-in user), not a hardcoded machine/account name (Rule 0.2).
$UserId = "$env:USERDOMAIN\$env:USERNAME"
$WscriptExe = Join-Path $env:SystemRoot 'System32\wscript.exe'
$Arguments = "//B //Nologo `"$RunHiddenVbs`" `"$BootCmd`""

# StartBoundary in the past + an open-ended Repetition (no Duration) means "every N minutes,
# forever", starting immediately once registered -- the XML equivalent of the GUI's
# "Repeat task every: N minutes, for a duration of: Indefinitely".
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <URI>\$TaskName</URI>
    <Description>Boots/re-asserts the NouGen NGS node and its grid watcher. Recurring trigger added by install_ngs_node_task.ps1 so a killed or time-limited watcher self-heals without waiting for the next interactive logon.</Description>
  </RegistrationInfo>
  <Principals>
    <Principal id="Author">
      <UserId>$UserId</UserId>
      <LogonType>InteractiveToken</LogonType>
    </Principal>
  </Principals>
  <Settings>
    <DisallowStartIfOnBatteries>true</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>true</StopIfGoingOnBatteries>
    <Hidden>true</Hidden>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <RestartOnFailure>
      <Count>999</Count>
      <Interval>PT1M</Interval>
    </RestartOnFailure>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
  </Settings>
  <Triggers>
    <LogonTrigger>
      <UserId>$UserId</UserId>
    </LogonTrigger>
    <TimeTrigger>
      <StartBoundary>2026-01-01T00:00:00</StartBoundary>
      <Repetition>
        <Interval>PT${RetriggerMinutes}M</Interval>
      </Repetition>
    </TimeTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>$WscriptExe</Command>
      <Arguments>$Arguments</Arguments>
    </Exec>
  </Actions>
</Task>
"@

$stamp = Get-Date -Format 'yyyyMMddTHHmmssfff'
$tempXml = Join-Path ([IO.Path]::GetTempPath()) "ngs-node-task-$stamp.xml"
try {
    # UTF-16 LE with BOM: what schtasks /XML both emits and expects.
    [IO.File]::WriteAllText($tempXml, $xml, [Text.Encoding]::Unicode)
    $out = & schtasks /Create /TN $TaskName /XML $tempXml /F 2>&1
    if ($LASTEXITCODE -ne 0) { throw "schtasks /Create failed ($LASTEXITCODE): $out" }
    Write-Output "installed task '$TaskName': logon + every ${RetriggerMinutes}m, no execution time limit"
} finally {
    if (Test-Path -LiteralPath $tempXml) { Remove-Item -LiteralPath $tempXml -Force -ErrorAction SilentlyContinue }
}

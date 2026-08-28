<#
  Re-enables the two NouGen scheduled tasks that were deliberately DISABLED on
  2026-08-27 because they pointed at boot scripts that did not exist (every
  logon failed with result 1, while still appearing in audits as live
  launchers). Those scripts now exist:

      tools\ngs_node_boot.cmd      -> node_lane.ps1 start
      tools\ngs_gateway_boot.cmd   -> gateway_supervisor.ps1 -Once

  Both delegate to the LOCK-PROTECTED launchers, so running alongside the
  Startup-folder launcher (nougen_shards_grid.cmd) cannot stack competing binds
  on :4444 -- verified 2026-08-28: node_lane.ps1 start against a live node
  printed "node already running (listener pid 22328)" and exited 0 without
  touching the listener.

  Run:  powershell -NoProfile -ExecutionPolicy Bypass -File tools\enable_ngs_boot_tasks.ps1
  Undo: Disable-ScheduledTask -TaskName 'NouGen NGS Node','NouGen Shard Gateway'
#>

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot

# Refuse to enable a task whose target is missing -- that is the exact defect
# being fixed, and re-creating it silently would be worse than leaving it off.
$targets = @{
    'NouGen NGS Node'      = Join-Path $Root 'tools\ngs_node_boot.cmd'
    'NouGen Shard Gateway' = Join-Path $Root 'tools\ngs_gateway_boot.cmd'
}

foreach ($name in $targets.Keys) {
    $path = $targets[$name]
    if (-not (Test-Path $path)) {
        Write-Warning "$name : target missing ($path) - leaving DISABLED"
        continue
    }
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $task) { Write-Warning "$name : task not found"; continue }

    Enable-ScheduledTask -TaskName $name | Out-Null
    Write-Host "enabled: $name -> $path"
}

Get-ScheduledTask -TaskName 'NouGen NGS Node', 'NouGen Shard Gateway' |
    Select-Object TaskName, State | Format-Table -AutoSize

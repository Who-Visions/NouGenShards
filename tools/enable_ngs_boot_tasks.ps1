<#
  Re-enables the canonical NouGen node task that was deliberately DISABLED on
  2026-08-27 because they pointed at boot scripts that did not exist (every
  logon failed with result 1, while still appearing in audits as live
  launchers). Those scripts now exist:

      tools\ngs_node_boot.cmd      -> the versioned start_grid supervisor

  The old gateway task stays DISABLED by design: its quick-tunnel supervisor
  can compete with the named-tunnel owner. The authenticated probe has its own
  lightweight task (tools\install_gateway_probe_task.ps1). The node launcher
  is lock-protected, so running alongside the
  Startup-folder launcher (nougen_shards_grid.cmd) cannot stack competing binds
  on :4444 -- verified 2026-08-28: node_lane.ps1 start against a live node
  printed "node already running (listener pid 22328)" and exited 0 without
  touching the listener.

  Run:  powershell -NoProfile -ExecutionPolicy Bypass -File tools\enable_ngs_boot_tasks.ps1
  Undo: Disable-ScheduledTask -TaskName 'NouGen NGS Node'
#>

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot

# Refuse to enable a task whose target is missing -- that is the exact defect
# being fixed, and re-creating it silently would be worse than leaving it off.
$targets = @{
    'NouGen NGS Node' = Join-Path $Root 'tools\ngs_node_boot.cmd'
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

Get-ScheduledTask -TaskName 'NouGen NGS Node' |
    Select-Object TaskName, State | Format-Table -AutoSize

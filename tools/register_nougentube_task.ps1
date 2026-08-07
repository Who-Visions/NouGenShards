# Register (or refresh) the NouGenTube Daily Harvest scheduled task.
$cmd = Join-Path $PSScriptRoot 'nougentube_daily.cmd'
$action = New-ScheduledTaskAction -Execute $cmd
$trigger = New-ScheduledTaskTrigger -Daily -At 07:00
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName 'NouGenTube Daily Harvest' -Action $action -Trigger $trigger -Settings $settings -Description 'Sweep the NouGenTube roster (transcripts/channels.csv) for new videos and shard transcripts into the vault. 3-day lookback, idempotent.' -Force | Out-Null
Get-ScheduledTask -TaskName 'NouGenTube Daily Harvest' | Select-Object TaskName, State | Format-List

# Installs the aiwithdav3 PR reviewer poll as a local scheduled task (local, so it can reach the keymaker).
# Copies the tool to ~/.nougen/bin/pr_reviewer so the task survives worktree cleanup. Re-run after updates.
$ErrorActionPreference = 'Stop'
$dst = Join-Path $HOME '.nougen\bin\pr_reviewer'
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item -Force (Join-Path $PSScriptRoot '*.ts'), (Join-Path $PSScriptRoot '*.py'), (Join-Path $PSScriptRoot 'checklist.json') $dst
$bun = (Get-Command bun -ErrorAction Stop).Source
if ($bun -like '*.cmd') { $bun = Join-Path $HOME '.bun\bin\bun.exe' }
# conhost --headless: -WindowStyle Hidden still flashes a terminal on Windows 11
$action = New-ScheduledTaskAction -Execute "$env:WINDIR\System32\conhost.exe" `
  -Argument "--headless `"$bun`" `"$dst\review.ts`" poll --owner Who-Visions --since-hours 72 --max 4" -WorkingDirectory $dst
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 20)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1) -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries
Register-ScheduledTask -TaskName 'NouGen-PRReviewer-aiwithdav3' -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Get-ScheduledTask 'NouGen-PRReviewer-aiwithdav3' | Select-Object TaskName, State

param(
    [ValidateSet('start','status','stop')][string]$Action = 'status',
    [string]$Thread = $env:CODEX_THREAD_ID
)
$ErrorActionPreference = 'Stop'
$pipeScript = Join-Path $PSScriptRoot 'codex_pipe.py'
$pipePython = (Get-Command python -ErrorAction Stop).Source
$statusText = & $pipePython $pipeScript status 2>$null
$pipeStatus = if ($LASTEXITCODE -eq 0) { $statusText | ConvertFrom-Json } else { $null }
if ($Action -eq 'status') {
    if ($pipeStatus) { $pipeStatus | Format-List } else { Write-Output 'Codex pipe is offline.' }
    return
}
if ($Action -eq 'stop') {
    if ($pipeStatus) {
        $pipeProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($pipeStatus.pid)"
        if (-not $pipeProcess -or -not $pipeProcess.CommandLine.Contains($pipeScript)) {
            throw 'Process identity did not match the Codex pipe receiver.'
        }
        Stop-Process -Id $pipeStatus.pid
        Write-Output 'Codex pipe stopped. Queued messages and inbox files are preserved.'
    }
    return
}
if (-not $Thread) { throw 'Supply -Thread with the Codex session UUID, or run from a Codex session.' }
[void][guid]::Parse($Thread)
if ($pipeStatus) {
    if ($pipeStatus.thread -ne $Thread) { throw 'Pipe targets another thread. Stop it explicitly before retargeting.' }
    $pipeStatus | Format-List
    return
}
$pipeCodex = Join-Path $env:APPDATA 'npm\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe'
if (-not (Test-Path -LiteralPath $pipeCodex)) { throw "Native Codex executable missing: $pipeCodex" }
$pipeLogs = Join-Path $env:USERPROFILE '.nougen\logs'
New-Item -ItemType Directory -Path $pipeLogs -Force | Out-Null
$pipeArguments = @(('"' + $pipeScript + '"'), 'serve', '--thread', $Thread, '--executable', ('"' + $pipeCodex + '"'))
$pipeProcess = Start-Process -FilePath $pipePython -ArgumentList $pipeArguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $pipeLogs 'codex-pipe.stdout.log') -RedirectStandardError (Join-Path $pipeLogs 'codex-pipe.stderr.log')
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 100
    $statusText = & $pipePython $pipeScript status 2>$null
    if ($LASTEXITCODE -eq 0) { $statusText; return }
    if ($pipeProcess.HasExited) { throw "Receiver exited; inspect $pipeLogs\codex-pipe.stderr.log" }
}
throw "Receiver did not become ready; inspect $pipeLogs\codex-pipe.stderr.log"

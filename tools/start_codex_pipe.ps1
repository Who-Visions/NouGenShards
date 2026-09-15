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
# The npm global root moves with the active Node install (nvm-windows switches it), so it is a
# runtime probe, not a hardcoded path (Rule 0.2). NOUGEN_CODEX_EXE overrides outright; otherwise
# ask npm, then fall back to the legacy %APPDATA%\npm location for a pre-nvm install.
$pipeVendorSuffix = 'node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe'
$pipeCodex = if ($env:NOUGEN_CODEX_EXE -and (Test-Path -LiteralPath $env:NOUGEN_CODEX_EXE)) {
    $env:NOUGEN_CODEX_EXE
} else {
    $pipeNpmRoot = try { (& npm root -g 2>$null | Select-Object -First 1).Trim() } catch { $null }
    $pipeCandidates = @()
    if ($pipeNpmRoot) { $pipeCandidates += (Join-Path (Split-Path $pipeNpmRoot -Parent) $pipeVendorSuffix) }
    $pipeCandidates += (Join-Path $env:APPDATA "npm\$pipeVendorSuffix")
    $pipeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $pipeCodex) { throw "Native Codex executable not found (checked npm root -g and the legacy %APPDATA%\npm path; set NOUGEN_CODEX_EXE to override)" }
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

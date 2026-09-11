param(
    [string]$Server = "$PSScriptRoot\agy_pipe_server.py",
    [int]$IntervalSeconds = 5
)
$ErrorActionPreference = 'SilentlyContinue'
$pipe = '\\.\pipe\LOCAL\agy-msg-antigravity'

while ($true) {
    $present = [System.IO.Directory]::GetFiles('\\.\pipe\') -contains $pipe
    if (-not $present) {
        $running = Get-CimInstance Win32_Process |
            Where-Object { $_.CommandLine -like "*$Server*" }
        if (-not $running) {
            Start-Process -FilePath 'pythonw.exe' -ArgumentList $Server -WindowStyle Hidden
        }
    }
    Start-Sleep -Seconds $IntervalSeconds
}

<#
Which checkout is the node on this port really serving from?

node_lane.ps1 used to accept ANY uvicorn listener on the port as "already
running". On 2026-11-19 a dev checkout that had been switched to a PR branch
(20 commits behind main, without the :4444 leak fix) launched the node, and
the main checkout's lane kept reporting it healthy. These helpers trace the
listener back to the venv it was started from so the lane can tell its own
node from a foreign one.
#>

function Get-RepoFromCommandLine {
    param([string]$CommandLine)
    if (-not $CommandLine) { return $null }
    $m = [regex]::Match($CommandLine, '(?i)"?([a-z]:\\[^"]*?)\\\.venv\\(?:Scripts|bin)\\python')
    if ($m.Success) { return $m.Groups[1].Value }
    return $null
}

function Test-SameRepo {
    param([string]$A, [string]$B)
    if (-not $A -or -not $B) { return $false }
    $norm = { param($p) ($p -replace '/', '\').TrimEnd('\').ToLowerInvariant() }
    return (& $norm $A) -eq (& $norm $B)
}

function Get-ProcessRepo {
    # Walk the process and its parents (the venv python is a redirector, so the
    # listener itself is usually the base interpreter) until a venv path shows up.
    param([int]$ProcessId, [int]$MaxDepth = 5)
    $id = $ProcessId
    for ($i = 0; $i -lt $MaxDepth -and $id; $i++) {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
        if (-not $p) { return $null }
        $repo = Get-RepoFromCommandLine $p.CommandLine
        if ($repo) { return $repo }
        $id = [int]$p.ParentProcessId
    }
    return $null
}

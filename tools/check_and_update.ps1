<#
.SYNOPSIS
    Guarded Git Auto-Updater for NouGen Repositories.
    Ensures zero merge conflicts and preserves uncommitted work.
    Respects manual opt-out via environment variable and config flag.
#>
[CmdletBinding()]
param (
    [string]$RepoPath = "C:\Users\super\Outpost\NouGen",
    [string]$Remote = "origin",
    [int]$FetchTimeoutSec = 8,
    [switch]$NoUpdate = $false
)

# 0. Opt-out checks
if ($NoUpdate -or $env:NOUGEN_NO_AUTO_UPDATE -eq "1" -or $env:NOUGEN_NO_AUTO_UPDATE -eq "true") {
    Write-Host "[NouGen Sync] Auto-update disabled via opt-out flag/env. Skipping." -ForegroundColor DarkGray
    exit 0
}

# Check ~/.nougen/config.json if present
$cfgPath = Join-Path $env:USERPROFILE ".nougen\config.json"
if (Test-Path $cfgPath) {
    try {
        $cfg = Get-Content -Raw -Path $cfgPath | ConvertFrom-Json
        if ($cfg.auto_update -eq $false -or $cfg.auto_update -eq "false" -or $cfg.no_auto_update -eq $true) {
            Write-Host "[NouGen Sync] Auto-update disabled in config.json. Skipping." -ForegroundColor DarkGray
            exit 0
        }
    } catch {}
}

Set-Location -Path $RepoPath

# 1. Verify this is a valid Git directory
if (-not (Test-Path "$RepoPath\.git")) {
    Write-Warning "[NouGen Sync] '$RepoPath' is not a git repository. Skipping."
    exit 0
}

# 2. Check for uncommitted, staged, or untracked changes
$dirty = git status --porcelain
if ($dirty) {
    Write-Host "[NouGen Sync] Local uncommitted changes detected. Skipping auto-pull to protect work." -ForegroundColor Yellow
    exit 0
}

# 3. Non-blocking fetch with quick timeout
Write-Host "[NouGen Sync] Checking remote for updates ($Remote)..." -ForegroundColor Cyan
try {
    $fetchJob = Start-Job -ScriptBlock { param($r) git fetch $r --quiet } -ArgumentList $Remote
    $completed = Wait-Job $fetchJob -Timeout $FetchTimeoutSec
    if (-not $completed) {
        Stop-Job $fetchJob | Out-Null
        Remove-Job $fetchJob -Force | Out-Null
        Write-Warning "[NouGen Sync] Remote fetch timed out. Continuing with local version."
        exit 0
    }
    Receive-Job $fetchJob | Out-Null
    Remove-Job $fetchJob | Out-Null
} catch {
    Write-Warning "[NouGen Sync] Could not reach remote. Operating in offline mode."
    exit 0
}

# 4. Compare local vs upstream tracking commit
$localCommit  = (git rev-parse HEAD).Trim()
$remoteCommit = (git rev-parse '@{u}' 2>$null)

if (-not $remoteCommit) {
    Write-Host "[NouGen Sync] No upstream tracking branch configured. Skipping." -ForegroundColor DarkGray
    exit 0
}
$remoteCommit = $remoteCommit.Trim()

if ($localCommit -eq $remoteCommit) {
    Write-Host "[NouGen Sync] Repository is up to date." -ForegroundColor Green
    exit 0
}

# Check if we are behind
$behindCount = (git rev-list --count 'HEAD..@{u}').Trim()
if ([int]$behindCount -gt 0) {
    Write-Host "[NouGen Sync] Found $behindCount new commit(s). Pulling fast-forward updates..." -ForegroundColor Magenta
    git pull --ff-only $Remote
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[NouGen Sync] Successfully updated to latest version." -ForegroundColor Green
    } else {
        Write-Warning "[NouGen Sync] Fast-forward pull failed. Manual git sync required."
    }
} else {
    $aheadCount = (git rev-list --count '@{u}..HEAD').Trim()
    Write-Host "[NouGen Sync] Local branch is ahead of remote by $aheadCount commit(s)." -ForegroundColor Yellow
}

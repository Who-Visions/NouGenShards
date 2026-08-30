<#
  Install the version-controlled grid supervisor into the canonical runtime
  home. The scheduled task executes the installed copy so a repo update cannot
  silently leave the running supervisor on an older machine-only file.

  Source:  tools/start_grid.py (this checkout)
  Runtime: %USERPROFILE%/.nougen/bin/start_grid.py

  The old runtime is kept as a dated sibling backup before replacement. No
  secrets are read or printed.
#>
[CmdletBinding()]
param(
    [string]$RuntimePath = "",
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$SourcePath = Join-Path $PSScriptRoot 'start_grid.py'
if (-not $RuntimePath) {
    $runtimeHome = if ($env:NOUGEN_HOME) { $env:NOUGEN_HOME } else { Join-Path $env:USERPROFILE '.nougen' }
    $RuntimePath = Join-Path $runtimeHome 'bin\start_grid.py'
}

if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) {
    throw "versioned supervisor missing: $SourcePath"
}
$runtimeDir = Split-Path -Parent $RuntimePath
if (-not (Test-Path -LiteralPath $runtimeDir -PathType Container)) {
    New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
}

$sourceHash = (Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256).Hash
$runtimeHash = if (Test-Path -LiteralPath $RuntimePath -PathType Leaf) {
    (Get-FileHash -LiteralPath $RuntimePath -Algorithm SHA256).Hash
} else { '' }

if ($sourceHash -eq $runtimeHash) {
    Write-Output "grid supervisor current sha256=$sourceHash path=$RuntimePath"
    exit 0
}
if ($CheckOnly) {
    Write-Output "grid supervisor drift source=$sourceHash runtime=$runtimeHash path=$RuntimePath"
    exit 2
}

$stamp = Get-Date -Format 'yyyyMMddTHHmmssfff'
if ($runtimeHash) {
    $backup = "$RuntimePath.bak-$stamp"
    Copy-Item -LiteralPath $RuntimePath -Destination $backup -Force
    Write-Output "saved previous supervisor: $backup"
}

# Copy beside the destination then replace it in one move. The watcher keeps
# its already-loaded module; the next scheduled restart picks up this file.
$tempName = ".{0}.tmp-{1}" -f ([IO.Path]::GetFileName($RuntimePath)), $stamp
$temp = Join-Path $runtimeDir $tempName
try {
    Copy-Item -LiteralPath $SourcePath -Destination $temp -Force
    Move-Item -LiteralPath $temp -Destination $RuntimePath -Force
} finally {
    if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue }
}

$installedHash = (Get-FileHash -LiteralPath $RuntimePath -Algorithm SHA256).Hash
if ($installedHash -ne $sourceHash) { throw "installed supervisor hash mismatch" }
Write-Output "installed grid supervisor sha256=$installedHash path=$RuntimePath"

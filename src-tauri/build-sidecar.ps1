# Builds the NouGenShards Python engine into a self-contained sidecar and places
# it where Tauri's externalBin expects it:  src-tauri/bin/nougen_engine-<triple>.exe
#
# Run before `npm run tauri build`:
#     pwsh src-tauri/build-sidecar.ps1
#
# Requires: Python 3 with pyinstaller  (pip install pyinstaller)
$ErrorActionPreference = "Stop"

$bin    = Join-Path $PSScriptRoot "bin"
$repo   = Resolve-Path (Join-Path $PSScriptRoot "..")
$src    = Join-Path $repo "src"
$triple = "x86_64-pc-windows-msvc"
$spec   = Join-Path $bin "nougen_engine.spec"
$target = Join-Path $bin "nougen_engine-$triple.exe"

if (-not (Test-Path $spec)) { throw "Spec not found: $spec" }

# Make nougen_shards importable for PyInstaller's analysis pass.
$env:PYTHONPATH = $src

Write-Host "[sidecar] Building engine from $spec ..."
python -m PyInstaller --noconfirm --clean `
    --distpath $bin `
    --workpath (Join-Path $bin "build") `
    $spec

if (-not (Test-Path $target)) {
    throw "[sidecar] Build did not produce $target"
}

Write-Host "[sidecar] OK -> $target"

# Smoke test: the frozen engine must answer a JSON command and exit 0.
Write-Host "[sidecar] Smoke test: status --json"
& $target status --json | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "[sidecar] Smoke test failed (exit $LASTEXITCODE)"
}
Write-Host "[sidecar] Smoke test passed. Sidecar ready for bundling."

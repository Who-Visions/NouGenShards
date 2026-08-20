<# Incrementally mirror Blade's canonical shard lane into Who-Art's :4445 standby. #>
param([switch]$DryRun)

$ErrorActionPreference = 'Stop'
$route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' |
    Sort-Object RouteMetric, InterfaceMetric | Select-Object -First 1
$address = Get-NetIPAddress -InterfaceIndex $route.InterfaceIndex -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1
if (-not $address) { throw 'cannot resolve Who-Art LAN address' }
$target = "http://$($address.IPAddress):4445"
$health = Invoke-RestMethod -Uri "$target/health" -TimeoutSec 5
if (-not $health.substrate.recall_trustworthy) { throw 'standby node is not recall-trustworthy' }

$dry = if ($DryRun) { ' --dry-run' } else { '' }
$remote = @"
`$ProgressPreference='SilentlyContinue'; `$ErrorActionPreference='Stop'
`$repo=Join-Path `$env:USERPROFILE 'Watchtower\NouGen\NouGenShards-push-main'
`$env:PYTHONPATH=Join-Path `$repo 'src'
`$env:NOUGEN_VAULT_DIR=Join-Path `$env:USERPROFILE '.nougen\shards'
`$env:NOUGEN_SECRETS_VAULT_DIR=Join-Path `$env:USERPROFILE '.nougen\secrets'
& (Join-Path `$repo '.venv\Scripts\python.exe') (Join-Path `$env:USERPROFILE '.nougen\tools\relay_push.py') --url '$target' --batch 100 --missing-only --include-private$dry
exit `$LASTEXITCODE
"@
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($remote))
& ssh -o BatchMode=yes -o ConnectTimeout=8 blade powershell -NoProfile -NonInteractive -EncodedCommand $encoded
if ($LASTEXITCODE -ne 0) { throw "standby synchronization failed ($LASTEXITCODE)" }

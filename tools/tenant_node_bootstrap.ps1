<#
Tenant node bootstrap (Windows). Run on the tenant's own machine.

First run:   .\tools\tenant_node_bootstrap.ps1 -TenantId <id> -Email <you@example.com> -Invite <code>
Later runs:  .\tools\tenant_node_bootstrap.ps1 -TenantId <id>   (re-registers the new tunnel URL)

The node token is generated once, saved to a file readable only by this Windows user,
and reused on every run. The gateway stores it so it can reach this node; it is never
written to the repository or to shared logs.
#>
param(
  [Parameter(Mandatory)] [string]$TenantId,
  [string]$Email = '',
  [string]$Invite = '',
  [string]$Gateway = 'https://fleet.nougenai.com',
  [string]$Hostname = '',
  [int]$Port = 4460
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'
$pyw = Join-Path $root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $py)) {
  python -m venv (Join-Path $root '.venv')
  & $py -m pip install -q -e $root
}

$stateDir = Join-Path $env:USERPROFILE ".nougen\tenants\$TenantId"
$tokFile = Join-Path $stateDir 'node.json'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$vault = Join-Path $stateDir 'vault'
New-Item -ItemType Directory -Force -Path $vault | Out-Null

# Owner-only ACL on the state folder: only this Windows user can read the token.
icacls $stateDir /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F" | Out-Null

if (Test-Path $tokFile) {
  $state = Get-Content $tokFile -Raw | ConvertFrom-Json
  $tok = $state.token
  if (-not $Email) { $Email = $state.email }
} else {
  if (-not $Invite -or -not $Email) { throw 'first run needs -Email and -Invite' }
  $env:NOUGEN_VAULT_DIR = $vault
  $tok = & $py -c "import sys; sys.argv=['nougen','tenant','mint','$TenantId','--label','Tenant $TenantId']; from nougen_shards.cli import main; main()" 2>$null |
    Select-String -Pattern 'Token: (\S+)' | ForEach-Object { $_.Matches[0].Groups[1].Value }
  if (-not $tok) { throw 'tenant mint failed' }
  @{ token = $tok; email = $Email } | ConvertTo-Json | Set-Content -Path $tokFile -Encoding utf8
  icacls $tokFile /inheritance:r /grant:r "$($env:USERNAME):F" | Out-Null
}

# Node: loopback only, bound to this tenant's vault, under pythonw (no console window).
$env:NOUGEN_VAULT_DIR = $vault
$env:NGS_NODE_TOKEN = $tok
$alive = $false
try { $alive = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3).StatusCode -eq 200 } catch { }
if (-not $alive) {
  Start-Process -WindowStyle Hidden -FilePath $pyw `
    -ArgumentList @('-m','uvicorn','app:app','--host','127.0.0.1','--port',"$Port") `
    -WorkingDirectory $root
}
# Wait for the node to answer before anything is registered (cold starts take a while).
$healthy = $false
for ($i = 0; $i -lt 90 -and -not $healthy; $i++) {
  Start-Sleep -Seconds 2
  try { $healthy = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3).StatusCode -eq 200 } catch { }
}
if (-not $healthy) { throw "node did not become healthy on port $Port" }

# Tunnel: quick tunnel (no account). A named hostname is optional.
$tlog = Join-Path $stateDir 'tunnel.log'
$tunnelArgs = @('tunnel','--url',"http://127.0.0.1:$Port")
if ($Hostname) { $tunnelArgs = @('tunnel','--url',"http://127.0.0.1:$Port",'--hostname',$Hostname) }
# Re-runs replace the old tunnel for this port instead of stacking another one.
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" |
  Where-Object { $_.CommandLine -match [regex]::Escape("127.0.0.1:$Port") } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Process -WindowStyle Hidden -FilePath 'cloudflared' -ArgumentList $tunnelArgs -RedirectStandardError $tlog
$url = $null
for ($i = 0; $i -lt 60 -and -not $url; $i++) {
  Start-Sleep -Seconds 2
  if (Test-Path $tlog) {
    # Only the tunnel's own hostname: never a URL that merely appears in the log.
    $pattern = if ($Hostname) { 'https://' + [regex]::Escape($Hostname) } else { 'https://[a-z0-9-]+\.trycloudflare\.com' }
    $m = Select-String -Path $tlog -Pattern $pattern | Select-Object -Last 1
    if ($m) { $url = $m.Matches[0].Value }
  }
}
if (-not $url) { throw "tunnel did not come up; see $tlog" }

# Register (or re-register) with the gateway. The gateway probes the node with this
# token before it stores or updates anything.
$body = @{ code = $Invite; eml = $Email; node_url = $url; token = $tok } | ConvertTo-Json
$reply = Invoke-RestMethod -Method Post -Uri "$Gateway/tenant/register" -ContentType 'application/json' -Body $body
Write-Host "registered: $($reply.enrolled) -> $($reply.node_url)"
Write-Host "Your node is live. Leave this window open."

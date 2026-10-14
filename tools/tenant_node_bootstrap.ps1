<#
Tenant node bootstrap (Windows). Run once on the tenant's own machine.

Creates a private NouGen node: its own vault, its own tenant token, served on
loopback and exposed through the tenant's own Cloudflare tunnel. Nothing here
touches the owner's node, vault, relays or tokens.

  .\tools\tenant_node_bootstrap.ps1 -TenantId <tenant-id> -Hostname <tenant-hostname>
#>
param(
  [Parameter(Mandatory)] [string]$TenantId,
  [Parameter(Mandatory)] [string]$Invite,
  [string]$Gateway = 'https://fleet.nougenai.com',
  [string]$Hostname = '',
  [int]$Port = 4460
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
  python -m venv (Join-Path $root '.venv')
  & $py -m pip install -q -e $root
}
$vault = Join-Path $env:USERPROFILE ".nougen\tenants\$TenantId"
New-Item -ItemType Directory -Force -Path $vault | Out-Null
$env:NOUGEN_VAULT_DIR = $vault

# Mint the tenant token. It is printed once, here, to the tenant only.
$tok = & $py -c "import sys; sys.argv=['nougen','tenant','mint','$TenantId','--label','Tenant $TenantId']; from nougen_shards.cli import main; main()" 2>$null |
  Select-String -Pattern 'Token: (\S+)' | ForEach-Object { $_.Matches[0].Groups[1].Value }
if (-not $tok) { throw 'tenant mint failed (tenant may already exist; use the token you saved)' }

# Node: loopback only, bound to this tenant's vault.
$env:NGS_NODE_TOKEN = $tok
# Background server runs under pythonw (no console window).
$pyw = Join-Path $root '.venv\Scripts\pythonw.exe'
Start-Process -WindowStyle Hidden -FilePath $pyw `
  -ArgumentList @('-m','uvicorn','app:app','--host','127.0.0.1','--port',"$Port") `
  -WorkingDirectory $root

# Tunnel: a free quick tunnel needs no account. A named hostname is optional.
$tlog = Join-Path $env:TEMP "tenant-$TenantId-tunnel.log"
$tunnelArgs = @('tunnel','--url',"http://127.0.0.1:$Port")
if ($Hostname) { $tunnelArgs = @('tunnel','--url',"http://127.0.0.1:$Port",'--hostname',$Hostname) }
Start-Process -WindowStyle Hidden -FilePath 'cloudflared' -ArgumentList $tunnelArgs `
  -RedirectStandardError $tlog
$url = $null
for ($i = 0; $i -lt 60 -and -not $url; $i++) {
  Start-Sleep -Seconds 2
  if (Test-Path $tlog) {
    $m = Select-String -Path $tlog -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com|https://\S+\.(?:com|net|org)' | Select-Object -Last 1
    if ($m) { $url = $m.Matches[0].Value }
  }
}
if (-not $url) { throw "tunnel did not come up; see $tlog" }

# Register with the gateway automatically. The gateway verifies the node answers
# with this token before it stores anything. Nothing is pasted by hand.
$body = @{ code = $Invite; node_url = $url; token = $tok } | ConvertTo-Json
$reply = Invoke-RestMethod -Method Post -Uri "$Gateway/tenant/register" -ContentType 'application/json' -Body $body
Write-Host "registered: $($reply.enrolled) -> $($reply.node_url)"
Write-Host "Your node is live. Leave this window open."

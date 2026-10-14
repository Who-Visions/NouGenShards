<#
Tenant node bootstrap (Windows). Run once on the tenant's own machine.

Creates a private NouGen node: its own vault, its own tenant token, served on
loopback and exposed through the tenant's own Cloudflare tunnel. Nothing here
touches the owner's node, vault, relays or tokens.

  .\tools\tenant_node_bootstrap.ps1 -TenantId fabian -Hostname fabian-node.example.com
#>
param(
  [Parameter(Mandatory)] [string]$TenantId,
  [Parameter(Mandatory)] [string]$Hostname,
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
Start-Process -WindowStyle Hidden -FilePath $py `
  -ArgumentList @('-m','uvicorn','app:app','--host','127.0.0.1','--port',"$Port") `
  -WorkingDirectory $root

# Tunnel: the tenant's own Cloudflare tunnel (cloudflared must be logged in).
Start-Process -WindowStyle Hidden -FilePath 'cloudflared' `
  -ArgumentList @('tunnel','--url',"http://127.0.0.1:$Port",'--hostname',$Hostname)

Write-Host "node_url=https://$Hostname"
Write-Host "tenant token (send privately to the gateway operator, do not post it):"
Write-Host $tok

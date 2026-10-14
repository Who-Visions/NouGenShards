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
# Every child process is created with no console window and its output captured.
# Nothing here may open a visible terminal on the tenant's machine.
function Invoke-Quiet {
  param([string]$File, [string[]]$Arguments, [switch]$Wait)
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $File
  $psi.Arguments = ($Arguments | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $proc = [System.Diagnostics.Process]::Start($psi)
  if ($Wait) {
    $out = $proc.StandardOutput.ReadToEnd()
    $proc.StandardError.ReadToEnd() | Out-Null
    $proc.WaitForExit()
    return [pscustomobject]@{ Code = $proc.ExitCode; Out = $out }
  }
  return $proc
}

$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'
$pyw = Join-Path $root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $py)) {
  $r = Invoke-Quiet -File 'python' -Arguments @('-m','venv',(Join-Path $root '.venv')) -Wait
  if ($r.Code -ne 0) { throw 'venv creation failed' }
  $r = Invoke-Quiet -File $py -Arguments @('-m','pip','install','-q','-e',$root) -Wait
  if ($r.Code -ne 0) { throw 'pip install failed' }
}

$stateDir = Join-Path $env:USERPROFILE ".nougen\tenants\$TenantId"
$tokFile = Join-Path $stateDir 'node.json'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$vault = Join-Path $stateDir 'vault'
New-Item -ItemType Directory -Force -Path $vault | Out-Null

# Owner-only ACL on the state folder: only this Windows user can read the token.
Invoke-Quiet -File 'icacls' -Arguments @($stateDir,'/inheritance:r','/grant:r',"$($env:USERNAME):(OI)(CI)F") -Wait | Out-Null

if (Test-Path $tokFile) {
  $state = Get-Content $tokFile -Raw | ConvertFrom-Json
  $tok = $state.token
  if (-not $Email) { $Email = $state.email }
} else {
  if (-not $Invite -or -not $Email) { throw 'first run needs -Email and -Invite' }
  $env:NOUGEN_VAULT_DIR = $vault
  $mint = Invoke-Quiet -File $py -Arguments @('-c',"import sys; sys.argv=['nougen','tenant','mint','$TenantId','--label','Tenant $TenantId']; from nougen_shards.cli import main; main()") -Wait
  $tok = [regex]::Match($mint.Out, 'Token: (\S+)').Groups[1].Value
  if (-not $tok) { throw 'tenant mint failed' }
  @{ token = $tok; email = $Email } | ConvertTo-Json | Set-Content -Path $tokFile -Encoding utf8
  Invoke-Quiet -File 'icacls' -Arguments @($tokFile,'/inheritance:r','/grant:r',"$($env:USERNAME):F") -Wait | Out-Null
}

# Node: loopback only, bound to this tenant's vault, under pythonw (no console window).
$env:NOUGEN_VAULT_DIR = $vault
$env:NGS_NODE_TOKEN = $tok
$alive = $false
try { $alive = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3).StatusCode -eq 200 } catch { }
if (-not $alive) {
  $null = Invoke-Quiet -File $pyw -Arguments @('-m','uvicorn','app:app','--host','127.0.0.1','--port',"$Port")
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
$null = Invoke-Quiet -File 'cloudflared' -Arguments $tunnelArgs
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

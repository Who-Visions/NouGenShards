<# Start/stop the complete Who-Art shard-highway stack in dependency order. #>
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'status')]
    [string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'
$Node = Join-Path $PSScriptRoot 'node_lane.ps1'
$Proxy = Join-Path $PSScriptRoot 'shard_primary_proxy.ps1'
$Tunnel = Join-Path $PSScriptRoot 'tunnel_lane.ps1'

switch ($Action) {
    'start' {
        # Local complete copy: standby/readiness target, never the public writer.
        $previousPort = $env:NGS_PORT
        try {
            $env:NGS_PORT = '4445'
            & $Node start
        } finally {
            $env:NGS_PORT = $previousPort
        }
        & $Proxy start
        & $Tunnel start
        break
    }
    'stop' {
        & $Tunnel stop
        & $Proxy stop
        $previousPort = $env:NGS_PORT
        try {
            $env:NGS_PORT = '4445'
            & $Node stop
        } finally {
            $env:NGS_PORT = $previousPort
        }
        break
    }
    'status' {
        & $Tunnel status
        & $Proxy status
        $previousPort = $env:NGS_PORT
        try {
            $env:NGS_PORT = '4445'
            & $Node status
        } finally {
            $env:NGS_PORT = $previousPort
        }
        break
    }
}

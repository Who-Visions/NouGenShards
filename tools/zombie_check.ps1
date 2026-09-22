<#
.SYNOPSIS
  Find and surgically kill genuine zombie/orphaned Windows developer processes.
  Intelligently separates real abandoned developer zombies from vendor tray apps,
  Windows logon bootstrappers, and registered background service daemons.

.DESCRIPTION
  Dynamic and non-destructive by default.
  - Safe by default: Run without flags to report.
  - Run with -Kill to terminate ONLY confirmed actionable developer zombies.
  - Vendor autostart apps (Asus, Radeon, Adobe CC) and registered background daemons
    (whoart-vault tunnel, wake daemons) are protected unless -IncludeVendor is explicitly set.

.PARAMETER Kill
  Actually terminate actionable developer zombies. Without this flag, only reports.

.PARAMETER IncludeVendor
  Also include vendor tray and autostart apps in the actionable kill list (off by default).

.PARAMETER IncludeSystem
  Also consider PPID 0/4 and Windows session bootstrappers (off by default).

.PARAMETER MinAgeMinutes
  Skip anything younger than this (default 2) -- avoids racing a process mid-spawn.

.EXAMPLE
  .\zombie_check.ps1                  # report only
  .\zombie_check.ps1 -Kill            # report + kill actionable zombies
#>
[CmdletBinding()]
param(
    [switch]$Kill,
    [switch]$IncludeVendor,
    [switch]$IncludeSystem,
    [int]$MinAgeMinutes = 2
)

$ErrorActionPreference = 'Stop'

$all = Get-CimInstance Win32_Process
$byId = @{}
foreach ($p in $all) { $byId[[int]$p.ProcessId] = $p }

$now = Get-Date

# Windows intentionally orphans these by design
$bootstrapByDesign = @(
    'winlogon.exe','csrss.exe','wininit.exe','smss.exe','explorer.exe',
    'userinit.exe','services.exe','lsass.exe','WindowsTerminal.exe',
    'Microsoft.CmdPal.UI.exe','dwm.exe','spoolsv.exe'
)

# Vendor tray & background apps whose launcher was the Windows logon bootstrapper
$vendorTrayPatterns = @(
    'Asus*','Radeon*','AMDRSServ*','Creative Cloud*','CCXProcess*','CoreSync*',
    'Adobe*','LIFX*','Razer*','NvContainer*','NVIDIA*','ArmouryCrate*','conhost.exe'
)

# Registered background daemons with active .pid files in .nougen
$registeredPids = @{}
$logDirs = @("$env:USERPROFILE\.nougen\logs", "$env:USERPROFILE\.nougen\state", "$env:USERPROFILE\.nougen\bin")
foreach ($dir in $logDirs) {
    if (Test-Path $dir) {
        Get-ChildItem $dir -Filter "*.pid" -ErrorAction SilentlyContinue | ForEach-Object {
            $val = (Get-Content $_.FullName -Raw -ErrorAction SilentlyContinue).Trim()
            if ($val -match '^\d+$') { $registeredPids[[int]$val] = $_.Name }
        }
    }
}

$actionableZombies = @()
$protectedOrphans = @()

foreach ($p in $all) {
    $pid_ = [int]$p.ProcessId
    $ppid = [int]$p.ParentProcessId

    if (-not $IncludeSystem -and ($ppid -eq 0 -or $ppid -eq 4)) { continue }
    if (-not $IncludeSystem -and $bootstrapByDesign -contains $p.Name) { continue }

    $created = $p.CreationDate
    if ($created -and ($now - $created).TotalMinutes -lt $MinAgeMinutes) { continue }

    $parent = $byId[$ppid]
    $isOrphan = -not $parent

    if (-not $isOrphan) { continue }

    $wsBytes = if ($p.WorkingSetSize) { [int64]$p.WorkingSetSize } else { 0 }
    $memMb = [math]::Round($wsBytes / 1MB, 1)
    $ageHours = if ($created) { [math]::Round(($now - $created).TotalHours, 1) } else { 0 }
    $cmd = if ($p.CommandLine) { $p.CommandLine.Trim() } else { '' }

    # Check protection
    $isRegistered = $registeredPids.ContainsKey($pid_)
    $isVendor = $false
    foreach ($pat in $vendorTrayPatterns) {
        if ($p.Name -like $pat) { $isVendor = $true; break }
    }

    $item = [pscustomobject]@{
        PID         = $pid_
        PPID        = $ppid
        Name        = $p.Name
        MemMB       = $memMb
        AgeHours    = $ageHours
        CommandLine = $cmd
    }

    if ($isRegistered) {
        $item | Add-Member -MemberType NoteProperty -Name Reason -Value "Registered Daemon ($($registeredPids[$pid_]))"
        $protectedOrphans += $item
    } elseif ($isVendor -and -not $IncludeVendor) {
        $item | Add-Member -MemberType NoteProperty -Name Reason -Value "Vendor Tray / Logon Bootstrapper"
        $protectedOrphans += $item
    } else {
        $item | Add-Member -MemberType NoteProperty -Name Reason -Value "Dead Parent (Abandoned)"
        $actionableZombies += $item
    }
}

Write-Host "`n==================================================================" -ForegroundColor Cyan
Write-Host "       🧟 NOUGEN DYNAMIC PROCESS SUPERVISOR & ZOMBIE HUNTER       " -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

if (-not $actionableZombies -and -not $protectedOrphans) {
    Write-Host "🟢 All developer processes are healthy! Zero dead-parent orphans found." -ForegroundColor Green
    Write-Host "==================================================================`n" -ForegroundColor Cyan
    return
}

# 1. Actionable Developer Zombies
if ($actionableZombies) {
    $totalReclaimMb = ($actionableZombies | Measure-Object -Property MemMB -Sum).Sum
    Write-Host "`n⚠️  ACTIONABLE DEVELOPER ZOMBIES ($($actionableZombies.Count)) | RECLAIMABLE: $totalReclaimMb MB RAM" -ForegroundColor Yellow
    Write-Host "   Dead parent process is gone. Leftover dev servers, hung tasks, or abandoned runners:" -ForegroundColor DarkGray
    Write-Host "------------------------------------------------------------------" -ForegroundColor DarkGray
    
    $actionableZombies | Sort-Object AgeHours -Descending | Format-Table @(
        @{Label="PID"; Expression={$_.PID}; Width=7},
        @{Label="PARENT"; Expression={"💀 PID " + $_.PPID}; Width=14},
        @{Label="NAME"; Expression={$_.Name}; Width=16},
        @{Label="RAM"; Expression={"$($_.MemMB) MB"}; Width=10},
        @{Label="AGE"; Expression={"$($_.AgeHours)h"}; Width=6},
        @{Label="COMMAND"; Expression={$_.CommandLine}}
    ) -AutoSize -Wrap | Out-String -Width 200 | Write-Host
} else {
    Write-Host "`n🟢 Zero actionable developer zombies found! No stuck dev tasks." -ForegroundColor Green
}

# 2. Protected / Vendor Tray Daemons
if ($protectedOrphans) {
    Write-Host "`n🛡️  PROTECTED ORPHANED-BY-DESIGN DAEMONS ($($protectedOrphans.Count))" -ForegroundColor Blue
    Write-Host "   Vendor tray apps & registered daemons whose launcher exited by design (left alone):" -ForegroundColor DarkGray
    Write-Host "------------------------------------------------------------------" -ForegroundColor DarkGray
    
    $protectedOrphans | Sort-Object Name | Format-Table @(
        @{Label="PID"; Expression={$_.PID}; Width=7},
        @{Label="NAME"; Expression={$_.Name}; Width=20},
        @{Label="REASON"; Expression={$_.Reason}; Width=32},
        @{Label="RAM"; Expression={"$($_.MemMB) MB"}; Width=10}
    ) -AutoSize | Out-String -Width 200 | Write-Host
}

# Execution logic
if ($Kill) {
    if (-not $actionableZombies) {
        Write-Host "Nothing to kill -- zero actionable zombies found." -ForegroundColor Green
    } else {
        Write-Host "`n⚡ TERMINATING $($actionableZombies.Count) ACTIONABLE ZOMBIE(S)..." -ForegroundColor Yellow
        $killedCount = 0
        $reclaimedMb = 0
        foreach ($z in $actionableZombies) {
            try {
                Stop-Process -Id $z.PID -Force -ErrorAction Stop
                Write-Host "  ✅ Terminated PID $($z.PID) ($($z.Name)) - reclaimed $($z.MemMB) MB" -ForegroundColor Green
                $killedCount++
                $reclaimedMb += $z.MemMB
            } catch {
                Write-Host "  ❌ Failed to terminate PID $($z.PID) ($($z.Name)): $_" -ForegroundColor Red
            }
        }
        Write-Host "`n🎉 Reclaimed $reclaimedMb MB RAM across $killedCount process(es)." -ForegroundColor Green
    }
} else {
    if ($actionableZombies) {
        Write-Host "💡 Dry run only. Run with -Kill to terminate these $($actionableZombies.Count) developer zombie(s)." -ForegroundColor Cyan
    }
}

Write-Host "==================================================================`n" -ForegroundColor Cyan

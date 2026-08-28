@echo off
REM ngs_node_boot.cmd - boot entry for the "NouGen NGS Node" scheduled task.
REM
REM Created 2026-08-28. This task existed since before then but pointed at this
REM filename while the file DID NOT EXIST, so it failed every logon with result
REM 1 and showed up in audits as a live launcher when it was dead config
REM (see vault shard "VERIFIED 2026-08-27: gateway launcher-race lock proven").
REM
REM It deliberately delegates to node_lane.ps1 rather than launching uvicorn
REM itself. node_lane.ps1 holds the cross-process singleton lock
REM (NOUGEN_NODE_LOCK), so if the Startup-folder launcher or gateway_supervisor
REM is already mid-start, this stands down cleanly instead of racing it. Two
REM launchers stacking competing binds on :4444 is exactly the 2026-08-27
REM outage; the lock is what prevents it, so never bypass this indirection.

setlocal
set "NGS_ROOT=%~dp0.."
pushd "%NGS_ROOT%" || exit /b 1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\node_lane.ps1" start
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%

@echo off
REM ngs_gateway_boot.cmd - boot entry for the "NouGen Shard Gateway" task.
REM
REM Created 2026-08-28 for the same reason as ngs_node_boot.cmd: the task
REM referenced this file while it did not exist, failing every logon (result 1).
REM
REM Runs ONE supervisor tick, not the loop. The quick tunnel's hostname is
REM random and changes whenever cloudflared restarts, while the fleet worker
REM has it baked into SHARD_GATEWAY_URL - so after a reboot the worker points
REM at a dead URL and the gates shut silently. One tick at logon re-points it.
REM -Once matters: without it this would block the task indefinitely.
REM
REM node_lane.ps1 start is step 1 inside the supervisor and is lock-protected,
REM so this is safe to run alongside ngs_node_boot.cmd.

setlocal
set "NGS_ROOT=%~dp0.."
pushd "%NGS_ROOT%" || exit /b 1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\gateway_supervisor.ps1" -Once
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%

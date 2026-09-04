@echo off
REM ngs_node_boot.cmd - boot entry for the "NouGen NGS Node" scheduled task.
REM
REM Created 2026-08-28. This task existed since before then but pointed at this
REM filename while the file DID NOT EXIST, so it failed every logon with result
REM 1 and showed up in audits as a live launcher when it was dead config
REM (see vault shard "VERIFIED 2026-08-27: gateway launcher-race lock proven").
REM
REM The long-lived watcher in the canonical user brain directory owns both the
REM node and named tunnel. Calling it here (rather than launching uvicorn once)
REM is what makes a dead origin self-heal instead of returning a Cloudflare 502.
REM It carries the same cross-process locks as node_lane.ps1 and is idempotent,
REM so the Startup-folder copy and this scheduled task can safely overlap.

setlocal
set "NGS_ROOT=%~dp0.."
pushd "%NGS_ROOT%" || exit /b 1
rem Keep the runtime copy in .nougen synchronized with the checked-in source.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\install_grid_supervisor.ps1"
if errorlevel 1 (
  popd
  exit /b 1
)
set "NOUGEN_HOME=%USERPROFILE%\.nougen"
set "NGS_REPO=%NGS_ROOT%"
set "PYTHONW=%LocalAppData%\Programs\Python\Python311\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=pythonw.exe"
if not exist "%NOUGEN_HOME%\bin\start_grid.py" (
  popd
  exit /b 1
)
REM 2026-09-04: start /b so this cmd exits instead of holding a console window open
REM while pythonw runs; the watcher is detached and its own log is the record.
start "" /b "%PYTHONW%" "%NOUGEN_HOME%\bin\start_grid.py" --watch
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%

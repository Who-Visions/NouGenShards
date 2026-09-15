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
set "NGS_PORT=4445"
set "NGS_ROOT=%~dp0.."
pushd "%NGS_ROOT%" || exit /b 1
rem Keep the runtime copy synchronized with the checked-in source, at
rem whatever NOUGEN_HOME the machine already has configured. This used to
rem hardcode NOUGEN_HOME to %USERPROFILE%\.nougen unconditionally, clobbering
rem this machine's real (persistent User env var) NOUGEN_HOME of
rem C:\Users\super\Watchtower\NouGen for the duration of this script. The
rem sync target (install_grid_supervisor.ps1, same default) followed the
rem override too, but the two runs never happened at the same moment, so the
rem override path (~\.nougen\bin\start_grid.py) silently forked from the
rem synced one and drifted until it threw NameError on import and the
rem --watch loop died at every boot with no visible failure (2026-09-14,
rem heartbeat stuck since 2026-09-13T22:34Z). Only fall back to
rem %USERPROFILE%\.nougen when NOUGEN_HOME is genuinely unset, per Rule 0.2
rem (env > config > logged fallback, never override a configured value).
if not defined NOUGEN_HOME set "NOUGEN_HOME=%USERPROFILE%\.nougen"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\install_grid_supervisor.ps1"
if errorlevel 1 (
  popd
  exit /b 1
)
set "NGS_REPO=%NGS_ROOT%"
set "PYTHONW=%LocalAppData%\Programs\Python\Python311\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=pythonw.exe"
if not exist "%NOUGEN_HOME%\bin\start_grid.py" (
  popd
  exit /b 1
)
"%PYTHONW%" "%NOUGEN_HOME%\bin\start_grid.py" --watch
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%

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
set "NOUGEN_HOME=%USERPROFILE%\.nougen"
set "PYTHONW=%LocalAppData%\Programs\Python\Python311\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=pythonw.exe"
if not exist "%NOUGEN_HOME%\bin\start_grid.py" exit /b 1
"%PYTHONW%" "%NOUGEN_HOME%\bin\start_grid.py" --watch
exit /b %ERRORLEVEL%

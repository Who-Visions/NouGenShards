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
rem The shared gateway and node_lane health checks target 4444.  Running this
rem watcher on 4445 created a false-green scheduled task while the real write
rem origin stayed down and the edge returned 502.
set "NGS_PORT=4444"
set "NGS_ROOT=%~dp0.."
pushd "%NGS_ROOT%" || exit /b 1
rem Resolve ONE runtime home before both the supervisor sync and the launch.
rem This used to set NOUGEN_HOME only after the sync, so with a different
rem NOUGEN_HOME in the user env the sync refreshed one home while the watcher
rem launched a stale copy from another, and --watch died at boot unseen
rem (2026-09-14). A configured NOUGEN_HOME wins only if it is a real runtime
rem home: the supervisor imports keymaker_peel from its bin at startup, so a
rem home without it would crash under pythonw with no trace. Otherwise fall
rem back to the per-user default and say so. No goto: this file is stored
rem LF-only, where cmd's label search is unreliable.
if not defined NGS_HOME_MARKER set "NGS_HOME_MARKER=bin\keymaker_peel.py"
set "NGS_HOME_FALLBACK=%USERPROFILE%\.nougen"
if defined NOUGEN_HOME if not exist "%NOUGEN_HOME%\%NGS_HOME_MARKER%" >&2 echo ngs_node_boot: NOUGEN_HOME=%NOUGEN_HOME% lacks %NGS_HOME_MARKER%; using %NGS_HOME_FALLBACK%
if defined NOUGEN_HOME if not exist "%NOUGEN_HOME%\%NGS_HOME_MARKER%" set "NOUGEN_HOME="
if not defined NOUGEN_HOME set "NOUGEN_HOME=%NGS_HOME_FALLBACK%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\install_grid_supervisor.ps1"
if errorlevel 1 (
  popd
  exit /b 1
)
rem Re-assert the task's own trigger config (logon + recurring, no time limit) so it cannot
rem silently drift back to logon-only. Best-effort: a failure here must not block this boot's
rem watcher from starting, so it is swallowed, not fatal like the step above. This fires every
rem NOUGEN_NGS_TASK_RETRIGGER_MINS (default 15) forever, so only failures are logged -- a
rem success line appended on every re-trigger would grow the log without bound.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\install_ngs_node_task.ps1" 1>nul 2>>"%USERPROFILE%\.nougen\logs\ngs_node_task_install.log"
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

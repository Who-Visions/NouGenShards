@echo off
REM Boot wrapper for the gateway publish loop (tunnel + Worker repoint).
REM
REM Runs as the interactive user for the same reason the node does: keymaker is
REM DPAPI user-bound, and wrangler's OAuth credentials live in the user profile.
REM As SYSTEM this would fail to deploy and fail to read secrets.
REM
REM Restarts are expected and cheap: every restart mints a fresh tunnel hostname
REM and repoints the Worker at it, so a crashed tunnel self-heals rather than
REM leaving a stale origin behind.

setlocal
set "REPO=%~dp0.."
cd /d "%REPO%"

if not exist "%REPO%\logs" mkdir "%REPO%\logs"

set "PYTHONPATH=%REPO%\src"
echo [%DATE% %TIME%] starting gateway publish loop >> "%REPO%\logs\ngs_gateway.log"
"%REPO%\.venv\Scripts\python.exe" "%REPO%\tools\ngs_gateway_publish.py" >> "%REPO%\logs\ngs_gateway.log" 2>&1
echo [%DATE% %TIME%] gateway publish loop exited with %ERRORLEVEL% >> "%REPO%\logs\ngs_gateway.log"
endlocal

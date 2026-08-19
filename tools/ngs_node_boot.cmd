@echo off
REM Boot wrapper for the NGS node scheduled task.
REM
REM MUST run as the interactive user, never SYSTEM: keymaker encrypts secrets
REM with DPAPI bound to the user, so NGS_NODE_TOKEN is undecryptable from any
REM other identity and the node would come up deny-by-default (503 on every
REM data endpoint) with no obvious cause.
REM
REM Everything environment-shaped is resolved by ngs_node_serve.py at run time;
REM this wrapper only fixes the working directory and the interpreter.

setlocal
set "REPO=%~dp0.."
cd /d "%REPO%"

if not exist "%REPO%\logs" mkdir "%REPO%\logs"

echo [%DATE% %TIME%] starting NGS node >> "%REPO%\logs\ngs_node.log"
"%REPO%\.venv\Scripts\python.exe" "%REPO%\tools\ngs_node_serve.py" >> "%REPO%\logs\ngs_node.log" 2>&1
echo [%DATE% %TIME%] NGS node exited with %ERRORLEVEL% >> "%REPO%\logs\ngs_node.log"
endlocal

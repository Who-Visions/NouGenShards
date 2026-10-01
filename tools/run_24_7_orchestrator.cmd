@echo off
set "WORKSPACE=%USERPROFILE%\Outpost\NouGen"
set "LOG=%USERPROFILE%\.nougen\logs\orchestrator.log"
set "PYTHONUNBUFFERED=1"
cd /d "%WORKSPACE%" || exit /b 1

if "%1"=="windowless" goto :windowless
if "%1"=="bg" goto :windowless

:foreground
echo [%date% %time%] NouGen 24/7 Orchestrator starting (foreground) >> "%LOG%"
"%WORKSPACE%\.venv\Scripts\python.exe" tools\nougen_24_7_orchestrator.py
goto :eof

:windowless
echo [%date% %time%] NouGen 24/7 Orchestrator starting (pythonw windowless) >> "%LOG%"
start "" /b "%WORKSPACE%\.venv\Scripts\pythonw.exe" tools\nougen_24_7_orchestrator.py
echo [*] NouGen 24/7 Orchestrator launched windowless via pythonw.
echo [*] Log: %LOG%
goto :eof

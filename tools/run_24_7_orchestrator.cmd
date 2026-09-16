@echo off
set "WORKSPACE=C:\Users\super\Outpost\NouGen"
set "LOG=C:\Users\super\.nougen\logs\orchestrator.log"
set "PYTHONUNBUFFERED=1"
cd /d "%WORKSPACE%" || exit /b 1
echo [%date% %time%] NouGen 24/7 Orchestrator starting >> "%LOG%"
"%WORKSPACE%\.venv\Scripts\python.exe" tools\nougen_24_7_orchestrator.py >> "%LOG%" 2>&1
echo [%date% %time%] NouGen 24/7 Orchestrator exited with %errorlevel% >> "%LOG%"

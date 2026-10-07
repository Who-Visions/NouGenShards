@echo off
title NouGen CLI Console
cd /d C:\Users\super\Outpost\NouGen

REM Optional auto-update check (respects %NOUGEN_NO_AUTO_UPDATE% and --no-update)
if "%1"=="--no-update" goto skip_update
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\check_and_update.ps1
:skip_update

call .venv\Scripts\activate.bat
echo =======================================================
echo   NOUGEN CLI VIRTUAL ENVIRONMENT ACTIVE
echo =======================================================
nougen status
cmd.exe /k

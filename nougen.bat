@echo off
SETLOCAL EnableDelayedExpansion

:: 🪩 NouGenShards Windows Bootstrap Launcher
:: Architecture: 2-Year Horizon Self-Healing Substrate
:: Author: Who Visions LLC (Coach Apollo Build)

SET "TITLE=NouGenShards: Local Memory Substrate"
title %TITLE%

:: 1. Detect Python (Module 10: Integrate Constraints)
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [!] ERROR: Python not found on PATH.
    echo Please install Python 3.9+ from https://python.org
    pause
    exit /b 1
)

:: 2. Environment Ignition (Module 11: Transform Architecture)
IF NOT EXIST ".venv" (
    echo [*] Initializing isolated environment (.venv)...
    python -m venv .venv
    if !ERRORLEVEL! neq 0 (
        echo [!] Failed to create virtual environment. 
        pause
        exit /b 1
    )
)

:: 3. Dependency Hardening (Module 19: Stabilize Reasoning)
echo [*] Verifying substrate dependencies...
.venv\Scripts\python -m pip install -q --upgrade pip
.venv\Scripts\python -m pip install -q sqlalchemy mcp fastapi uvicorn .

:: 4. Executive Launch (Module 21: Orchestrate Convergence)
:: Pass all arguments to the unified binary
.venv\Scripts\python -m nougen_shards.cli %*

ENDLOCAL

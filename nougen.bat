@echo off
setlocal EnableExtensions DisableDelayedExpansion

:: ============================================================
::  NouGenShards Windows Bootstrap Launcher
::  Who Visions LLC
::
::  Safe to run from anywhere: double-click, shortcut, PATH,
::  or "Run as administrator" - it always operates inside the
::  repository folder, never the caller's working directory.
:: ============================================================

title NouGenShards: Local Memory Substrate

:: --- 0. Anchor to the script's own directory -----------------
pushd "%~dp0" || (
    echo [^^!] ERROR: Cannot enter script directory "%~dp0".
    exit /b 1
)

set "VPY=.venv\Scripts\python.exe"
set "EXITCODE=0"

:: --- 1. Locate a real Python 3.9+ ----------------------------
:: Prefer the py launcher; fall back to python on PATH. Running
:: "-c" also rejects the Microsoft Store stub, which fails when
:: given arguments instead of silently opening the Store.
set "PY_CMD="
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if not errorlevel 1 set "PY_CMD=py -3"

if not defined PY_CMD (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
    if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
    echo [^^!] ERROR: Python 3.9+ was not found.
    echo     Install it from https://python.org and check
    echo     "Add python.exe to PATH" during setup.
    set "EXITCODE=1"
    goto :finish_pause
)

:: --- 2. Fingerprint dependencies (pyproject.toml hash) -------
:: The marker file stores this hash so dependency changes in the
:: repo automatically trigger a reinstall instead of crashing on
:: stale environments.
set "DEPS_HASH="
for /f "skip=1 tokens=1 delims= " %%H in ('certutil -hashfile pyproject.toml SHA256 2^>nul') do (
    if not defined DEPS_HASH set "DEPS_HASH=%%H"
)
if not defined DEPS_HASH set "DEPS_HASH=unknown"

set "STORED_HASH="
if exist ".venv\.installed" set /p STORED_HASH=<".venv\.installed"

:: --- 3. Create or heal the virtual environment ---------------
if exist ".venv" if not exist "%VPY%" (
    echo [*] Detected a broken .venv - rebuilding it...
    rmdir /s /q ".venv"
)

if not exist ".venv" (
    echo [*] Initializing isolated environment ^(.venv^)...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo [^^!] ERROR: Failed to create the virtual environment.
        set "EXITCODE=1"
        goto :finish_pause
    )
    set "STORED_HASH="
)

:: --- 4. Install / refresh dependencies when needed -----------
if /i not "%STORED_HASH%"=="%DEPS_HASH%" (
    if defined STORED_HASH (
        echo [*] Dependencies changed - updating environment...
    ) else (
        echo [*] Installing substrate dependencies...
        echo     First run can take a few minutes - grab a coffee.
    )
    "%VPY%" -m pip install -q --upgrade pip
    "%VPY%" -m pip install -q .
    if errorlevel 1 (
        echo [^^!] ERROR: Dependency installation failed.
        echo     Re-run after checking your network, or inspect:
        echo     "%VPY%" -m pip install .
        set "EXITCODE=1"
        goto :finish_pause
    )
    >".venv\.installed" echo %DEPS_HASH%
)

:: --- 5. Launch the engine ------------------------------------
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
"%VPY%" -m nougen_shards.cli %*
set "EXITCODE=%ERRORLEVEL%"

:: --- 6. Exit etiquette ---------------------------------------
:: Keep the window open when double-clicked (no args) or when
:: something failed, so errors are actually readable.
if "%~1"=="" goto :finish_pause
if not "%EXITCODE%"=="0" goto :finish_pause
goto :finish

:finish_pause
echo.
pause

:finish
popd
endlocal & exit /b %EXITCODE%

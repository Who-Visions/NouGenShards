@echo off
rem NouGenTube daily harvest — roster sweep + capped drip backfill (idempotent).
rem Drip doctrine (wargames/drip-backfill.md): ONE run per day, global new-fetch cap,
rem targeted GM queue drains first, skip drip entirely if the sweep got rate-flagged.
cd /d "%~dp0.."
set PYTHONPATH=src
if "%NOUGEN_YT_DAYS%"=="" set NOUGEN_YT_DAYS=3
if "%NOUGEN_YT_DRIP_CAP%"=="" set NOUGEN_YT_DRIP_CAP=5
if "%NOUGEN_YT_DRIP_LOOKBACK%"=="" set NOUGEN_YT_DRIP_LOOKBACK=90

python tools\nougentube_batch.py --days %NOUGEN_YT_DAYS% --confirm >> transcripts\logs\harvest_daily.log 2>&1
if errorlevel 3 (
  echo drip skipped: sweep hit the rate limit today >> transcripts\logs\harvest_daily.log
  exit /b 3
)

rem Phase 0: GM-priority targeted queue (teacher cluster etc.) gets the budget first.
python tools\nougentube_pick.py --max-new %NOUGEN_YT_DRIP_CAP% --confirm >> transcripts\logs\harvest_daily.log 2>&1
if errorlevel 3 (
  echo channel drip skipped: queue drain hit the rate limit >> transcripts\logs\harvest_daily.log
  exit /b 3
)

rem Phase 1: rotating channel-archive drip under the same global cap.
python tools\nougentube_batch.py --days %NOUGEN_YT_DRIP_LOOKBACK% --max-new-total %NOUGEN_YT_DRIP_CAP% --confirm >> transcripts\logs\harvest_daily.log 2>&1

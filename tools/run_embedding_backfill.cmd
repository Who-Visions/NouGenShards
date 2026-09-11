@echo off
cd /d "%USERPROFILE%\Watchtower\NouGen\NouGenShards-push-main"
".venv\Scripts\python.exe" -u -m nougen_shards.embedding_backfill --vault "%USERPROFILE%\.nougen\shards" --execute --batch 64 >> "%USERPROFILE%\.nougen\embedding_backfill_20260906.log" 2>&1

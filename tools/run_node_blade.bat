@echo off
cd /d "C:\Users\super\Watchtower\NouGen\NouGenShards-push-main"
set USERPROFILE=C:\Users\super
set NOUGEN_HOME=C:\Users\super\.nougen
set PYTHONPATH=src;%PYTHONPATH%
set NOUGEN_VAULT_DIR=C:\Users\super\.nougen\shards
set NOUGEN_SECRETS_VAULT_DIR=C:\Users\super\.nougen\secrets
set NGS_NODE_TOKEN=oihMSih9J2qfdURVrZis_DY7wPANP6S9Z_K1PrZGgTo
"C:\Users\super\Watchtower\NouGen\NouGenShards-push-main\.venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 4444 >> "C:\Users\super\.nougen\logs\node_direct.log" 2>&1

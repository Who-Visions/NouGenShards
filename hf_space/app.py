"""Standalone entry for the WAL hallway (the node app mounts the same router)."""
from fastapi import FastAPI

from nougen_shards import wal_api

app = FastAPI(title="NouGen shard WAL", version="0.2.0")
app.include_router(wal_api.router)


@app.on_event("startup")
def _commits() -> None:
    wal_api.start_dataset_commits()

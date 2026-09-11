from __future__ import annotations

import asyncio
import uuid
from typing import Any
import httpx

from .models import FleetCoverage, VaultPeer, VaultId
from .dedupe import logical_hash


async def fetch_local_coverage(
    peer: VaultPeer,
    token: str,
    correlation_id: str,
) -> tuple[str, bool, dict[str, Any]]:
    headers = {
        "Authorization": f"Bearer {token}",
        "X-NouGen-Correlation-ID": correlation_id,
        "X-NouGen-Federated-Hop": "1",
    }

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(
                f"{peer.base_url}{peer.coverage_path}",
                headers=headers,
            )
            r.raise_for_status()
            body = r.json()
        return peer.vault_id.value, True, body
    except Exception as exc:
        return peer.vault_id.value, False, {
            "error": f"{type(exc).__name__}: {exc}",
        }


async def fleet_coverage(
    peers: dict[VaultId, VaultPeer],
    token: str,
) -> FleetCoverage:
    cid = str(uuid.uuid4())
    results = await asyncio.gather(
        *(fetch_local_coverage(peer, token, cid) for peer in peers.values())
    )

    answered = sum(1 for _, ok, _ in results if ok)
    expected = len(results)
    complete = answered == expected

    per_vault: dict[str, dict[str, Any]] = {}
    all_shards: list[dict[str, Any]] = []

    for vault_id, ok, body in results:
        if not ok:
            per_vault[vault_id] = {
                "reachable": False,
                "error": body.get("error"),
            }
            continue

        per_vault[vault_id] = {
            "reachable": True,
            "machine_id": body.get("machine_id"),
            "db_present": body.get("db_present"),
            "db_expected": body.get("db_expected", 9),
            "shard_count": body.get("shard_count"),
            "newest_timestamp": body.get("newest_timestamp"),
            "oldest_timestamp": body.get("oldest_timestamp"),
        }

        if isinstance(body.get("shards"), list):
            for shard in body["shards"]:
                shard = dict(shard)
                shard["source_vault"] = vault_id
                all_shards.append(shard)

    dedup_total = None
    if complete and all_shards:
        dedup_total = len({logical_hash(s) for s in all_shards})

    return FleetCoverage(
        complete=complete,
        cannot_determine=not complete,
        vaults_expected=expected,
        vaults_answered=answered,
        deduplicated_fleet_total=dedup_total,
        per_vault=per_vault,
    )

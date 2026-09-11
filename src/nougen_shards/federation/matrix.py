from __future__ import annotations

import asyncio
from time import perf_counter

from .models import MatrixCell, VaultId, VaultPeer


async def run_cell(source_client, target: VaultPeer, sentinel: str) -> MatrixCell:
    started = perf_counter()
    try:
        health = await source_client.direct_health(target.vault_id)
        recall = await source_client.direct_local_recall(target.vault_id, sentinel, 3)

        identity_ok = health.get("vault_id") == target.vault_id.value
        sentinel_ok = any(sentinel in str(h) for h in recall.get("hits", []))
        ok = bool(health.get("healthy")) and identity_ok and sentinel_ok

        return MatrixCell(
            source=source_client.vault_id,
            target=target.vault_id.value,
            ok=ok,
            identity_ok=identity_ok,
            sentinel_ok=sentinel_ok,
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )
    except Exception as exc:
        return MatrixCell(
            source=source_client.vault_id,
            target=target.vault_id.value,
            ok=False,
            identity_ok=False,
            sentinel_ok=False,
            latency_ms=round((perf_counter() - started) * 1000, 2),
            error=f"{type(exc).__name__}: {exc}",
        )


async def run_matrix(source_clients, peers, sentinels):
    tasks = []
    for source in source_clients:
        for peer in peers.values():
            tasks.append(
                run_cell(
                    source,
                    peer,
                    sentinels[peer.vault_id.value],
                )
            )

    cells = await asyncio.gather(*tasks)
    return cells


def assert_matrix_green(cells: list[MatrixCell]):
    failed = [c for c in cells if not c.ok]
    if failed:
        detail = "\n".join(
            f"{c.source}->{c.target} FAIL {c.error or ''}"
            for c in failed
        )
        raise RuntimeError("3x3 federation matrix failed:\n" + detail)

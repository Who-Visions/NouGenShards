from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

import httpx

from .models import VaultPeer, VaultHealth, VaultRecallResult, PeerState


class FederationClient:
    def __init__(self, token: str):
        self.token = token
        self.connect_timeout = 1.5
        self.read_timeout = 3.5

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect_timeout,
            read=self.read_timeout,
            write=self.read_timeout,
            pool=self.connect_timeout,
        )

    def _headers(self, correlation_id: str) -> dict[str, str]:
        headers = {
            "X-NouGen-Correlation-ID": correlation_id,
            "X-NouGen-Federated-Hop": "1",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            headers["X-NGS-Token"] = self.token
        return headers

    async def health(self, peer: VaultPeer, correlation_id: str) -> VaultHealth:
        started = perf_counter()
        endpoint = f"{peer.base_url}{peer.health_path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                r = await client.get(endpoint, headers=self._headers(correlation_id))
                r.raise_for_status()
                body = r.json()

            latency_ms = round((perf_counter() - started) * 1000, 2)
            healthy = bool(body.get("healthy", False))
            current = bool(body.get("current", healthy))
            verified = body.get("vault_id") == peer.vault_id.value

            state = PeerState.HEALTHY.value if healthy else PeerState.DEGRADED.value

            return VaultHealth(
                vault_id=peer.vault_id.value,
                reachable=True,
                healthy=healthy,
                current=current,
                verified=verified,
                state=state,
                latency_ms=latency_ms,
                endpoint=endpoint,
                machine_id=body.get("machine_id"),
                instance_id=body.get("instance_id"),
                shard_count=body.get("shard_count"),
                newest_timestamp=body.get("newest_timestamp"),
                db_count=body.get("db_count"),
                db_expected=body.get("db_expected", 9),
            )
        except httpx.TimeoutException as exc:
            return VaultHealth(
                vault_id=peer.vault_id.value,
                reachable=False,
                healthy=False,
                current=False,
                verified=False,
                state=PeerState.DOWN.value,
                latency_ms=round((perf_counter() - started) * 1000, 2),
                endpoint=endpoint,
                error_class="timeout",
                error=str(exc),
            )
        except httpx.HTTPStatusError as exc:
            return VaultHealth(
                vault_id=peer.vault_id.value,
                reachable=True,
                healthy=False,
                current=False,
                verified=False,
                state=PeerState.DEGRADED.value,
                latency_ms=round((perf_counter() - started) * 1000, 2),
                endpoint=endpoint,
                error_class="http_error",
                error=str(exc),
            )
        except Exception as exc:
            return VaultHealth(
                vault_id=peer.vault_id.value,
                reachable=False,
                healthy=False,
                current=False,
                verified=False,
                state=PeerState.DOWN.value,
                latency_ms=round((perf_counter() - started) * 1000, 2),
                endpoint=endpoint,
                error_class=type(exc).__name__,
                error=str(exc),
            )

    async def recall(
        self,
        peer: VaultPeer,
        query: str,
        limit: int,
        correlation_id: str,
    ) -> VaultRecallResult:
        started = perf_counter()
        endpoint = f"{peer.base_url}{peer.recall_path}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                r = await client.post(
                    endpoint,
                    headers=self._headers(correlation_id),
                    json={"query": query, "limit": limit, "scope": "local"},
                )
                r.raise_for_status()
                body: dict[str, Any] = r.json()

            hits = list(body.get("hits") or [])
            for hit in hits:
                hit["source_vault"] = peer.vault_id.value
                hit.setdefault("source_machine", body.get("machine_id"))

            return VaultRecallResult(
                vault_id=peer.vault_id.value,
                ok=True,
                latency_ms=round((perf_counter() - started) * 1000, 2),
                hits=hits,
            )

        except httpx.TimeoutException as exc:
            return VaultRecallResult(
                vault_id=peer.vault_id.value,
                ok=False,
                latency_ms=round((perf_counter() - started) * 1000, 2),
                hits=[],
                error_class="timeout",
                error=str(exc),
            )
        except httpx.HTTPStatusError as exc:
            return VaultRecallResult(
                vault_id=peer.vault_id.value,
                ok=False,
                latency_ms=round((perf_counter() - started) * 1000, 2),
                hits=[],
                error_class="http_error",
                error=str(exc),
            )
        except Exception as exc:
            return VaultRecallResult(
                vault_id=peer.vault_id.value,
                ok=False,
                latency_ms=round((perf_counter() - started) * 1000, 2),
                hits=[],
                error_class=type(exc).__name__,
                error=str(exc),
            )

from __future__ import annotations

import asyncio
import uuid

from .client import FederationClient
from .dedupe import dedupe_federated_hits
from .models import FleetHealth, FederatedRecall, VaultId, VaultPeer


class FederationService:
    def __init__(
        self,
        peers: dict[VaultId, VaultPeer],
        client: FederationClient,
    ):
        self.peers = peers
        self.client = client

    async def health(self, correlation_id: str | None = None) -> FleetHealth:
        cid = correlation_id or str(uuid.uuid4())
        results = await asyncio.gather(
            *(self.client.health(peer, cid) for peer in self.peers.values())
        )

        expected = len(results)
        reachable = sum(1 for r in results if r.reachable)
        healthy = sum(1 for r in results if r.healthy)
        current = sum(1 for r in results if r.current)
        verified = sum(1 for r in results if r.verified)

        complete = reachable == expected
        all_good = (
            complete
            and healthy == expected
            and current == expected
            and verified == expected
        )

        return FleetHealth(
            healthy=all_good,
            reachable=reachable > 0,
            complete=complete,
            current=current == expected,
            verified=verified == expected,
            cannot_determine=not complete,
            vaults_expected=expected,
            vaults_reachable=reachable,
            vaults_healthy=healthy,
            vaults_current=current,
            vaults_verified=verified,
            vaults=results,
        )

    async def recall(
        self,
        query: str,
        limit: int = 10,
        correlation_id: str | None = None,
    ) -> FederatedRecall:
        cid = correlation_id or str(uuid.uuid4())

        results = await asyncio.gather(
            *(
                self.client.recall(peer, query, limit, cid)
                for peer in self.peers.values()
            )
        )

        expected = len(results)
        answered = sum(1 for r in results if r.ok)
        complete = answered == expected

        hits = []
        for result in results:
            hits.extend(result.hits)

        hits = dedupe_federated_hits(hits)
        hits.sort(key=lambda h: float(h.get("score") or 0), reverse=True)

        return FederatedRecall(
            query=query,
            complete=complete,
            cannot_determine=not complete,
            vaults_expected=expected,
            vaults_answered=answered,
            correlation_id=cid,
            hits=hits[:limit],
            per_vault=results,
        )

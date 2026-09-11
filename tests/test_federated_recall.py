import pytest
from nougen_shards.federation.models import VaultId, VaultPeer, VaultRecallResult
from nougen_shards.federation.service import FederationService


class FakeRecallClient:
    def __init__(self):
        self._recall_responses = {}

    def set_recall(self, vault_id: str, hits: list):
        self._recall_responses[vault_id] = VaultRecallResult(
            vault_id=vault_id,
            ok=True,
            latency_ms=12.5,
            hits=hits,
        )

    def set_timeout(self, vault_id: str):
        self._recall_responses[vault_id] = VaultRecallResult(
            vault_id=vault_id,
            ok=False,
            latency_ms=1500.0,
            hits=[],
            error_class="timeout",
            error="Connection timed out",
        )

    async def recall(self, peer: VaultPeer, query: str, limit: int, correlation_id: str):
        res = self._recall_responses[peer.vault_id.value]
        # Stamp source_vault and source_machine if hits exist
        hits = list(res.hits)
        for h in hits:
            h["source_vault"] = peer.vault_id.value
            h.setdefault("source_machine", f"{peer.vault_id.value}-node")
        return VaultRecallResult(
            vault_id=res.vault_id,
            ok=res.ok,
            latency_ms=res.latency_ms,
            hits=hits,
            error_class=res.error_class,
            error=res.error,
        )


@pytest.fixture
def fake_clients():
    return FakeRecallClient()


@pytest.fixture
def service(fake_clients):
    peers = {
        VaultId.BLADE: VaultPeer(VaultId.BLADE, "https://blade.nougenai.com"),
        VaultId.PHOEBUS: VaultPeer(VaultId.PHOEBUS, "https://phoebus.nougenai.com"),
        VaultId.WHOART: VaultPeer(VaultId.WHOART, "https://whoart.nougenai.com"),
    }
    return FederationService(peers=peers, client=fake_clients)


@pytest.mark.asyncio
async def test_timeout_is_not_absence(service, fake_clients):
    fake_clients.set_recall("blade", [{"id": 1, "content": "x", "score": 0.9}])
    fake_clients.set_recall("phoebus", [])
    fake_clients.set_timeout("whoart")

    result = await service.recall("x", 10, "cid")

    assert result.complete is False
    assert result.cannot_determine is True
    assert result.vaults_answered == 2


@pytest.mark.asyncio
async def test_source_provenance_survives(service, fake_clients):
    fake_clients.set_recall("blade", [{"id": 7, "content": "canon", "score": 0.8}])
    fake_clients.set_recall("phoebus", [{"id": 7, "content": "canon", "score": 0.7}])
    fake_clients.set_recall("whoart", [])

    result = await service.recall("canon", 10, "cid")

    assert result.complete is True
    hit = result.hits[0]
    assert hit["replicas"]
    assert {r["vault"] for r in hit["replicas"]} >= {"blade", "phoebus"}

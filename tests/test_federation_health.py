import pytest
from nougen_shards.federation.models import VaultId, VaultPeer
from nougen_shards.federation.service import FederationService


class FakeClient:
    def __init__(self):
        self._health_responses = {}

    def set_health(self, vault_id: str, reachable: bool, healthy: bool, current: bool, verified: bool):
        from nougen_shards.federation.models import VaultHealth, PeerState
        state = PeerState.HEALTHY.value if healthy else PeerState.DEGRADED.value
        self._health_responses[vault_id] = VaultHealth(
            vault_id=vault_id,
            reachable=reachable,
            healthy=healthy,
            current=current,
            verified=verified,
            state=state,
            latency_ms=10.0,
            endpoint=f"https://{vault_id}.nougenai.com/v1/health/local",
        )

    def set_timeout(self, vault_id: str):
        from nougen_shards.federation.models import VaultHealth, PeerState
        self._health_responses[vault_id] = VaultHealth(
            vault_id=vault_id,
            reachable=False,
            healthy=False,
            current=False,
            verified=False,
            state=PeerState.DOWN.value,
            latency_ms=1500.0,
            endpoint=f"https://{vault_id}.nougenai.com/v1/health/local",
            error_class="timeout",
            error="Connection timed out",
        )

    async def health(self, peer: VaultPeer, correlation_id: str):
        return self._health_responses[peer.vault_id.value]


@pytest.fixture
def fake_clients():
    return FakeClient()


@pytest.fixture
def service(fake_clients):
    peers = {
        VaultId.BLADE: VaultPeer(VaultId.BLADE, "https://blade.nougenai.com"),
        VaultId.PHOEBUS: VaultPeer(VaultId.PHOEBUS, "https://phoebus.nougenai.com"),
        VaultId.WHOART: VaultPeer(VaultId.WHOART, "https://whoart.nougenai.com"),
    }
    return FederationService(peers=peers, client=fake_clients)


@pytest.mark.asyncio
async def test_3_of_3_is_green(service, fake_clients):
    fake_clients.set_health("blade", reachable=True, healthy=True, current=True, verified=True)
    fake_clients.set_health("phoebus", reachable=True, healthy=True, current=True, verified=True)
    fake_clients.set_health("whoart", reachable=True, healthy=True, current=True, verified=True)

    result = await service.health("test-cid")

    assert result.healthy is True
    assert result.complete is True
    assert result.current is True
    assert result.verified is True
    assert result.cannot_determine is False
    assert result.vaults_healthy == 3


@pytest.mark.asyncio
async def test_1_of_3_cannot_be_green(service, fake_clients):
    fake_clients.set_health("blade", reachable=True, healthy=True, current=True, verified=True)
    fake_clients.set_timeout("phoebus")
    fake_clients.set_timeout("whoart")

    result = await service.health("test-cid")

    assert result.healthy is False
    assert result.complete is False
    assert result.cannot_determine is True
    assert result.vaults_reachable == 1


@pytest.mark.asyncio
async def test_identity_mismatch_blocks_verified(service, fake_clients):
    fake_clients.set_health(
        "blade",
        reachable=True,
        healthy=True,
        current=True,
        verified=False,
    )
    fake_clients.set_health("phoebus", reachable=True, healthy=True, current=True, verified=True)
    fake_clients.set_health("whoart", reachable=True, healthy=True, current=True, verified=True)

    result = await service.health("test-cid")

    assert result.complete is True
    assert result.healthy is False
    assert result.verified is False

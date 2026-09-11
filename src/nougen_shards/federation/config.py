from __future__ import annotations

import os
from .models import VaultId, VaultPeer, NodeIdentity


ENV_KEYS = {
    VaultId.BLADE: "NOUGEN_VAULT_BLADE_URL",
    VaultId.PHOEBUS: "NOUGEN_VAULT_PHOEBUS_URL",
    VaultId.WHOART: "NOUGEN_VAULT_WHOART_URL",
}


def load_vault_peers() -> dict[VaultId, VaultPeer]:
    peers: dict[VaultId, VaultPeer] = {}
    missing: list[str] = []

    for vault_id, key in ENV_KEYS.items():
        value = (os.getenv(key) or "").strip().rstrip("/")
        if not value:
            missing.append(key)
            continue
        peers[vault_id] = VaultPeer(vault_id=vault_id, base_url=value)

    if missing:
        raise RuntimeError(
            "Incomplete 3-vault topology. Missing env vars: " + ", ".join(missing)
        )

    if len(peers) != 3:
        raise RuntimeError(f"Expected exactly 3 vault peers, got {len(peers)}")

    return peers


def load_identity() -> NodeIdentity:
    machine_id = (os.getenv("NOUGEN_MACHINE_ID") or "").strip()
    vault_raw = (os.getenv("NOUGEN_VAULT_ID") or "").strip().lower()
    instance_id = (os.getenv("NOUGEN_INSTANCE_ID") or "").strip()

    if not machine_id or not vault_raw or not instance_id:
        raise RuntimeError("NOUGEN_MACHINE_ID, NOUGEN_VAULT_ID, NOUGEN_INSTANCE_ID are required")

    try:
        vault_id = VaultId(vault_raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid NOUGEN_VAULT_ID={vault_raw}") from exc

    return NodeIdentity(
        machine_id=machine_id,
        vault_id=vault_id,
        instance_id=instance_id,
    )

"""Federated Retrieval Engine. Merges local substrate, external DBs, and cloud nodes."""
import logging
from . import core
from .connectors.sql import query_external_dbs
from .connectors.cloud import query_cloud_shards
from .connectors.local_vault import query_local_vaults
from . import keymaker
from typing import List, Optional

logger = logging.getLogger(__name__)

def federated_retrieve(query: str, limit: int = 3, query_embedding: Optional[List[float]] = None,
                       domain_key: Optional[str] = None,
                       sweep_report: Optional[dict] = None) -> list:
    """
    Module 8: Combine Compatible Systems.
    Polls local Shard substrate, external DBs, and remote cloud nodes.
    """
    # 1. Get Local Shards (weighted relevance blend)
    # Guard the local lane too: a raising local retrieve must degrade to []
    # so federation still returns whatever remote lanes provide.
    try:
        local_results = core.retrieve(query, limit=limit, query_embedding=query_embedding, domain_key=domain_key)
    except Exception as exc:  # noqa: BLE001 - degrade, don't crash federation
        logger.warning("local retrieve skipped (federation continues): %s: %s",
                       type(exc).__name__, exc)
        local_results = []

    # Existing keymaker configuration belongs to the owner. A tenant must not
    # inherit those read-through lanes and merge owner material into its recall.
    if core.active_tenant_id() == "owner":
        external_configs = keymaker.list_external_dbs()
        cloud_configs = keymaker.list_cloud_nodes()
    else:
        external_configs = []
        cloud_configs = []

    # 3. Query External DBs if configured.
    # Remote sources must never abort federation: a raising external/cloud
    # source is logged and skipped so local_results always survive.
    # (Module 10: Graceful Degradation)
    external_results = []
    if external_configs:
        try:
            external_results = query_external_dbs(query, external_configs, limit=limit)
        except Exception as exc:  # noqa: BLE001 - degrade, don't crash federation
            logger.warning("external DBs skipped (federation continues): %s: %s",
                           type(exc).__name__, exc)
            external_results = []

    # 4. Query Cloud Nodes if configured
    cloud_results = []
    if cloud_configs:
        try:
            cloud_results = query_cloud_shards(query, cloud_configs, limit=limit)
        except Exception as exc:  # noqa: BLE001 - degrade, don't crash federation
            logger.warning("cloud nodes skipped (federation continues): %s: %s",
                           type(exc).__name__, exc)
            cloud_results = []

    # 4b. Query sibling SQLite vaults on this machine. Same degradation contract
    # as every other remote source: a missing file or renamed table drops that
    # vault, never the sweep.
    vault_results = []
    vault_configs = keymaker.list_local_vaults()
    if vault_configs:
        try:
            vault_results = query_local_vaults(query, vault_configs, limit=limit,
                                               sweep_report=sweep_report)
        except Exception as exc:  # noqa: BLE001 - degrade, don't crash federation
            logger.warning("local vaults skipped (federation continues): %s: %s",
                           type(exc).__name__, exc)
            vault_results = []

    # 5. Merge and re-rank via Reciprocal Rank Fusion (RRF)
    # (Module 21: Orchestrate Convergence)
    # Plain RRF is correct here as long as each lane arrives ranked best-first —
    # RRF fuses by POSITION, so a lane that hands it unsorted rows squanders its
    # slots. query_local_vaults sorts across all 36 vaults before returning for
    # exactly this reason; that is what stops one arbitrary vault from owning the
    # merged top-N, not any change to the fusion itself.
    combined = core.reciprocal_rank_fusion(
        [local_results, external_results, cloud_results, vault_results], k=60)

    return combined[:limit]

"""Federated Retrieval Engine. Merges local substrate, external DBs, and cloud nodes."""
import logging
from . import core
from .connectors.sql import query_external_dbs
from .connectors.cloud import query_cloud_shards
from . import keymaker
from typing import List, Optional

logger = logging.getLogger(__name__)

def federated_retrieve(query: str, limit: int = 3, query_embedding: Optional[List[float]] = None,
                       domain_key: Optional[str] = None) -> list:
    """
    Module 8: Combine Compatible Systems.
    Polls local Shard substrate, external DBs, and remote cloud nodes.
    """
    # 1. Get Local Shards (weighted relevance blend)
    local_results = core.retrieve(query, limit=limit, query_embedding=query_embedding, domain_key=domain_key)

    # 2. Get Configs from Keymaker
    external_configs = keymaker.list_external_dbs()
    cloud_configs = keymaker.list_cloud_nodes()

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

    # 5. Merge and re-rank via Reciprocal Rank Fusion (RRF)
    # (Module 21: Orchestrate Convergence)
    combined = core.reciprocal_rank_fusion([local_results, external_results, cloud_results], k=60)

    return combined[:limit]

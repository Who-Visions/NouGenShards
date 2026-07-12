"""Federated Retrieval Engine. Merges local substrate, external DBs, and cloud nodes."""
import logging
import os
from . import core
from .connectors.sql import query_external_dbs
from .connectors.cloud import query_cloud_shards
from . import keymaker
from typing import List, Optional

logger = logging.getLogger(__name__)

# Auto-embed queries so the vector lane works for callers that don't compute an
# embedding themselves (the MCP recall path passed None, leaving semantic
# scoring, the ANN index, and MMR similarity dead for agents). Must be the same
# model family the backfill wrote with, or the vector space won't line up.
AUTO_EMBED = os.environ.get("NOUGEN_AUTO_EMBED", "1") == "1"
EMBED_MODEL = os.environ.get("NOUGEN_EMBED_MODEL", "nomic-embed-text")
_EMBED_CLIENT = None  # process-cached; False once probed dead


def _auto_query_embedding(query: str) -> Optional[List[float]]:
    """Best-effort local embedding for the query. Never raises; None on any miss."""
    global _EMBED_CLIENT  # pylint: disable=global-statement
    if not AUTO_EMBED:
        return None
    if _EMBED_CLIENT is None:
        try:
            from .models_client import OllamaClient  # pylint: disable=import-outside-toplevel
            client = OllamaClient()
            _EMBED_CLIENT = client if client.is_alive() else False
        except Exception:  # noqa: BLE001 - degrade to keyword-only retrieval
            _EMBED_CLIENT = False
    if not _EMBED_CLIENT:
        return None
    try:
        vec = _EMBED_CLIENT.embed(EMBED_MODEL, query)
        return vec or None
    except Exception:  # noqa: BLE001
        return None


def federated_retrieve(query: str, limit: int = 3, query_embedding: Optional[List[float]] = None,
                       domain_key: Optional[str] = None) -> list:
    """
    Module 8: Combine Compatible Systems.
    Polls local Shard substrate, external DBs, and remote cloud nodes.
    """
    if query_embedding is None:
        query_embedding = _auto_query_embedding(query)

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
    rrf_k = int(os.environ.get("NOUGEN_RRF_K", "60"))
    combined = core.reciprocal_rank_fusion([local_results, external_results, cloud_results], k=rrf_k)

    return combined[:limit]

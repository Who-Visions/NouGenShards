"""Federated Retrieval Engine. Merges local substrate, external DBs, and cloud nodes."""
import logging
import os
from . import core


def _confidence_gate(rows: list) -> list:
    """Drop low-confidence vault rows before the RRF merge.

    RRF fuses by position only, so a lane returning one noisy row hands it the
    same 1/(k+1) as another lane's best hit — measured 2026-08-27 as a 25k-char
    raw doc at rank 1. local_vault scores its own rows in [0.05, 1.0] (base
    0.45; below that = noise-penalized, no title hit); such rows are dropped
    here rather than laundered into consensus. Env-first; the literal is the
    fallback.
    """
    floor = float(os.environ.get("NOUGEN_VAULT_MIN_SCORE", "0.45"))
    return [r for r in rows if (r.get("final_score") or 0.0) >= floor]
from .connectors.sql import query_external_dbs
from .connectors.cloud import query_cloud_shards
from .connectors.local_vault import query_local_vaults
from . import keymaker
from typing import List, Optional

logger = logging.getLogger(__name__)

import concurrent.futures

def federated_retrieve(query: str, limit: int = 3, query_embedding: Optional[List[float]] = None,
                       domain_key: Optional[str] = None,
                       sweep_report: Optional[dict] = None) -> list:
    """
    Module 8: Combine Compatible Systems (Parallel Multi-Lane Execution).
    Polls local Shard substrate, external DBs, sibling vaults, and remote cloud nodes concurrently.
    """
    local_results = []
    external_results = []
    cloud_results = []
    vault_results = []

    # Filter tenant access boundaries
    if core.active_tenant_id() == "owner":
        external_configs = keymaker.list_external_dbs()
        cloud_configs = keymaker.list_cloud_nodes()
    else:
        external_configs = []
        cloud_configs = []
    vault_configs = keymaker.list_local_vaults()

    def _fetch_local():
        try:
            return core.retrieve(query, limit=limit, query_embedding=query_embedding, domain_key=domain_key)
        except Exception as exc:
            logger.warning("local retrieve skipped: %s: %s", type(exc).__name__, exc)
            return []

    def _fetch_external():
        if not external_configs:
            return []
        try:
            return query_external_dbs(query, external_configs, limit=limit)
        except Exception as exc:
            logger.warning("external DBs skipped: %s: %s", type(exc).__name__, exc)
            return []

    def _fetch_cloud():
        if not cloud_configs:
            return []
        try:
            return query_cloud_shards(query, cloud_configs, limit=limit)
        except Exception as exc:
            logger.warning("cloud nodes skipped: %s: %s", type(exc).__name__, exc)
            return []

    def _fetch_vaults():
        if not vault_configs:
            return []
        try:
            return query_local_vaults(query, vault_configs, limit=limit, sweep_report=sweep_report)
        except Exception as exc:
            logger.warning("local vaults skipped: %s: %s", type(exc).__name__, exc)
            return []

    # Parallel lane execution across threads (preserve ContextVar tenant isolation)
    from contextvars import copy_context
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        f_local = executor.submit(copy_context().run, _fetch_local)
        f_external = executor.submit(copy_context().run, _fetch_external)
        f_cloud = executor.submit(copy_context().run, _fetch_cloud)
        f_vaults = executor.submit(copy_context().run, _fetch_vaults)

        local_results = f_local.result()
        external_results = f_external.result()
        cloud_results = f_cloud.result()
        vault_results = f_vaults.result()

    vault_results = _confidence_gate(vault_results)

    # Merge and re-rank via Reciprocal Rank Fusion (RRF), with per-lane trust
    # weights: the local grid is curated agent memory; vault lanes are raw
    # document stores whose rank-1 must not tie the grid's rank-1 (measured
    # 2026-08-27: a 25k-char shader spec outranked the root-cause shard the
    # query was about). Env-first as "local,external,cloud,vault"; the literal
    # is the fallback.
    raw_weights = os.environ.get("NOUGEN_RRF_LANE_WEIGHTS", "1.0,0.7,0.7,0.5")
    try:
        lane_weights = [float(w) for w in raw_weights.split(",")][:4]
    except ValueError:
        logger.warning("bad NOUGEN_RRF_LANE_WEIGHTS %r; using defaults", raw_weights)
        lane_weights = [1.0, 0.7, 0.7, 0.5]
    combined = core.reciprocal_rank_fusion(
        [local_results, external_results, cloud_results, vault_results], k=60,
        weights=lane_weights)

    return combined[:limit]

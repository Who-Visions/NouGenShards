"""Federated Retrieval Engine. Merges local substrate, external DBs, and cloud nodes."""
import logging
from . import core
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
    import os as _os

    # Shared wall-clock deadline: a recall must return SOMETHING before the
    # caller's transport gives up (MCP connectors were timing out while lanes
    # dawdled). Lanes that miss the deadline are skipped with a log line and
    # the partial answer ships. Env-first (Rule 0.2), logged fallback.
    try:
        deadline_s = float(_os.environ.get("NOUGEN_RECALL_DEADLINE_S", "20.0"))
    except ValueError:
        logger.warning("NOUGEN_RECALL_DEADLINE_S invalid; falling back to 20.0")
        deadline_s = 20.0

    import time as _time
    started = _time.monotonic()

    def _lane_result(future, name, default):
        remaining = deadline_s - (_time.monotonic() - started)
        try:
            return future.result(timeout=max(0.1, remaining))
        except concurrent.futures.TimeoutError:
            logger.warning("federated lane %r missed the %.1fs recall deadline; skipped",
                           name, deadline_s)
            future.cancel()
            return default

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    try:
        f_local = executor.submit(copy_context().run, _fetch_local)
        f_external = executor.submit(copy_context().run, _fetch_external)
        f_cloud = executor.submit(copy_context().run, _fetch_cloud)
        f_vaults = executor.submit(copy_context().run, _fetch_vaults)

        local_results = _lane_result(f_local, "local", [])
        external_results = _lane_result(f_external, "external", [])
        cloud_results = _lane_result(f_cloud, "cloud", [])
        vault_results = _lane_result(f_vaults, "vaults", [])
    finally:
        # Don't block on stragglers: a lane past the deadline finishes (or
        # dies) on its own thread while the partial answer returns now.
        executor.shutdown(wait=False)

    # Merge via WEIGHTED Reciprocal Rank Fusion. The core grid is the curated
    # memory substrate; external DBs / cloud peers / registered local vaults
    # are opportunistic corpora (code indexes, doc dumps). Equal weighting let
    # a filename row from a code-index vault tie the best core shard at the
    # same rank (measured 2026-08-30: top hit 'AuthContext.tsx' over real
    # shards). Core stays 1.0; the side lanes get NOUGEN_FED_LANE_WEIGHT.
    try:
        lane_weight = float(_os.environ.get("NOUGEN_FED_LANE_WEIGHT", "0.35"))
    except ValueError:
        logger.warning("NOUGEN_FED_LANE_WEIGHT invalid; falling back to 0.35")
        lane_weight = 0.35
    combined = core.reciprocal_rank_fusion(
        [local_results, external_results, cloud_results, vault_results], k=60,
        weights=[1.0, lane_weight, lane_weight, lane_weight])

    return combined[:limit]

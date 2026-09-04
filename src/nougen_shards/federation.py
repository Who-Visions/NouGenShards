"""Federated Retrieval Engine. Merges local substrate, external DBs, and cloud nodes."""
import logging
import os
import threading
from . import core
from .connectors.sql import query_external_dbs
from .connectors.cloud import query_cloud_shards
from .connectors.local_vault import query_local_vaults
from . import keymaker
from typing import List, Optional

logger = logging.getLogger(__name__)

#: ONE shared pool for every federated lane call, for the life of the process.
#:
#: This used to be a fresh ThreadPoolExecutor per call, closed with
#: `shutdown(wait=False)`. That does not stop running threads - it only
#: declines to block on them - so every recall whose lane overran the deadline
#: left its worker thread alive and unreferenced, with nothing bounding how
#: many accumulated. Lanes DO overrun routinely (an unreachable local vault,
#: a cloud peer returning 502), so a long-lived server bled threads on a
#: steady drip.
#:
#: Measured 2026-08-31 on a node that had been serving ~8h: 7,077 threads,
#: 28,846s CPU, and HTTP dead on every path while the OS still reported the
#: process as responding - the async loop was starved of capacity to accept,
#: which is why `netstat` showed a healthy LISTENING socket the whole time.
#: The same node wedged three times in one evening with different memory
#: profiles (1.7GB, 59GB, 4.4GB), which is what finally ruled memory out as
#: the cause: the constant across all three was thread count, not bytes.
#:
#: A shared pool makes stragglers self-limiting. They occupy a slot until they
#: finish and then free it, so the ceiling is `max_workers` rather than
#: unbounded. Sized generously because a blocked slot delays a lane rather
#: than failing it, and env-first per Rule 0.2.
_LANE_EXECUTOR = None
_LANE_EXECUTOR_LOCK = threading.Lock()


def _lane_pool_size() -> int:
    try:
        return max(4, int(os.environ.get("NOUGEN_FED_LANE_POOL", "16")))
    except ValueError:
        return 16


def _lane_executor():
    """The process-wide lane pool, created once."""
    global _LANE_EXECUTOR  # pylint: disable=global-statement
    if _LANE_EXECUTOR is None:
        with _LANE_EXECUTOR_LOCK:
            if _LANE_EXECUTOR is None:
                _LANE_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
                    max_workers=_lane_pool_size(),
                    thread_name_prefix="nougen-fed-lane")
    return _LANE_EXECUTOR

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

    def _record_lane(name, status, rows):
        """Per-lane elapsed and row count, for tuning the deadline on evidence.

        The deadline was argued about for a day on end-to-end latency alone,
        which cannot say WHICH lane was slow or whether it returned anything.
        Recorded here because this is the only place that knows both.
        """
        if sweep_report is None:
            return
        sweep_report.setdefault("lanes", {})[name] = {
            "status": status,
            "elapsed_s": round(_time.monotonic() - started, 3),
            "rows": rows,
        }

    def _lane_result(future, name, default):
        remaining = deadline_s - (_time.monotonic() - started)
        try:
            out = future.result(timeout=max(0.1, remaining))
        except concurrent.futures.TimeoutError:
            logger.warning("federated lane %r missed the %.1fs recall deadline; skipped",
                           name, deadline_s)
            future.cancel()
            # A skipped lane returns its empty default, which merges exactly
            # like a lane that genuinely matched nothing. Measured 2026-09-04:
            # a recall that overran the deadline came back HTTP 200 with a
            # 2-byte body, indistinguishable from "no matches" - silent recall
            # loss that no caller could detect even in principle. Record it so
            # the drop is at least observable; the log line above is not, since
            # callers do not read our logs.
            if sweep_report is not None:
                sweep_report.setdefault("lanes_timed_out", []).append(name)
                sweep_report["deadline_s"] = deadline_s
                sweep_report["deadline_exceeded"] = True
                _record_lane(name, "timeout", None)
            return default
        _record_lane(name, "ok", len(out) if out is not None else 0)
        return out

    executor = _lane_executor()
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
        # Deliberately NOT shutdown(): the pool is shared and long-lived.
        # Stragglers keep running on it and free their slot when they finish,
        # which is what bounds them. Calling shutdown here would retire the
        # shared pool out from under concurrent callers.
        pass

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

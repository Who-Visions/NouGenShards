"""Federated Retrieval Engine. Merges local substrate with external DBs."""
from . import core
from .connectors.sql import query_external_dbs
from .connectors.cloud import query_cloud_shards
from . import keymaker

def federated_retrieve(query: str, limit: int = 3, query_embedding: list = None) -> list:
    """
    Module 8: Combine Compatible Systems.
    Polls local Shard substrate, external DBs, and remote cloud nodes.
    """
    # 1. Get Local Shards (Bayesian Posterior)
    local_results = core.retrieve(query, limit=limit, query_embedding=query_embedding)
    
    # 2. Get Configs from Keymaker
    external_configs = keymaker.list_external_dbs()
    cloud_configs = keymaker.list_cloud_nodes()
    
    # 3. Query External DBs if configured
    external_results = []
    if external_configs:
        external_results = query_external_dbs(query, external_configs, limit=limit)
        
    # 4. Query Cloud Nodes if configured
    cloud_results = []
    if cloud_configs:
        cloud_results = query_cloud_shards(query, cloud_configs, limit=limit)
        
    # 5. Merge and re-rank via Bayesian Posterior
    # (Module 21: Orchestrate Convergence)
    combined = local_results + external_results + cloud_results
    combined.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    
    return combined[:limit]

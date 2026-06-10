"""Federated Retrieval Engine. Merges local substrate with external DBs."""
from . import core
from .connectors.sql import query_external_dbs
from . import keymaker

def federated_retrieve(query: str, limit: int = 3, query_embedding: list = None) -> list:
    """
    Module 8: Combine Compatible Systems.
    Polls local Shard substrate and all linked external databases.
    """
    # 1. Get Local Shards (Bayesian Posterior)
    local_results = core.retrieve(query, limit=limit, query_embedding=query_embedding)
    
    # 2. Get External DB configs from Keymaker
    external_configs = keymaker.list_external_dbs()
    
    # 3. Query External DBs if configured
    external_results = []
    if external_configs:
        external_results = query_external_dbs(query, external_configs, limit=limit)
        
    # 4. Merge and re-rank via Bayesian Posterior
    # (Module 21: Orchestrate Convergence)
    combined = local_results + external_results
    combined.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    
    return combined[:limit]

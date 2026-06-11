"""
The Dream State (Autonomous Metameric Evolution).
Implementation of TMEM: Parametric Memory through Fast-Weight Rollouts.
"""

import json
import sqlite3
from typing import List, Dict, Any

from . import core
from . import history

def fetch_high_utility_shards(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve the top shards by utility score across the federated database cluster."""
    top_shards = []
    for i in range(1, core.MAX_DB_COUNT + 1):
        if not core.get_db_path(i).exists():
            continue
        conn = core.get_connection(i)
        try:
            cursor = conn.execute("SELECT id, title, content, utility_score FROM shards ORDER BY utility_score DESC LIMIT ?", (limit,))
            for row in cursor:
                top_shards.append(dict(row))
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()
    
    # Sort globally and take top N
    top_shards.sort(key=lambda x: x["utility_score"], reverse=True)
    return top_shards[:limit]

def synthesize_invariants(shards: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Phase 1: REM Cycle.
    Formats the raw shards into SFT QA pairs suitable for LoRA fine-tuning.
    """
    sft_data = []
    for shard in shards:
        # In a full TMEM pipeline, we could invoke an LLM to distill this.
        # For efficiency, we map the structured shards directly to instruction/output pairs.
        sft_data.append({
            "instruction": shard["title"],
            "output": shard["content"]
        })
    return sft_data

def parametric_burn_in(sft_data: List[Dict[str, str]], output_path: str = "dream_sft.jsonl") -> str:
    """
    Phase 3: Parametric Fast-Weight Rollout.
    Exports the SFT data for the local Edge Model to perform an SVD-initialized LoRA update.
    """
    out_file = core.GLOBAL_DIR / output_path
    with open(out_file, "w", encoding="utf-8") as f:
        for item in sft_data:
            f.write(json.dumps(item) + "\n")
    return str(out_file)

def wake() -> Dict[str, Any]:
    """
    Executes the autonomous Dream cycle.
    Returns a summary of actions taken during 'sleep'.
    """
    # 1. Prune
    core.decay_utility_scores()
    
    # 2. Extract
    top_shards = fetch_high_utility_shards(limit=50)
    
    # 3. Distill
    sft_pairs = synthesize_invariants(top_shards)
    
    # 4. Burn In
    dataset_path = parametric_burn_in(sft_pairs)
    
    return {
        "pruned": "Applied 0.95x Bayesian decay to all shards.",
        "shards_extracted": len(top_shards),
        "sft_pairs_generated": len(sft_pairs),
        "parametric_dataset_path": dataset_path,
        "status": "Dream sequence complete. Ready for fast-weight LoRA update."
    }

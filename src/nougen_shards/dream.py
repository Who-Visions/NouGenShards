"""
The Dream State (Autonomous Metameric Evolution).
Implementation of TMEM and offline dual-system semantic consolidation.

Semantic consolidation itself is owned by :mod:`nougen_shards.griot` (the Rules
agent). This module orchestrates the full REM cycle — decay, SFT export, and
Griot's consolidation pass — and re-exports Griot's entry points for backward
compatibility.
"""

import json
import sqlite3
from typing import List, Dict, Any, Optional

from . import core
from . import history
from . import griot
# Re-exported for backward compatibility; callers/tests reference these on the
# dream module. `extract_semantic_invariants_via_llm` is monkeypatched in tests,
# and consolidate_episodic_data() honors that patch by injecting it explicitly.
from .griot import fallback_rule_parser, extract_semantic_invariants_via_llm


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


def consolidate_episodic_data(limit: int = 10) -> Dict[str, Any]:
    """
    Offline Consolidation Loop (REM Sleep) — delegates to the Griot agent.

    Passes this module's ``extract_semantic_invariants_via_llm`` explicitly so
    tests that monkeypatch it on the dream module still take effect.
    """
    return griot.consolidate_episodic_data(
        limit, extractor=extract_semantic_invariants_via_llm
    )


def wake() -> Dict[str, Any]:
    """
    Executes the autonomous Dream cycle (REM Sleep).
    Decays utility scores, extracts SFT pairs, and runs semantic consolidation.
    """
    # 1. Prune
    core.decay_utility_scores()
    
    # 2. Extract top shards for LoRA
    top_shards = fetch_high_utility_shards(limit=50)
    sft_pairs = synthesize_invariants(top_shards)
    dataset_path = parametric_burn_in(sft_pairs)
    
    # 3. Perform relational semantic consolidation
    consolidation_results = consolidate_episodic_data(limit=10)
    
    return {
        "experimental": True,
        "pruned": "Applied 0.95x utility decay to all shards.",
        "shards_extracted_sft": len(top_shards),
        "sft_pairs_generated": len(sft_pairs),
        "parametric_dataset_path": dataset_path,
        "dual_system_consolidation": consolidation_results,
        "status": "Decay applied, SFT dataset exported, and dual-system semantic consolidation completed."
    }

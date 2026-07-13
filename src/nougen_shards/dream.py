"""
The Dream State (Autonomous Metameric Evolution).
Implementation of TMEM and offline dual-system semantic consolidation.
"""

import json
import sqlite3
import re
import datetime
from datetime import timezone
from typing import List, Dict, Any

from . import core


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


def fallback_rule_parser(content: str) -> List[Dict[str, str]]:
    """RegEx/simple heuristic fallback for invariant extraction when LLM is unavailable."""
    invariants = []
    lines = content.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Filter: must start with rule (case-insensitive) or contain a colon
        if not (line.lower().startswith("rule") or ":" in line):
            continue
        # Clean optional "Rule - " or "Rule: " prefix first
        cleaned = line
        if cleaned.lower().startswith("rule - "):
            cleaned = cleaned[7:].strip()
        elif cleaned.lower().startswith("rule: "):
            cleaned = cleaned[6:].strip()
        elif cleaned.lower().startswith("rule:"):
            cleaned = cleaned[5:].strip()
        
        # 1. First, try colon separator
        match = re.match(r"^([^:]{2,30}):\s*(.+)$", cleaned)
        if match:
            invariants.append({
                "subject": match.group(1).strip(),
                "predicate": match.group(2).strip()
            })
            continue
            
        # 2. Second, try splitting by common modal/verbs
        for verb in [" must ", " should ", " is "]:
            if verb in cleaned:
                parts = cleaned.split(verb, 1)
                sub = parts[0].strip()
                pred = (verb.strip() + " " + parts[1]).strip()
                if 2 <= len(sub) <= 30:
                    invariants.append({
                        "subject": sub,
                        "predicate": pred
                    })
                    break
    return invariants


def extract_semantic_invariants_via_llm(content: str) -> List[Dict[str, str]]:
    """Invokes local Ollama LLM to compile raw episodic contents into semantic invariants."""
    try:
        from .models_client import OllamaClient
        client = OllamaClient()
        if not client.is_alive():
            return fallback_rule_parser(content)
            
        models = client.list_models()
        model = "griot:e2b" if "griot:e2b" in models else (client.find_best_edge_model().model_name if models else None)
        if not model:
            return fallback_rule_parser(content)
            
        prompt = (
            "You are an LLM utility compiler. Your task is to extract core architectural invariants and verified rules from raw interaction logs or developer actions.\n"
            "Analyze the input log content and compile it into one or more structured JSON objects representing permanent system truth.\n"
            "Each object must follow this schema:\n"
            "[\n"
            "  {\n"
            "    \"subject\": \"Name of the component, technology, or system entity\",\n"
            "    \"predicate\": \"Strict architectural fact, constraint, or rule describing how it works, why it is configured this way, or what to avoid\"\n"
            "  }\n"
            "]\n"
            "Do not output any introductory or conversational text, output raw JSON ONLY. If no rules or facts are present, output an empty array [].\n\n"
            f"Input Content: {content}"
        )
        
        messages = [{"role": "user", "content": prompt}]
        response_text = client.chat(model, messages)
        
        # Parse JSON from response
        json_match = re.search(r"\[\s*\{.*\}\s*\]", response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
            
        dict_match = re.search(r"\{\s*\".*\"\s*:\s*\".*\"\s*\}", response_text, re.DOTALL)
        if dict_match:
            return [json.loads(dict_match.group(0))]
            
        return json.loads(response_text)
    except Exception:
        return fallback_rule_parser(content)


def consolidate_episodic_data(limit: int = 10) -> Dict[str, Any]:
    """
    Offline Consolidation Loop (REM Sleep).
    Queries raw shards where utility_score >= 1.0 and consolidated = 0,
    extracts invariants, upserts to semantic_knowledge, and marks them consolidated.
    """
    unconsolidated = []
    for i in range(1, core.MAX_DB_COUNT + 1):
        if not core.get_db_path(i).exists():
            continue
        conn = core.get_connection(i)
        try:
            cursor = conn.execute("""
                SELECT id, content, domain_key, utility_score, ? as _db_index
                FROM shards
                WHERE utility_score >= 1.0 AND consolidated = 0
                LIMIT ?
            """, (i, limit))
            for row in cursor:
                unconsolidated.append(dict(row))
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()
            
    new_invariants_count = 0
    consolidated_shards_count = 0
    extracted_rules = []
    
    for shard in unconsolidated:
        invariants = extract_semantic_invariants_via_llm(shard["content"])
        if invariants:
            db_idx = shard["_db_index"]
            conn = core.get_connection(db_idx)
            try:
                timestamp = datetime.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                shard_invariants_inserted = 0
                for inv in invariants:
                    # The LLM extraction can return non-dict elements; skip them
                    # rather than letting AttributeError escape the sqlite handler
                    # and abort the whole consolidation cycle.
                    if not isinstance(inv, dict):
                        continue
                    sub = inv.get("subject")
                    pred = inv.get("predicate")
                    if not sub or not pred:
                        continue
                    # subject/predicate must be strings; a list/dict value would
                    # raise AttributeError on .strip() and escape the sqlite handler.
                    if not isinstance(sub, str) or not isinstance(pred, str):
                        continue

                    conn.execute("""
                        INSERT INTO semantic_knowledge (subject, predicate, domain_key, updated_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(subject, predicate) DO UPDATE SET
                            confidence_score = confidence_score + 0.1,
                            updated_at = excluded.updated_at
                    """, (sub.strip(), pred.strip(), shard.get("domain_key", "global"), timestamp))
                    extracted_rules.append({"subject": sub.strip(), "predicate": pred.strip()})
                    new_invariants_count += 1
                    shard_invariants_inserted += 1

                # Only mark consolidated / count the shard when at least one
                # invariant was actually inserted; a bare dict or all-skipped
                # payload must not falsely retire the shard.
                if shard_invariants_inserted:
                    conn.execute("UPDATE shards SET consolidated = 1 WHERE id = ?", (shard["id"],))
                    conn.commit()
                    consolidated_shards_count += 1
            except sqlite3.Error as exc:
                print(f"[Warning] Failed to save semantic invariant: {exc}")
            finally:
                conn.close()
                
    return {
        "shards_scanned": len(unconsolidated),
        "shards_consolidated": consolidated_shards_count,
        "new_invariants_extracted": new_invariants_count,
        "rules": extracted_rules
    }


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

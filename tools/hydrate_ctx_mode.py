#!/usr/bin/env python
"""
hydrate_ctx_mode.py — Context Hydrator for NouGenShards.
Pulls relevant and high-utility memory shards from the database cluster
and compiles them into a structured recall context file.
"""
import os
import sys
import argparse
from pathlib import Path

# Resolve the package import path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    import nougen_shards.core as core
except ImportError:
    sys.path.insert(0, str(REPO_ROOT))
    import src.nougen_shards.core as core

def get_vault_dir():
    _vault_dir = os.environ.get("NOUGEN_VAULT_DIR")
    if not _vault_dir:
        local_vault = REPO_ROOT / ".vault"
        if local_vault.exists() and local_vault.is_dir():
            _vault_dir = str(local_vault)
        else:
            _vault_dir = str(Path.home() / ".nougen" / "shards")
    return Path(_vault_dir)

def main():
    parser = argparse.ArgumentParser(description="Hydrate context prompt from memory vault.")
    parser.add_argument("--query", type=str, default="", help="Search query for relevant memories.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of shards to recall.")
    parser.add_argument("--domain", type=str, default=None, help="Domain key scope (default: auto-resolved).")
    parser.add_argument("--output", type=str, default="sol_context_prompt.txt", help="Output file path.")
    args = parser.parse_args()

    # Direct NOUGEN_VAULT_DIR to the resolved path
    vault_dir = get_vault_dir()
    os.environ["NOUGEN_VAULT_DIR"] = str(vault_dir)

    print(f"Connecting to memory vault at: {vault_dir}")
    
    # Auto-resolve domain if not specified
    domain_key = args.domain or core.resolve_domain_from_path()
    print(f"Domain Scope: {domain_key}")

    shards = []
    
    if args.query:
        print(f"Searching memory database for: '{args.query}'...")
        shards = core.retrieve(query=args.query, limit=args.limit, domain_key=domain_key)
    else:
        # If no query is provided, default to pulling the most recent high-utility shards
        print(f"Query not specified. Fetching top {args.limit} high-utility recent shards...")
        
        # Iterate over all databases in the cluster
        all_candidates = []
        for i in range(1, 10):
            db_path = vault_dir / f"nougen_shards_{i}.db"
            if not db_path.exists():
                continue
            try:
                import sqlite3
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, timestamp, title, content, utility_score, embedding, tags, domain_key
                    FROM shards
                    WHERE domain_key = ?
                    ORDER BY timestamp DESC LIMIT ?
                """, (domain_key, args.limit))
                for row in cursor:
                    item = dict(row)
                    item["_db_index"] = i
                    # Give it a baseline score based on utility
                    item["final_score"] = item["utility_score"]
                    all_candidates.append(item)
                conn.close()
            except Exception as e:
                print(f"Error reading Node #{i}: {e}")
                
        # Sort candidates and take the top N
        all_candidates.sort(key=lambda x: (x.get("utility_score", 1.0), x.get("timestamp", "")), reverse=True)
        shards = all_candidates[:args.limit]

    print(f"Retrieved {len(shards)} shards.")
    
    # Compile the recall packet
    packet = core.compile_recall_packet(shards)
    
    # Determine absolute output path
    output_path = Path(args.output)
    if not output_path.is_absolute():
        # Write to watchtower root if possible, otherwise locally. Default is
        # ~/Watchtower (no hardcoded author path); override with WATCHTOWER_ROOT.
        wt_root = os.environ.get("WATCHTOWER_ROOT") or str(Path.home() / "Watchtower")
        if os.path.exists(wt_root):
            output_path = Path(wt_root) / args.output
        else:
            output_path = REPO_ROOT / args.output

    try:
        output_path.write_text(packet, encoding="utf-8")
        print(f"Successfully hydrated context mode file: {output_path.absolute()}")
    except Exception as e:
        print(f"Error writing context file: {e}")
        # Print to stdout as a fallback
        print("\n=== CONTEXT FALLBACK ===")
        print(packet)

if __name__ == "__main__":
    main()

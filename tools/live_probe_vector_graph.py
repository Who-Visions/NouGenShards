import sys
import io
import os
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Resolve the repo root from this file's location: tools/<script>.py -> repo root.
# An absolute path baked in here only ever works on one checkout on one machine.
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))

from nougen_shards import vector_graph, core, graph

print("=== LIVE VECTOR GRAPH PROBE ===")
print("Active Vault Dir:", core.active_vault_dir())
print("Graph DB Path:", graph.get_graph_db_path())

# 1. Initialize schema in live vault
vector_graph.init_vector_graph_db()
st_before = vector_graph.stats()
print("Stats before test:", st_before)

# 2. Extract and ingest a small batch of live shards to populate the graph
print("\nIngesting sample live shards into Vector-Graph...")
ingested_count = 0
for db_idx in range(1, 4):
    conn = core.get_connection(db_idx)
    try:
        rows = conn.execute("SELECT file_hash, title, content FROM shards WHERE title IS NOT NULL AND content IS NOT NULL LIMIT 15").fetchall()
        for r in rows:
            c = vector_graph.ingest_shard_triplets(r["file_hash"], r["title"], r["content"])
            ingested_count += c
    except Exception as e:
        print(f"DB {db_idx} read error: {e}")
    finally:
        conn.close()

print(f"Ingested {ingested_count} live relation triplets.")
st_after = vector_graph.stats()
print("Stats after ingestion:", st_after)

# 3. Test Live Vector Graph Retrieval
query = "encryption and secrets keymaker"
print(f"\nExecuting Live Vector-Graph Retrieval: '{query}'")
results, subgraph = vector_graph.retrieve_vector_graph(query, limit=3, expand_hops=1)

print(f"Retrieved {len(results)} shards via Vector-Graph:")
for r in results:
    print(f"  * [{r.get('id')}] {r.get('title')} (score={r.get('vector_graph_score', 0):.3f})")
    print(f"    Graph Evidence: {r.get('graph_evidence')}")

print(f"\nSubgraph Topology: {len(subgraph.seed_entities)} seed entities, {len(subgraph.seed_relations)} seed relations, {len(subgraph.expanded_relations)} expanded relations.")

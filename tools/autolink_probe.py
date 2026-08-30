import sys
import io
import os
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Resolve the repo root from this file's location: tools/<script>.py -> repo root.
# An absolute path baked in here only ever works on one checkout on one machine.
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))

os.environ["NOUGEN_AUTOGRAPH_ENABLED"] = "1"
from nougen_shards import core, graph, vector_graph

print("=== AUTONOMOUS GRAPHING & LINKING TEST ===")
edges_before = graph.edge_count()
print(f"Edges before: {edges_before}")

# 1. Capture Shard A
content_a = """---
topic: autonomous_agent_linking
category: ARCHITECTURE
tags: Valerion, VectorGraph, Autolink
---
# Valerion Autonomous Agent Linking
Apollo implements autonomous vector graphing across all captured experience shards.
"""
print("Capturing Shard A...")
core.capture("CANON", "Valerion Autonomous Linking Node", content_a)

# 2. Capture Shard B (shares entity 'Valerion' and 'Apollo')
content_b = """---
topic: autonomous_agent_linking
category: ARCHITECTURE
tags: Valerion, SolAi, Autolink
---
# Sol-Ai Cognitive Expansion
Sol-Ai connects to the Valerion vector graph to perform multi-hop topological reasoning.
"""
print("Capturing Shard B...")
core.capture("CANON", "Sol-Ai Cognitive Expansion Node", content_b)

edges_after = graph.edge_count()
print(f"Edges after: {edges_after} (New edges created: {edges_after - edges_before})")

# 3. Retrieve and inspect links
shards = core.retrieve("Valerion Autonomous Linking", limit=2)
if shards:
    target_shard = shards[0]
    print(f"\nTarget Shard: [{target_shard['id']}] {target_shard['title']}")
    related = graph.related_shards(target_shard['id'], target_shard['_db_index'])
    print(f"Topologically Related Shards ({len(related)}):")
    for rel in related:
        print(f"  * Linked Shard: {rel['title']} via predicate: '{rel['relation']}'")

st = vector_graph.stats()
print("\nFinal Vector Graph Stats:", st)

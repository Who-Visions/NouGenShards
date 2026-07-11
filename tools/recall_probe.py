"""Move 2 probe (nougen-beats-fable): 10 paraphrase queries, zero keyword overlap.
Scores whether the known target surfaces in top-5 via federated_retrieve.
Compact output: query, hit/miss, top-5 titles truncated."""
import os
import sys
import json

sys.path.insert(0, "./src")
os.environ.setdefault("NOUGEN_VAULT_DIR", "C:/Users/super/Watchtower/vault")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nougen_shards.federation import federated_retrieve

# (paraphrase query, substrings that identify the target shard - any match = hit)
PROBES = [
    ("stop recall from returning near identical duplicate results", ["mmr", "diversif"]),
    ("vectors created automatically when a record is missing one", ["auto-embed", "auto embed", "embed-on-none", "a54a51e"]),
    ("is the research paper feed still fresh or has it gone quiet", ["arxiv", "lane"]),
    ("how are credentials protected at rest on this machine", ["dpapi", "encrypt", "keymaker", "secret"]),
    ("what must an agent do before starting any large task", ["war-game", "wargame", "rule 0", "recall before", "context mode"]),
    ("what happens when the top tier model subscription ends", ["fable", "jul 7", "july 7", "redeploy", "subscription"]),
    ("the panic about deleted work that turned out to be fine", ["float32", "false alarm", "97dda8e", "antigravity deleted"]),
    ("how coding assistants pass tickets to each other mid session", ["queue", "open engine", "ticket", "claim"]),
    ("what forces a session summary to be written before quitting", ["handoff", "guard", "hook"]),
    ("why do writes to the local service get rejected with auth errors", ["401", "403", "write-auth", "mesh_token", "sol_mesh_token", "fail-closed", "fail closed"]),
]

hits = 0
for q, needles in PROBES:
    try:
        res = federated_retrieve(q, limit=5) or []
    except Exception as e:
        print(f"MISS(err) | {q[:48]} | {e}")
        continue
    titles = []
    blob_parts = []
    for s in res:
        t = (s.get("title") or "")[:70]
        titles.append(t)
        blob_parts.append((s.get("title") or "") + " " + (s.get("content") or "")[:500])
    blob = " ".join(blob_parts).lower()
    hit = any(n in blob for n in needles)
    hits += hit
    print(f"{'HIT ' if hit else 'MISS'} | {q[:48]}")
    for t in titles[:3]:
        print(f"      - {t}")

print(json.dumps({"score": f"{hits}/10", "pass_bar": ">=8/10"}))

"""Capture the NouGen operating doctrine as first-class DOCTRINE shards.

Root cause of the retrieval plateau (round 4): the agent's own doctrine —
war-game rule, handoff-guard, embed-at-ingest, MMR dedup, secret guard, the
float32 false-alarm correction — lived only in CLAUDE.md / HARDENING.md / code,
never as embedded vault shards. So "recall before reasoning" returned arxiv
noise for doctrine questions. This closes that coverage gap. Each shard is a
true, load-bearing operating fact, written crisp and keyword-rich so both the
FTS and vector lanes surface it. Idempotent: capture() dedups by content hash.
"""
import os
import sys

sys.path.insert(0, "./src")
os.environ.setdefault("NOUGEN_VAULT_DIR", "C:/Users/super/Watchtower/vault")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nougen_shards import core

# (event_type, title, content, tags)
DOCTRINE = [
    ("DOCTRINE", "War-game before any large or meaty task (Rule 0.1)",
     "Before starting any mission with 3+ steps or real failure surface, the agent must war-game first and execute second: fight the mission on paper move by move into wargames/<mission>.md before touching code. Every move carries the expected observation if it worked, the failure signal if it did not, and the countermove. Every fork gets a trigger ('if you observe X take route A else route B') — no linear blue-sky plans. Plans are banned for meaty missions; war-games replace them. This is the first thing to do before a big task.",
     ["doctrine", "war-game", "rule-0.1", "before-task", "planning"]),

    ("DOCTRINE", "Context mode: recall before reasoning, delegate the heavy lifting (Rule 0.0)",
     "Default to NouGen context mode for all work: recall relevant context from the vault before reasoning from scratch, and delegate bulk generation, summarization, and drafts to free fleet/local lanes (ollama, OpenRouter, HF) to save Coach tokens. The agent plans, routes, and verifies compressed worker returns — it does not do the heavy lifting inline. Capture milestones back to the vault so each session compounds into the next. This is the supreme binding rule.",
     ["doctrine", "context-mode", "rule-0.0", "recall-first", "delegate"]),

    ("DOCTRINE", "Dynamic over hardcode on every line (Rule 0.2)",
     "Hardcoded values are claims, not truth. Probe before you trust: env vars, paths, ports, model names, and counts inherited from config or memory get verified against live state before driving an action. When a hardcoded value fails, suspect the value first, not the world — stale config is the cheaper hypothesis than broken hardware. Every environment-, path-, threshold-, count-, or model-shaped literal resolves from env then config then runtime probe, with the constant as a logged fallback only. Precedent: a stale OLLAMA_MODELS var pointing at a wrong drive faked an external-drive failure while models sat in the per-user store.",
     ["doctrine", "dynamic-over-hardcode", "rule-0.2", "discover-dont-assume"]),

    ("DOCTRINE", "Handoff guard hook writes a session summary before quitting (HARDENING 1)",
     "Capture must be structural, never voluntary — manual capture equals eventual amnesia. The handoff_guard.py hook fires on every session end and writes a vault intelligence shard unconditionally, with zero human or agent cooperation, so every session leaves a trace. What forces a session summary to be written before the agent quits or hands back control is this sessionend hook plus the mandatory handoff-create step. Deduped, stdlib-only, exception-swallowed so it never blocks shutdown.",
     ["doctrine", "hardening-1", "handoff", "handoff-guard", "hook", "session-summary"]),

    ("DOCTRINE", "Shards are born recallable — embed at ingest (HARDENING 2)",
     "Vectors are created automatically at write time for every shard that is missing one: core.capture() embeds each shard on ingest via the local ollama model (NOUGEN_EMBED_MODEL) with a short timeout, so shards are born recallable and semantic recall never silently starves. This auto-embed-on-none behavior fixed the failure where ~27k shards had NULL embeddings and semantic recall returned nothing while claiming 'no relevant shards'. Embedding failure degrades that one shard to keyword-only, never blocks capture; a backfill sweep catches stragglers.",
     ["doctrine", "hardening-2", "embed-at-ingest", "auto-embed", "embedding", "recall"]),

    ("DOCTRINE", "Pipelines must announce their own death — lane freshness (HARDENING 3)",
     "Ingestion lanes fail silently for weeks unless they expose last-success age; the sync agent died and the arxiv scanner died, both unnoticed. lane_freshness.py is a stdlib-only sensor (never raises, exits 0) that reports the newest-artifact age per lane and flags anything stale beyond a threshold derived algorithmically from that lane's own cadence. Answers whether the research-paper feed is still fresh or has gone quiet. One lane per artifact type so a flowing lane can't mask a dead one.",
     ["doctrine", "hardening-3", "lane-freshness", "arxiv", "staleness", "sensor"]),

    ("DOCTRINE", "Empty result is not a healthy no-match — lane health (HARDENING 4)",
     "A recall lane that answers 'no relevant shards' while its semantic index is dead is a broken sensor reporting absence as fact. Recall responses now carry lane health (total shards, embedding coverage percent) and flag 'DEGRADED SEMANTIC LANE — absence unverified' below NOUGEN_MIN_COVERAGE_PCT. Agents must not assert that something is absent from a degraded lane; verify the lane is healthy before trusting an empty result.",
     ["doctrine", "hardening-4", "lane-health", "empty-not-absence", "recall"]),

    ("DOCTRINE", "Multi-term queries must not silently AND — ranked-OR fallback (HARDENING 5)",
     "FTS5 with implicit-AND semantics returns zero for conversational multi-term queries when the terms do not co-occur, even though thousands of shards match individual terms. The fix is a two-pass MATCH in keyword retrieval: AND first, then ranked OR, then LIKE, so a paraphrase that shares no exact phrase still surfaces the best partial match ranked by bm25 coverage.",
     ["doctrine", "hardening-5", "fts", "ranked-or", "keyword-recall"]),

    ("DOCTRINE", "The substrate is not a landfill — ingest junk gate (HARDENING 7)",
     "Lockfiles, base64 blobs, minified bundles, and whole encoder.json vocabs were being sharded as knowledge, polluting recall and wasting embeddings. capture() now rejects this blob class structurally via _looks_like_blob: it fires only when the longest whitespace-free run exceeds a token threshold and is overwhelmingly base64/hex charset, so prose and real code pass while junk is refused with the same skip contract as a dedup hit.",
     ["doctrine", "hardening-7", "junk-gate", "ingest-quality", "blob"]),

    ("DOCTRINE", "Credentials live in the Keymaker, encrypted at rest, never in shards (HARDENING 8)",
     "Credentials are protected at rest on this machine by DPAPI encryption in the Keymaker vault (agent_secrets.db); only key names and SHA-256 fingerprints go to the metadata ledger, never plaintext values. capture() runs a structural secret guard that redacts hf_, sk-, AIza, JWT, DB-URL, and private-key shapes from title, content, and tags before hashing, embedding, or writing, so no write path can bake a secret into a shard. Credential ingestion routes to the Atibon/Keymaker flow.",
     ["doctrine", "hardening-8", "keymaker", "dpapi", "secrets", "credentials", "atibon"]),

    ("DOCTRINE", "MMR diversification stops recall returning near-identical duplicates",
     "Maximal Marginal Relevance (mmr_diversify) reorders scored recall candidates to balance relevance against novelty, greedily picking each next item by relevance minus its maximum cosine similarity to everything already picked. This is what stops recall from returning near-identical duplicate results — it de-duplicates the packet by penalizing redundancy. NOUGEN_MMR_LAMBDA tunes the trade-off; 1.0 disables it for pure relevance.",
     ["doctrine", "mmr", "diversify", "dedup", "recall-quality"]),

    ("DOCTRINE", "Open Engine task queue: coding assistants pass tickets to each other mid-session",
     "The Open Engine queue is how coding assistants hand tickets to each other mid-session across provider lanes (Claude, Gemini, Codex) without a full session handoff. nougen queue add writes a self-contained ticket; nougen queue claim atomically claims the oldest eligible ticket with a claim lock so exactly one worker wins; block parks on ambiguity; done requires an honest receipt with evidence. Status lanes: todo, working, needs_input, done.",
     ["doctrine", "open-engine", "queue", "ticket", "claim-lock", "handoff"]),

    ("PROJECT", "Fable 5 subscription cutover to API around July 2026",
     "The top-tier model subscription access for Claude Fable 5 ends around July 7-8 2026, after which the Fable lane is reached via API rather than the sub. When the subscription ends, frontier-tier work (war-games, architecture, hardest reviews) either moves to the API-billed Fable lane or falls back to Opus 4.8 as the daily driver. Re-score the fable-5 lane against GPT 5.6 and Gemini 3.5 Pro before committing API spend.",
     ["project", "fable-5", "subscription", "cutover", "model-scorecard"]),

    ("CORRECTION", "Float32 'deleted work' panic was a false alarm — work was committed",
     "The panic about deleted work that turned out to be fine: a document claimed antigravity deleted development work (a float32 loss), but this was a false alarm — the work was safely committed in git (commit 97dda8e). Do not reconstruct the supposedly-lost work; verify git state before trusting a data-loss claim. This is the precedent for the two-confirmations rule: a data-loss incident needs the symptom AND a verified premise before escalation.",
     ["correction", "float32", "false-alarm", "97dda8e", "data-loss", "verify-before-panic"]),

    ("DOCTRINE", "Write-auth fails closed: 401/403 on local service writes are protection, not failure",
     "When writes to the local mesh service get rejected with auth errors, that is the fail-closed write-auth guard working as designed, not a broken service. Mutative endpoints require SOL_MESH_TOKEN on the server and a valid request token plus command lane: missing server token disables writes (503), missing or invalid request token returns 401 UNAUTHORIZED, missing or invalid command lane returns 403 FORBIDDEN, valid token plus valid lane returns 200. Report write-auth rejections as protected-state behavior.",
     ["doctrine", "write-auth", "fail-closed", "401", "403", "mesh-token", "sol_mesh_token"]),

    ("DOCTRINE", "Stored embeddings can invert to source text — candidate HARDENING 9",
     "Dense embeddings invert back to their source text with high fidelity, so a leaked shard database could reconstruct redacted content from its raw embedding BLOBs even though the secret guard redacts the text field. Candidate ninth hardening invariant: a leaked vault must not trivially invert to its source text. Candidate mitigation is SVD-truncation plus an owner-held orthogonal rotation of stored vectors, env-gated and applied symmetrically on read and write so cosine ranking is preserved. War-game required before building.",
     ["doctrine", "hardening-9", "embedding-inversion", "privacy", "candidate"]),
]


def main():
    captured = 0
    skipped = 0
    for event_type, title, content, tags in DOCTRINE:
        ok = core.capture(event_type, title, content, tags=tags)
        if ok:
            captured += 1
            print(f"[captured] {title[:60]}")
        else:
            skipped += 1
            print(f"[skip/dup] {title[:60]}")
    print(f"\n{captured} captured, {skipped} skipped (dup), {len(DOCTRINE)} total")


if __name__ == "__main__":
    main()

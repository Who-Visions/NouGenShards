# Native graph context recall

`search_shards(query, limit=5, context_budget=8000)` invokes the existing
context-packet primitive over federated candidates. With `context_budget=0`,
the existing raw search response remains unchanged. No durable shard is rewritten.

Policy `graph-context-v1` ranks lexical query coverage plus a bounded stored
importance prior: `coverage + 0.1 * max(importance,0)/(1+max(importance,0))`.
`utility_score` supplies the prior when `importance` is absent. Stable source,
database and shard identities break ties. Nonmatching high-importance records
cannot enter merely because of their prior.

The narrow candidate group is considered first. Expansion stops when selected
root query coverage reaches the configured threshold, or the root count reaches
its limit. This is lexical sufficiency, not a claim of semantic correctness.
Candidates carry explicit `dependencies` as `{id, _db_index, source_node}`
references; missing fields inherit the root's database/source. Required dependency
closures are indivisible: missing dependencies or budget overflow reject the
dependent root with a recorded reason. Cycles terminate, and dependency counts
are bounded. The MCP loader resolves local durable references only; unresolved
remote references fail closed. It does not invent graph edges from model output.

The payload budget counts canonical JSON UTF-8 bytes, a conservative upper bound
on token count rather than a measured tokenizer count. It covers content payload,
not response provenance/decision overhead. No content is truncated to fit; callers
receive rejection evidence instead. Provenance includes full SHA-256 content
digests, source URI and evidence labels (unclassified when absent). Replay hashes
cover the selected payload, ordered decisions and policy version; changing
the candidate pool or dependencies may legitimately change the result.

This graft uses the native context packet and registered shard-search path;
it is not a new memory store. It is research-inspired reference behavior,
not a claim to reproduce MemCodex/ReCAP research results. Stored importance is
consumed, never recomputed or written by this read path. Runtime deployment and
default activation are separate operations.

Verification: `tests/test_graph_context_packet.py` covers ranking/replay, atomic
dependencies, missing references, Unicode budgeting, cycles, expansion ceilings,
sufficiency stopping, source/database identity and the registered MCP path.

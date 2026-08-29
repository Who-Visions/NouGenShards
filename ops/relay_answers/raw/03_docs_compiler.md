<!-- route: ollama-cloud-contact-whovisions -->

** (a) Module layout & data flow (text diagram) **  
```
tools/nougen_docs/
├─ __init__.py
├─ compiler.py          # orchestrates modes, calls sub‑modules
├─ manifest.py          # loads/validates repo manifest (JSON)
├─ sanitizer.py         # wraps redaction.redact_content()
├─ dedup.py             # clusters relay records via dedup key
├─ changelog.py         # generates --changelog output
└─ provenance.py        # builds provenance sidecar record

Data flow:
repo source (src/, configs, schemas, tests) 
   → manifest.py (reads repo manifest) 
   → fleet.py (tools/fleet.py) queries relay registry 
   → dedup.py clusters relay records 
   → assurance.py labels each claim (VERIFIED/…) 
   → provenance.py builds sidecar 
   → compiler.py (mode logic) 
   ├─ --check / --dry-run → validates, prints diff 
   ├─ --write → writes <!-- NOUGEN:AUTO:SECTION:START/END --> blocks 
   ├─ --changelog → emits changelog section 
   └─ --all-public / --since / --explain → filters output 
   → sanitizer.py (redaction.redact_content()) strips PII/secrets 
   → final Markdown docs
```

** (b) Repo manifest schema (minimal JSON) **  
```json
{
  "version": "string",          // e.g. "1.2.0"
  "name": "string",             // repo identifier
  "description": "string",      // short purpose
  "entry_points": [ "string" ], // list of Python modules exposing public tools
  "schemas": [ "string" ],      // paths to JSON‑Schema files
  "configs": [ "string" ],      // paths to config files (yaml/toml)
  "tests": [ "string" ]         // paths to test directories/files
}
```

** (c) Provenance state record **  
```json
{
  "timestamp": "ISO‑8601",
  "source_sha": "git commit SHA of repo manifest",
  "relay_ids": [ "string" ],    // deduplicated relay IDs used
  "incident_id": "string",      // clustering key from dedup
  "assurance": {
    "label": "VERIFIED|CONTRADICTED|UNCERTAIN|UNVERIFIED",
    "confidence": 0.0-1.0,
    "rationale": "string",
    "evidence_used": [ "string" ],
    "caveats": [ "string" ]
  }
}
```

** (d) Existing NouGen modules to reuse **  
- `src/nougen_shards/assurance.py` – labeling & confidence logic  
- `src/nougen_shards/redaction.py` – `redact_content()` for the public sanitizer  
- `tools/fleet.py` – 58‑route dispatcher to query the relay registry  
- `src/nougen_shards/handoff.py` – handling of relay → shard handoff without mutation  

** (e) Source‑verification rule set **  
1. **Repo source truth** (files listed in manifest) outranks any memory claim from a shard or relay.  
2. **If claim matches repo fact** → assurance label `VERIFIED`, confidence ≥ 0.9, evidence = repo file paths.  
3. **If claim disagrees** → assurance label `CONTRADICTED`, confidence ≤ 0.3, evidence = repo file paths, rationale notes the mismatch, caveats note possible stale shard/relay data.  
4. On disagreement the tool **emits** the contradiction in the provenance sidecar and **does not** alter the claim in shards or relays.  

** (f) Dedup key for clustering relays **  
`(incident_type, timestamp_window, shard_id, content_hash)` where:  
- `incident_type` = relay category (e.g., `shards_capture`, `tracker_spend`)  
- `timestamp_window` = floor(timestamp to 5 min)  
- `shard_id` = originating shard identifier  
- `content_hash` = SHA‑256 of the relay payload after redaction  

** (g) What MUST NOT be automated on day one **  
- No automatic write/mutation of shards, relay registry, or memory based on tool output.  
- No auto‑promotion of context to shard (`promote_context_to_shard`).  
- No auto‑application of assurance verdicts to shard labels.  
- No auto‑generation of new relay entries or modification of existing ones.  
- No auto‑evolution of skills or agents.  

---  
*End of deliverable.*
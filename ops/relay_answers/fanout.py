"""Fan the 6 open relay legs across the full fleet for independent evaluation.

whoart / claude-cli, 2026-08-28. Coach routes, fleet drafts, coach reviews.
Writes one markdown file per leg to ops/relay_answers/raw/.
"""
import sys
import json
import pathlib

# derive the repo's tools/ from this file: a hardcoded absolute path names the
# operator's account and disk layout on a public repo, and only works on one box.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))
from fleet import Fleet  # noqa: E402

OUT = pathlib.Path(__file__).parent / "raw"
OUT.mkdir(parents=True, exist_ok=True)

GROUND = """FACTS ABOUT THE NouGen REPO (verified from source, these outrank your priors):
- Local MCP server src/nougen_shards/mcp.py registers 19 @mcp.tool() tools:
  capture_experience, recall_memory, mark_utility, link_shards, recall_related,
  log_context_event, search_context, promote_context_to_shard, execute_sandboxed_code,
  run_brain_scan, run_brain_import, get_memory_stats, apply_skills, list_skills,
  load_skill, evolve_skill, ask_iris, ask_agent, list_agents.
- The fleet CONNECTOR (separate surface) exposes 25 tools: relay_open/read/create/ack/
  latest/claim_list, shards_recall/search/capture/amend/retract/forget/mark/status/window/
  coverage, tracker_daily/lanes/spend, vault_list/put, ask_griot, ask_rhea, kaedra_ask,
  fleet_whoami.
- src/nougen_shards/assurance.py ALREADY EXISTS: routes claims through Iris and labels them
  VERIFIED / CONTRADICTED / UNCERTAIN / UNVERIFIED with confidence, rationale, evidence_used,
  caveats. It never mutates shards from an automated verdict.
- src/nougen_shards/brain_scan/redaction.py ALREADY EXISTS: redact_content().
- Other existing modules: handoff.py, handoff_sync.py, handoff_triggers.py, handoff_dialects.py,
  graph.py, federation.py, gatekeeper.py, keymaker.py, history.py, evolution.py, skills.py,
  nougen_sandbox.py, vram_gate.py, tenants.py, billing.py, router.py, agents.py.
- tools/ has 50+ scripts incl. fleet.py (58-route dispatcher), dream_*.py, gateway_probe.py,
  handoff_guard.py, lane_freshness.py, nougenai_audit.py, capture_doctrine.py.
- README.md is 263 lines with ZERO generated-section markers. CHANGELOG.md is 141 lines.
- Rule: source truth outranks remembered claims. Do not invent files that are not listed above.

Answer in tight markdown. No preamble, no restating the question. Be specific and short.
"""

PROMPTS = {
    "01_dav1d_enforcement": GROUND + """
TASK: Dav1d is the fleet road authority. Spec the enforcement hooks for Relay CLAIMS.
Required capabilities: (1) reject a claim whose scope collides by PATH CONTAINMENT with active
work; (2) collapse duplicate logical claims from multiple connector lanes; (3) revoke/expire
stale claims by policy; (4) freeze one malfunctioning lane without stopping unrelated traffic;
(5) require evidence before marking critical work complete; (6) escalate repeated 4xx/5xx/52x
into repair work instead of silent retry storms; (7) reconcile contradictory relay assertions
against claims/SHAs/tests/telemetry/timestamps; (8) immutable auditable decision trail.
Constraint: Dav1d governs coordination, NOT a universal bottleneck. Non-conflicting traffic
must never ask permission. DETERMINISTIC CHECKS BEFORE MODEL JUDGMENT.
LIVE FIXTURE: two blade1tb/antigravity claims, same session, same goal, identical scope
"relay_daemon,hud,ui,keymaker", 21s apart, different SHAs (7374548 vs c921bc0).
DELIVER: (a) the exact deterministic predicate ladder in evaluation order, with what each
compares; (b) which of the 8 need model judgment at all and why; (c) the claim record fields
that must be added; (d) how the dedup rule would have collapsed the live fixture, stated as a
concrete rule; (e) the single smallest first commit that proves the loop.
""",
    "02_recursive_failure": GROUND + """
TASK: Codify "NouGen recursively learns through failure" as an enforceable fleet principle,
not a slogan. Loop: fumble -> recover -> adapt -> continue -> remember. Failure is training
material for the OS, not an exception outside the learning loop.
DELIVER: (a) the principle stated in <=60 words as doctrine; (b) 4-6 FALSIFIABLE invariants
that make it testable (each phrased so a check could fail); (c) where each invariant is
enforced given the modules listed above; (d) the shard-capture convention for a failure shard
(required fields); (e) why a "Learned" CHANGELOG category is or is not justified; (f) the
product-facing lines. Do not write marketing prose beyond (f).
""",
    "03_docs_compiler": GROUND + """
TASK: Design ONE tool, tools/nougen_docs.py -- a documentation COMPILER, not an AI overwrite.
Hierarchy of truth: 1 repo source/config/schemas/tests, 2 relay registry, 3 shards. Source
truth wins; relays explain transition; shards explain meaning. Bounded generated sections
fenced <!-- NOUGEN:AUTO:SECTION:START/END -->. Modes: --check --dry-run --write --changelog
--repo --all-public --since --explain. Needs a repo manifest, provenance sidecar state,
dedup/clustering of relays describing one incident, and a PUBLIC SANITIZER.
DELIVER: (a) module layout and the data flow in one diagram-as-text; (b) the repo manifest
schema, minimal fields only; (c) the provenance state record; (d) EXACTLY which existing
NouGen modules it must reuse instead of reimplementing -- name them; (e) the source-verification
rule set (memory claim vs repo fact, who wins, what gets emitted on disagreement); (f) the
dedup key for clustering relays; (g) what MUST NOT be automated on day one.
""",
    "04_readme_audit": GROUND + """
TASK: Public README audit protocol across all public NouGen repos. Stale README = a bug.
Sequencing question to answer first: hand-editing N READMEs that a compiler will later
regenerate is wasted work -- so what is the correct order of operations?
DELIVER: (a) the ordered protocol; (b) the DRIFT CLASS taxonomy (what kinds of staleness
exist -- e.g. counts, endpoints, install steps, env vars, terminology, dead links) with a
deterministic detector for each class; (c) which classes are safely auto-generated vs must
stay hand-written; (d) the canonical cross-repo terminology set implied by the facts above
(README = current truth, CHANGELOG = historical motion, RELAYS = operational motion,
SHARDS = durable memory, SOURCE = executable truth); (e) the exact drift-report output format.
""",
    "05_connector_tools": GROUND + """
TASK: 20 next-gen connector tools were proposed for closed-loop agency (observe -> reason ->
act -> verify -> remember): repo_scan, repo_read, repo_grep, shards_related, shard_from_diff,
repo_diff, repo_status, fleet_activity, fleet_compare, tests_run, command_run,
relay_from_failure, readme_sync, service_health, logs_query, incident_trace, verify_relay,
docs_drift, public_surface_audit, changelog_build, release_snapshot.
The leg explicitly asks: map each to EXISTING infrastructure, do not spawn redundant endpoints.
DELIVER a table with columns: TOOL | ALREADY EXISTS AS (name the module/tool/script from the
facts, or NONE) | VERDICT (ALIAS / THIN-WRAP / BUILD / DROP) | ONE-LINE JUSTIFICATION.
Then: the smallest high-leverage FIRST WAVE of at most 5 tools, ranked, each with the reason it
earns its slot ahead of the others. Then: which proposals are REDUNDANT with existing tools and
should be dropped outright. Be ruthless -- fewer tools is the correct answer.
""",
    "06_risks": GROUND + """
TASK: Adversarial review of this whole batch of 6 proposals (Dav1d claim enforcement, recursive-
failure doctrine, a docs compiler fusing relays+shards+source into public README/CHANGELOG, a
fleet-wide README audit, and 20 new connector tools).
Find what BREAKS. Specifically hunt for: (1) ways generated public docs leak private memory
despite a sanitizer; (2) ways claim enforcement deadlocks or blocks legitimate parallel work;
(3) circular dependencies between the proposals; (4) where "verified" could become a lie;
(5) which proposal is the most likely to be abandoned half-built and why; (6) the failure mode
where the docs compiler generates confident prose from a RETRACTED shard.
DELIVER: ranked findings, each = FAILURE MODE / CONCRETE TRIGGER / MITIGATION. No hedging, no
generic advice. Maximum 8 findings, ordered most severe first.
""",
}


def main() -> None:
    f = Fleet()
    print(f"[fleet] routes loaded: {len(f.routes)}", flush=True)
    healthy = f.probe(verbose=False)
    print(f"[fleet] healthy routes: {len(healthy)}", flush=True)

    keys = list(PROMPTS)
    # map() returns (index, route_name, output) in COMPLETION order, not input order.
    for idx, route_name, out in f.map([PROMPTS[k] for k in keys], max_tokens=2048):
        k = keys[idx]
        body = f"<!-- route: {route_name} -->\n\n{out}"
        (OUT / f"{k}.md").write_text(body, encoding="utf-8")
        print(f"[write] {k}.md  route={route_name}  {len(out)} chars", flush=True)
    print("[done]")


if __name__ == "__main__":
    main()

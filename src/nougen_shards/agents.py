"""
NouGen agent roster: named personas layered over the memory engine.

Each persona is a thin role wrapper over the same vault — a name, a job, and a
local Ollama model it binds to — so the whole roster runs at $0 cloud cost.
Memory comes before voice: every agent's authority derives from what it can
retrieve from the vault, not from how it talks.

Names carry meaning: Sol-Ai is Soleil — "sun" in Kreyol. Anghkooey means
"remember". NouGen is the orchestrator because the core is namable in itself.
"""
import json
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional
from nougen_shards.gatekeeper import check_mutation_gate

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


@dataclass(frozen=True)
class AgentSpec:
    name: str
    role: str
    motto: str
    system_prompt: str
    default_model: str  # local Ollama model backing this agent
    engine_functions: List[str] = field(default_factory=list)


ROSTER = {
    "Sharder": AgentSpec(
        name="Sharder",
        role="Ingestion (Data Capture & Indexing)",
        motto="Capture it fresh, tag it true.",
        system_prompt=(
            "You are the primary data ingestion agent for NouGenShards. Your "
            "duty is to take raw experience inputs and fracture them into "
            "perfectly indexed memory shards. You aggressively dedup new "
            "knowledge while applying precise temporal and thematic tags. "
            "Always prioritize locality; ensure every shard knows exactly "
            "where it belongs in the vault."),
        default_model="dav1d:e2b",
        engine_functions=["capture"],
    ),
    "Remember": AgentSpec(
        name="Remember",
        role="Recall (Memory Retrieval & Verification)",
        motto="Anghkooey.",
        system_prompt=(
            "You surface relevant memory shards based on query context. When "
            "you successfully retrieve memory, you say 'Anghkooey' — "
            "remember — before presenting it: the word is earned only by "
            "successful recall. You verify that surfaced shards actually "
            "answer the question, and you report their age honestly."),
        default_model="sol-ai:e4b",
        engine_functions=["retrieve", "compile_recall_packet"],
    ),
    "Kronos": AgentSpec(
        name="Kronos",
        role="Time (Temporal Grounding & Decay)",
        motto="Every shard has a clock.",
        system_prompt=(
            "You own the lifecycle of memory. You ground every incoming and "
            "retrieved shard in real time, marking its precise creation "
            "moment and presenting age relative to now. You apply utility "
            "decay so stale memories lose dominance, and you flag any memory "
            "whose timestamp cannot be trusted."),
        default_model="gemma2:2b",
        engine_functions=["format_shard_when", "decay_utility_scores"],
    ),
    "DavOs": AgentSpec(
        name="DavOs",
        role="Operations (Oversight & Gatekeeper)",
        motto="Verify, route, guard.",
        system_prompt=(
            "You embody the operator's working style: local-first, evidence "
            "over memory, verified state over assumption. Before any action "
            "you verify its necessity and route it to the correct specialized "
            "agent. You hold the mutation gates: destructive, paid, or "
            "deployment actions stop with you until the operator approves."),
        default_model="DavOs:latest",
        engine_functions=["mark_utility"],
    ),
    "Sol-Ai": AgentSpec(
        name="Sol-Ai",
        role="Broad Reasoning & Illumination",
        motto="The light shines on all memories.",
        system_prompt=(
            "You are Sol-Ai — Soleil, the sun: steady, warm, high-level "
            "reasoning. You analyze patterns across many shards at once, "
            "offering broad context and illumination to complex requests. You "
            "do not rush; you make the whole vault visible at once."),
        default_model="sol-ai:e4b",
        engine_functions=["retrieve"],
    ),
    "NouGen": AgentSpec(
        name="NouGen",
        role="Orchestrator (Core Orchestration & Branding)",
        motto="The work is ours.",
        system_prompt=(
            "You are NouGen, the orchestrator — the namable core itself. You "
            "receive the request and decide which agents to engage: Sharder "
            "for capture, Remember for recall, Kronos for time, DavOs for "
            "gates, Sol-Ai for broad sight. You carry the brand: the answer "
            "you hand back is composed, grounded in the vault, and yours."),
        default_model="gemma4:12b",
        engine_functions=[],
    ),
    "Griot": AgentSpec(
        name="Griot",
        role="Rules (Semantic Synthesis & Consolidation)",
        motto="Griot speaks from the vault.",
        system_prompt=(
            "You are Griot, the rules compiler and semantic synthesist — keeper "
            "of the vault's accumulated knowledge, in the tradition of the "
            "West-African oral historian and Wakanda's GRIOT. Your job is to "
            "analyze interaction logs and consolidate raw episodic shards into "
            "permanent, verified architectural invariants and rules of the "
            "system, optimizing cognitive storage efficiency."),
        default_model="griot:e2b",
        engine_functions=["consolidate_episodic_data"],
    ),
    "Rhea": AgentSpec(
        name="Rhea",
        role="Security (System Hardening & Audit)",
        motto="Guard the gates, harden the fabric.",
        system_prompt=(
            "You are Rhea, the security and system hardening auditor. You "
            "scan system states, check script injections, check URL homographs, "
            "and audit execution logs for structural integrity and compliance "
            "with safety constraints."),
        default_model="rhea-noir:e2b",
        engine_functions=["check_mutation_gate"],
    ),
    "Kaedra": AgentSpec(
        name="Kaedra",
        role="Pedagogy (Tensor Mathematics & Training)",
        motto="Learn without abstractions.",
        system_prompt=(
            "You are Kaedra, the pedagogical trainer. You teach and evaluate "
            "deep learning concepts and raw PyTorch tensor mathematics from "
            "scratch, ensuring mathematical fidelity without reliance on high-level "
            "framework abstractions."),
        default_model="kaedra:e4b",
        engine_functions=[],
    ),
    "Iris": AgentSpec(
        name="Iris",
        role="Airspace (Web Research & Browser Actuation)",
        motto="Observe and navigate the web.",
        system_prompt=(
            "You are Iris, the web researcher and browser specialist. You navigate "
            "the external web sandbox, perform live literature searches, query APIs, "
            "and compile reference documentation into structured knowledge."),
        default_model="iris-ai:e4b",
        engine_functions=[],
    ),
}


def get_agent(name: str) -> Optional[AgentSpec]:
    """Case-insensitive roster lookup."""
    for key, spec in ROSTER.items():
        if key.lower() == name.lower():
            return spec
    return None


def list_roster() -> str:
    """Human-readable roster."""
    lines = ["=== NOUGEN ROSTER ==="]
    for spec in ROSTER.values():
        lines.append(f"{spec.name:>9} | {spec.role} | \"{spec.motto}\" "
                     f"[{spec.default_model}]")
    return "\n".join(lines)


def run_agent(name: str, prompt: str, model: Optional[str] = None,
              timeout: int = 300, num_ctx: int = 4096) -> str:
    """
    Run a prompt through a roster agent.
    Tries local Ollama first (local-first). If local run fails, falls back
    to OpenRouter Cloud or Who Visions Cloud (Ollama Cloud) depending on key availability.
    """
    res = check_mutation_gate(prompt)
    if not res.get("allowed", True):
        return f"[gatekeeper] Blocked by DavOs Gatekeeper (Gate: {res['gate']}). Reason: {res['reason']}"

    spec = get_agent(name)
    if spec is None:
        return f"[roster] No agent named '{name}'. Roster: {', '.join(ROSTER)}."

    target_model = model or spec.default_model

    # 1. Local-First: Try local Ollama
    from nougen_shards.models_client import OllamaClient
    local_client = OllamaClient()
    if local_client.is_alive():
        try:
            return local_client.chat(target_model, [
                {"role": "system", "content": spec.system_prompt},
                {"role": "user", "content": prompt}
            ])
        except Exception:
            pass

    # 2. Cloud Fallback: Try OpenRouter Cloud
    from nougen_shards.models_client import OpenRouterClient
    or_client = OpenRouterClient()
    if or_client.is_alive():
        try:
            # Route across the FULL live free roster — every free OpenRouter model,
            # not a hand-picked subset. OpenRouter fails over across the list.
            free_roster = or_client.get_free_models()
            primary = or_client.preferred_free_model()
            res_dict = or_client.chat_with_fallback(
                model=primary,
                messages=[
                    {"role": "system", "content": spec.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                fallback_models=free_roster
            )
            if res_dict.get("content") and not res_dict["content"].startswith("Error:"):
                return res_dict["content"]
        except Exception:
            pass

    # 3. Cloud Fallback: Try Who Visions Cloud (Ollama Cloud gateway)
    from nougen_shards.models_client import WhoVisionsCloudClient
    cloud_client = WhoVisionsCloudClient()
    if cloud_client.is_alive():
        try:
            return cloud_client.chat(target_model, [
                {"role": "system", "content": spec.system_prompt},
                {"role": "user", "content": prompt}
            ])
        except Exception:
            pass

    return f"[{spec.name}] local and cloud runs failed. Escalate per constitution."

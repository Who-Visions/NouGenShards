"""Which node tools a tenant identity may call (DECISION shard 30954).

A tenant gets the full NouGen surface *scoped to its own root*, not a stripped
shard-only subset. Every tool registered on the node MCP surface must be
labelled here: ``TENANT_SCOPED`` (binds to ``core.active_home()`` /
``core.active_vault_dir()`` so a tenant only ever touches its own data) or
``OWNER_ONLY`` (touches the host machine, the owner's agents, hardware, shared
services, or author-exclusive IP). An unlabelled tool is denied to tenants and
``tests/test_tenant_full_surface.py`` fails until it is labelled, so a new tool
cannot ship with an accidental exposure.

Env ``NOUGEN_TENANT_EXTRA_TOOLS`` (comma list) widens the tenant set at run
time for one node; ``NOUGEN_TENANT_DENY_TOOLS`` narrows it. Both are logged.
"""
from __future__ import annotations

import logging
import os
from typing import Iterable

logger = logging.getLogger(__name__)

OWNER_TENANT_ID = "owner"

# Bound to the identity's vault / home: safe for every tenant.
TENANT_SCOPED: frozenset[str] = frozenset({
    # shards (active vault)
    "recall_memory", "search", "get_shard", "capture_experience", "mark_utility",
    "substrate_coverage", "recall_window", "shard_amend", "shard_retract", "shard_forget",
    "recall_graph", "temporal_query", "recall_layered", "recall_related", "link_shards",
    "node_status",
    # keymaker vault (active_home()/secrets)
    "vault_put", "vault_list",
    # prospective memory (active_vault_dir()/destinies.db)
    "unfinished_destinies", "create_destiny", "get_destiny", "update_destiny",
    "link_destiny", "search_destinies",
    # NouGenMsg (active_home()/inbox, messages.db; no machine pipes for tenants)
    "nougenmsg", "nougenmsg_latest", "nougenmsg_inbox", "nougenmsg_read", "nougenmsg_search",
    # relay board (active_home()/relay/.handoffs)
    "relay_open_legs", "relay_claim_leg", "relay_create_leg", "relay_ack_leg",
    # pure compute / read-only repo assets
    "nougen_time_now", "nougen_time_format",
    "nougen_verse_analyze", "nougen_verse_score", "nougen_verse_plan", "nougen_verse_repair",
    "morph_gate", "morph_atom_catalog", "morph_holistic_gate",
    "evidence_assure", "evaluate_evidence_template", "evaluate_quota",
    "nougen_translate_response",
    "list_skills", "load_skill", "apply_skills", "nougen_skill_search", "nougen_skill_get",
})

# Touches the host, the owner's agents/hardware/shared services, or owner IP.
OWNER_ONLY: frozenset[str] = frozenset({
    # agents and local compute on the owner's machines
    "ask_rhea", "dav1d_exec", "agy_ask", "ask_dav1d", "ask_iris", "ask_agent", "list_agents",
    "persona_resolve",
    # fleet, tunnels, mesh, daemons, leases, host maintenance
    "fleet_status", "fleet_send", "wake_daemon_status", "tunnel_status", "sync_mesh_status",
    "pr_lease_status", "pr_lease_acquire", "pr_lease_release", "token_fuse_status",
    "shard_vacuum", "dream_trigger", "turn_compound", "studio_lighting",
    # owner media pipelines and services
    "wispr_latest", "wispr_history", "youtube_ingest", "nougentube_preview", "nougentube_ingest",
    "nougentube_transcript", "nougen_media_transcribe", "nougentube", "transcribe_media",
    # owner GitHub token
    "github_repo_inspect", "github_repo_read", "github_repo_capture_readme",
    # author-exclusive IP / personas (xoah_* register from the node plugin dir
    # and exist only where that plugin is installed; labelled here so a node
    # that has them never exposes them)
    "shadow_dweller_search",
    "ask_xoah", "xoah_active_scars", "xoah_conservation", "xoah_precedents", "xoah_pressure",
    "xoah_relationship", "xoah_self", "xoah_then_vs_now", "xoah_throne", "xoah_unwritten",
    "mrsb_audit", "mrsb_status", "mrsb_lineage", "mrsb_character",
    "mrsb_recall", "mrsb_recurse",
    # shared stores not yet bound to active_home() (see wargames/ledger.md)
    "arxiv_research", "arxiv_capabilities", "arxiv_radar", "arxiv_lab_watch", "arxiv_paper",
    "semantic_context_assemble", "context_task_checkpoint", "context_task_current",
    "context_feedback", "context_correct", "context_session_assemble",
    # host toolchains (lean, z3, benchmarks, RSI, control plane)
    "formal_verify_lean", "formal_solve_smt", "formal_verification_suite",
    "information_gain_evaluate", "information_dynamics_benchmark",
    "rsi_graze_shards", "rsi_cycle", "rsi_diagnostics",
    "control_plane_context_select", "control_plane_pareto_route", "control_plane_adherence_evaluate",
})

_ENV_EXTRA = "NOUGEN_TENANT_EXTRA_TOOLS"
_ENV_DENY = "NOUGEN_TENANT_DENY_TOOLS"


def _env_set(var: str) -> frozenset[str]:
    raw = os.environ.get(var, "")
    names = frozenset(n.strip() for n in raw.split(",") if n.strip())
    if names:
        logger.info("tenant_policy: %s=%s", var, ",".join(sorted(names)))
    return names


def tenant_allowed_names() -> frozenset[str]:
    """Effective tenant set: TENANT_SCOPED + env extras - env denies.

    Extras are an operator knob on the node process (a tenant cannot set this
    node's environment), and they still cannot grant an OWNER_ONLY tool: that
    floor is code, not configuration.
    """
    extra = _env_set(_ENV_EXTRA)
    refused = extra & OWNER_ONLY
    if refused:
        logger.warning("tenant_policy: %s cannot grant owner-only tools, ignored: %s",
                       _ENV_EXTRA, ",".join(sorted(refused)))
    return (TENANT_SCOPED | (extra - OWNER_ONLY)) - _env_set(_ENV_DENY)


def tenant_allowed(name: object) -> bool:
    return isinstance(name, str) and name in tenant_allowed_names()


def allowed_for(tenant_id: str, name: object) -> bool:
    """Owner calls everything; a tenant only the scoped set."""
    if tenant_id == OWNER_TENANT_ID:
        return True
    return tenant_allowed(name)


def classify(registered: Iterable[str]) -> dict:
    """Label the live tool list; ``unclassified`` must be empty before merge."""
    names = set(registered)
    both = TENANT_SCOPED & OWNER_ONLY
    return {
        "tenant": sorted(names & TENANT_SCOPED),
        "owner_only": sorted(names & OWNER_ONLY),
        "unclassified": sorted(names - TENANT_SCOPED - OWNER_ONLY),
        "stale_labels": sorted((TENANT_SCOPED | OWNER_ONLY) - names),
        "double_labelled": sorted(both),
    }


def filter_tool_listing(tools: list, tenant_id: str) -> list:
    """Drop tools the identity cannot call from a ``tools/list`` result."""
    if tenant_id == OWNER_TENANT_ID:
        return tools
    return [t for t in tools if isinstance(t, dict) and tenant_allowed(t.get("name"))]

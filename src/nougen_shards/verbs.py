"""NouGen 11-Verb Cognitive Instruction Set & 6-Plane Architecture Registry.

Canonical semantic contracts locked by Dave & Fleet (2026-09-23).
Provides non-overlapping authority definition across Memory, Coordination,
Observability, Intent, Execution, and Learning planes.
"""
from __future__ import annotations
from typing import Dict, Any

PLANES: Dict[str, Dict[str, Any]] = {
    "memory": {
        "name": "Memory Plane",
        "verbs": ["shard"],
        "description": "Durable memory and retrievable evidence.",
    },
    "coordination": {
        "name": "Coordination Plane",
        "verbs": ["relay", "msg", "live"],
        "description": "Ownership continuity, inter-agent communication, and present-tense operational truth.",
    },
    "observability": {
        "name": "Observability Plane",
        "verbs": ["track"],
        "description": "Measurement, telemetry, costs, usage, and metrics.",
    },
    "intent": {
        "name": "Intent Plane",
        "verbs": ["destiny", "wish"],
        "description": "Prospective long-horizon target states and next actionable testable deltas.",
    },
    "execution": {
        "name": "Execution Plane",
        "verbs": ["build", "harden"],
        "description": "Candidate creation and adversarial verification.",
    },
    "learning": {
        "name": "Learning Plane",
        "verbs": ["dream", "evolve"],
        "description": "Replay/exploration and promotion of verified lessons into durable capabilities.",
    }
}

VERBS: Dict[str, Dict[str, Any]] = {
    "shard": {
        "plane": "memory",
        "role": "Durable memory and evidence",
        "description": "What happened, what was learned, what remains retrievable.",
        "authority": "Record and retrieve ground-truth historical evidence.",
        "forbidden_authority": "Cannot claim future state or dictate current coordination without verification.",
        "evidence_produced": "Memory Shards in 9-DB cluster with vector/FTS embeddings.",
        "next_verbs": ["dream", "evolve", "wish"]
    },
    "relay": {
        "plane": "coordination",
        "role": "Handoff and responsibility continuity",
        "description": "Who owns what next and why.",
        "authority": "Transfer session baton, responsibility, and state across agents/machines.",
        "forbidden_authority": "Accepting a relay is not proof of work completion.",
        "evidence_produced": "Git handoff legs (.handoffs/*.json + .md).",
        "next_verbs": ["live", "wish", "build"]
    },
    "live": {
        "plane": "coordination",
        "role": "Present-tense operational truth",
        "description": "What is reachable, running, listening, connected, or degraded now.",
        "authority": "Direct socket/process/port/host probing of live infrastructure.",
        "forbidden_authority": "Cannot fabricate offline services as live without socket confirmation.",
        "evidence_produced": "Live status telemetry and daemon health reports.",
        "next_verbs": ["msg", "wish", "track"]
    },
    "msg": {
        "plane": "coordination",
        "role": "Active inter-agent communication",
        "description": "What the fleet is saying now.",
        "authority": "Immediate IPC, pipe delivery, and fleet broadcasting.",
        "forbidden_authority": "A message is not durable memory merely because it was transmitted.",
        "evidence_produced": "Inbox JSON receipts and named pipe delivery acknowledgments.",
        "next_verbs": ["live", "relay", "shard"]
    },
    "track": {
        "plane": "observability",
        "role": "Measurement and telemetry",
        "description": "Usage, cost, state changes, performance, quotas, and behavioral telemetry.",
        "authority": "Measure token burn, latency, compute usage, and budget thresholds.",
        "forbidden_authority": "Observing a metric does not fix or mutate state.",
        "evidence_produced": "Usage ledgers, token deltas, latency tables.",
        "next_verbs": ["wish", "live", "shard"]
    },
    "wish": {
        "plane": "intent",
        "role": "Next desired delta",
        "description": "A bounded, testable change between verified current state and intended state.",
        "authority": "Structure actionable engineering requests with verification criteria.",
        "forbidden_authority": "A wish is not a destiny nor a completed build until verified.",
        "evidence_produced": "Wishlist items, acceptance criteria contracts.",
        "next_verbs": ["build", "harden"]
    },
    "destiny": {
        "plane": "intent",
        "role": "Long-horizon prospective target state",
        "description": "What future must remain directionally true across many cycles.",
        "authority": "Define goal graphs, triggers, required events, and forbidden outcomes.",
        "forbidden_authority": "Must never masquerade as present fact or history without evidence.",
        "evidence_produced": "Destiny graph records in destinies.db.",
        "next_verbs": ["wish", "build"]
    },
    "build": {
        "plane": "execution",
        "role": "Creation of candidate implementation",
        "description": "Authoring code, scripts, configurations, and PRs.",
        "authority": "Produce candidate artifacts and branch commits.",
        "forbidden_authority": "A build is not success merely because it compiled.",
        "evidence_produced": "Source code patches, PRs, build artifacts.",
        "next_verbs": ["harden", "shard"]
    },
    "harden": {
        "plane": "execution",
        "role": "Adversarial verification and regression testing",
        "description": "Failure injection, unit testing, schema verification, and external proof.",
        "authority": "Reject flawed builds and certify regression-free changes.",
        "forbidden_authority": "Passing one test is not evolutionary promotion.",
        "evidence_produced": "Pytest reports, acceptance test outputs, proof receipts.",
        "next_verbs": ["shard", "evolve", "relay"]
    },
    "dream": {
        "plane": "learning",
        "role": "Offline replay and proposal generation",
        "description": "Replay trajectories, counterfactual exploration, and lesson compression.",
        "authority": "Propose improvements from past patterns; does not self-promote.",
        "forbidden_authority": "A dream proposal is not reality until validated by GM or Harden.",
        "evidence_produced": "Dream digests, compressed lesson candidates.",
        "next_verbs": ["evolve", "wish"]
    },
    "evolve": {
        "plane": "learning",
        "role": "Promotion into durable capability",
        "description": "Promotion of verified lessons into skills, tools, and compiler primitives.",
        "authority": "Upgrade agent skills, tools, and core system rules.",
        "forbidden_authority": "Cannot promote unverified or unhardened proposals.",
        "evidence_produced": "Installed skills, updated MCP tools, hardened constitution rules.",
        "next_verbs": ["destiny", "shard", "relay"]
    }
}

NON_COLLAPSE_RULES = [
    "A message is not memory merely because it was said.",
    "A relay is not truth merely because it was accepted.",
    "A build is not success merely because it compiled.",
    "A hardened build is not evolution merely because one test passed.",
    "A Dream proposal is not reality merely because an LLM generated it.",
    "A Wish is not Destiny merely because it is important.",
    "A Destiny is not history until reality produces evidence.",
    "No subsystem may silently assume the authority of another plane."
]


def get_verb_info(verb: str) -> Dict[str, Any]:
    """Retrieve the authoritative semantic contract for a NouGen verb."""
    v = (verb or "").strip().lower()
    if v in VERBS:
        return {"verb": v, **VERBS[v]}
    return {"error": f"Unknown verb {v!r}. Valid verbs: {list(VERBS.keys())}"}


def get_all_verbs() -> Dict[str, Any]:
    """Return the entire 11-verb registry and 6-plane schema."""
    return {
        "version": "2026.09.23",
        "planes": PLANES,
        "verbs": VERBS,
        "non_collapse_rules": NON_COLLAPSE_RULES
    }

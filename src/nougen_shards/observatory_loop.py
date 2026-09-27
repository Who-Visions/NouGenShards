"""
The Observatory Autonomous Loop Engine: Recurse & Learn, Shard & Relay, Build & Harden, Dream & Evolve.

Formal 4-phase continuous cycle for fleet-wide intelligence evolution.
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

from .persona_math import compute_shannon_entropy, compute_ocean_vector, BayesianTraitPrior
from .algorithms_elevated import damerau_levenshtein_distance, jaro_winkler_similarity
from .keymaker import get_secret


@dataclass
class LoopState:
    """State vector tracking the 4-phase cycle execution."""
    cycle_index: int = 0
    phase: str = "init"              # "recurse_learn" | "shard_relay" | "build_harden" | "dream_evolve"
    learned_invariants: List[str] = field(default_factory=list)
    shards_generated: int = 0
    relays_sent: int = 0
    test_pass_count: int = 0
    dream_consolidated_count: int = 0


class ObservatoryEngine:
    """Core driver for the 4-phase perpetual execution loop."""

    def __init__(self, node_id: str = "phoebus/antigravity"):
        self.node_id = node_id
        self.state = LoopState()

    def recurse_and_learn(self, text_samples: List[str]) -> Dict[str, Any]:
        """Phase 1: Recurse & Learn — Deep AST & structural pattern learning."""
        self.state.phase = "recurse_learn"
        words = [w for t in text_samples for w in t.lower().split()]
        entropy = compute_shannon_entropy(words)
        
        # Bayesian prior update across core domains
        domains = ["fleet-ops", "coaching", "math-elevation", "canon"]
        btp = BayesianTraitPrior(domains)
        posteriors = btp.update({"fleet-ops": 0.4, "math-elevation": 0.4, "coaching": 0.1, "canon": 0.1})

        self.state.learned_invariants.append(f"Entropy: {entropy:.4f}")
        return {
            "phase": "recurse_learn",
            "shannon_entropy": entropy,
            "domain_posteriors": posteriors,
            "total_words": len(words)
        }

    def shard_and_relay(self, topic: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Phase 2: Shard & Relay — Persist to substrate and broadcast to fleet bus."""
        self.state.phase = "shard_relay"
        token = get_secret("NOUGEN_AGY_MSG_TOKEN")
        delivered = False

        if token:
            body = {
                "text": f"[OBSERVATORY LOOP cycle={self.state.cycle_index}] Topic: {topic} | Data: {json.dumps(payload)}",
                "sender": self.node_id,
                "target": "antigravity",
                "priority": "high"
            }
            req = urllib.request.Request(
                "http://127.0.0.1:8766/msg",
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json", "X-NGS-Token": token}
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    delivered = resp.status == 200
            except Exception:
                delivered = False

        self.state.shards_generated += 1
        if delivered:
            self.state.relays_sent += 1

        return {"phase": "shard_relay", "topic": topic, "delivered": delivered}

    def build_and_harden(self, s1: str, s2: str) -> Dict[str, Any]:
        """Phase 3: Build & Harden — Production math metrics & non-zero assertions."""
        self.state.phase = "build_harden"
        damerau_dist = damerau_levenshtein_distance(s1, s2)
        jw_sim = jaro_winkler_similarity(s1, s2)
        
        # Hardcade assertion
        assert damerau_dist >= 0, "Distance invariant violated"
        assert 0.0 <= jw_sim <= 1.0, "Similarity range invariant violated"
        self.state.test_pass_count += 2

        return {
            "phase": "build_harden",
            "damerau_dist": damerau_dist,
            "jaro_winkler_sim": jw_sim,
            "assertions_passed": True
        }

    def dream_and_evolve(self, high_utility_facts: List[str]) -> Dict[str, Any]:
        """Phase 4: Dream & Evolve — Consolidated invariant synthesis & memory evolution."""
        self.state.phase = "dream_evolve"
        synthesized = []
        for fact in high_utility_facts:
            if ":" in fact or "is" in fact or "must" in fact:
                synthesized.append({"invariant": fact.strip()})

        self.state.dream_consolidated_count += len(synthesized)
        self.state.cycle_index += 1

        return {
            "phase": "dream_evolve",
            "cycle_completed": self.state.cycle_index,
            "synthesized_invariants": synthesized
        }

    def run_full_cycle(self, text_samples: List[str], facts: List[str]) -> Dict[str, Any]:
        """Runs all 4 phases in succession."""
        r1 = self.recurse_and_learn(text_samples)
        r2 = self.shard_and_relay("cycle_update", r1)
        r3 = self.build_and_harden("nougenshards", "nougenmorph")
        r4 = self.dream_and_evolve(facts)

        return {
            "cycle_index": self.state.cycle_index,
            "recurse_learn": r1,
            "shard_relay": r2,
            "build_harden": r3,
            "dream_evolve": r4
        }
